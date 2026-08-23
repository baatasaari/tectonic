import pytest

from workflow_engine.core.symbolic import (
    RuleEvaluationError,
    SymbolicRule,
    SymbolicRuleExecutor,
    safe_eval,
)


def test_safe_eval_basic_expressions():
    assert safe_eval("amount > 1000 and region == 'EU'", {"amount": 1500, "region": "EU"}) is True
    assert safe_eval("amount > 1000 and region == 'EU'", {"amount": 500, "region": "EU"}) is False


def test_safe_eval_rejects_unknown_identifier():
    with pytest.raises(RuleEvaluationError):
        safe_eval("__import__('os')", {})


def test_safe_eval_rejects_attribute_not_in_dict():
    with pytest.raises(RuleEvaluationError):
        safe_eval("x.secret", {"x": {"visible": 1}})


def test_symbolic_rule_executor_matches_highest_priority_first():
    executor = SymbolicRuleExecutor()
    executor.register_ruleset(
        "eligibility",
        [
            SymbolicRule(id="low_amount", when="amount < 100", then={"decision": "auto_approve"}, priority=0),
            SymbolicRule(id="high_amount", when="amount >= 100", then={"decision": "escalate"}, priority=10),
        ],
    )
    result = executor.evaluate("eligibility", {"amount": 5000})
    assert result["decision"] == "escalate"
    assert result["matched_rule_id"] == "high_amount"


def test_symbolic_rule_executor_no_match_raises():
    executor = SymbolicRuleExecutor()
    executor.register_ruleset("eligibility", [SymbolicRule(id="r1", when="amount < 0", then={})])
    with pytest.raises(RuleEvaluationError):
        executor.evaluate("eligibility", {"amount": 5})


def test_symbolic_rule_executor_unknown_ruleset_raises():
    executor = SymbolicRuleExecutor()
    with pytest.raises(RuleEvaluationError):
        executor.evaluate("nope", {})
