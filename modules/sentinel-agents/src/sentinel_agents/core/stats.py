"""Welford's online algorithm for numerically stable running mean/
variance — the statistical basis for the Behavioural Baseliner's default
"statistical" method (LLD §2 sub-components).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WelfordState:
    mean: float
    m2: float
    count: int


def update(state: WelfordState, value: float) -> WelfordState:
    count = state.count + 1
    delta = value - state.mean
    mean = state.mean + delta / count
    delta2 = value - mean
    m2 = state.m2 + delta * delta2
    return WelfordState(mean=mean, m2=m2, count=count)


def variance(state: WelfordState) -> float:
    return state.m2 / state.count if state.count > 0 else 0.0


def z_score(value: float, state: WelfordState) -> float:
    std = math.sqrt(variance(state))
    if std == 0:
        return 0.0 if value == state.mean else float("inf")
    return abs(value - state.mean) / std
