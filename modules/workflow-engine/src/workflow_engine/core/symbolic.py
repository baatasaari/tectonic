"""Symbolic Rule Executor (LLD §2.2, stack table).

The LLD names `durable-rules`/Nools-equivalent as the primary choice, with an
explicit fallback: "a lightweight custom rule DSL compiled to Python callables
if third-party engine proves too heavyweight". This module takes that fallback
so deterministic-step evaluation has no third-party runtime dependency and is
trivially explainable: a rule is a boolean expression over the step's input
context plus an output dict to emit when it matches.

Expressions are evaluated with a restricted AST walker (no attribute access,
no calls except a small allowlist, no imports) rather than `eval`, so a rule
authored by a non-technical builder user can't execute arbitrary code.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Any

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_ALLOWED_BOOLOPS = {ast.And: all, ast.Or: any}
_ALLOWED_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}
_ALLOWED_UNARYOPS = {ast.Not: operator.not_, ast.USub: operator.neg}


class RuleEvaluationError(Exception):
    pass


class _SafeEvaluator(ast.NodeVisitor):
    """Walks a restricted expression AST, resolving Name/Attribute chains
    against the supplied context dict only."""

    def __init__(self, context: dict[str, Any]):
        self.context = context

    def visit(self, node: ast.AST) -> Any:
        method = getattr(self, f"_eval_{type(node).__name__}", None)
        if method is None:
            raise RuleEvaluationError(f"disallowed expression element: {type(node).__name__}")
        return method(node)

    def _eval_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def _eval_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def _eval_Name(self, node: ast.Name) -> Any:
        if node.id not in self.context:
            raise RuleEvaluationError(f"unknown identifier '{node.id}'")
        return self.context[node.id]

    def _eval_Attribute(self, node: ast.Attribute) -> Any:
        base = self.visit(node.value)
        if isinstance(base, dict) and node.attr in base:
            return base[node.attr]
        raise RuleEvaluationError(f"unknown attribute '{node.attr}'")

    def _eval_Subscript(self, node: ast.Subscript) -> Any:
        base = self.visit(node.value)
        key = self.visit(node.slice)
        return base[key]

    def _eval_BoolOp(self, node: ast.BoolOp) -> Any:
        fn = _ALLOWED_BOOLOPS[type(node.op)]
        return fn(self.visit(v) for v in node.values)

    def _eval_BinOp(self, node: ast.BinOp) -> Any:
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise RuleEvaluationError(f"disallowed operator: {type(node.op).__name__}")
        return op(self.visit(node.left), self.visit(node.right))

    def _eval_UnaryOp(self, node: ast.UnaryOp) -> Any:
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise RuleEvaluationError(f"disallowed unary operator: {type(node.op).__name__}")
        return op(self.visit(node.operand))

    def _eval_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op_node, comparator in zip(node.ops, node.comparators):
            op = _ALLOWED_CMPOPS.get(type(op_node))
            if op is None:
                raise RuleEvaluationError(f"disallowed comparison: {type(op_node).__name__}")
            right = self.visit(comparator)
            if not op(left, right):
                return False
            left = right
        return True

    def _eval_List(self, node: ast.List) -> list:
        return [self.visit(v) for v in node.elts]

    def _eval_Tuple(self, node: ast.Tuple) -> tuple:
        return tuple(self.visit(v) for v in node.elts)


def safe_eval(expression: str, context: dict[str, Any]) -> Any:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise RuleEvaluationError(f"invalid expression syntax: {e}") from e
    return _SafeEvaluator(context).visit(tree)


@dataclass
class SymbolicRule:
    id: str
    when: str  # boolean expression over context
    then: dict[str, Any]  # output emitted when `when` evaluates truthy
    priority: int = 0


class SymbolicRuleExecutor:
    """Deterministic rule evaluation for `execution_mode=symbolic` steps.

    Rules are registered per `symbolic_rule_ref` (from the node config) and
    evaluated in priority order (highest first); the first matching rule's
    `then` clause is the step output. No match is a hard failure — symbolic
    steps must be deterministic and total over their declared rule set.
    """

    def __init__(self) -> None:
        self._rulesets: dict[str, list[SymbolicRule]] = {}

    def register_ruleset(self, rule_ref: str, rules: list[SymbolicRule]) -> None:
        self._rulesets[rule_ref] = sorted(rules, key=lambda r: -r.priority)

    def evaluate(self, rule_ref: str, context: dict[str, Any]) -> dict[str, Any]:
        rules = self._rulesets.get(rule_ref)
        if rules is None:
            raise RuleEvaluationError(f"no ruleset registered for '{rule_ref}'")
        for rule in rules:
            if safe_eval(rule.when, context):
                return {"matched_rule_id": rule.id, **rule.then}
        raise RuleEvaluationError(f"no rule in '{rule_ref}' matched context")
