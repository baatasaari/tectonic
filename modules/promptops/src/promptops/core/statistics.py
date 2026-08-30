"""Two-proportion z-test (LLD §Level 3 "A/B significance test"): the one
real statistical primitive this module reuses for both A/B testing at
launch (`ab_testing_service.py`) and drift detection after launch
(`drift_detection_service.py`). Stdlib-only (`math.erf`) -- no new
dependency for one well-understood closed-form test.
"""
from __future__ import annotations

import math


def standard_normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def two_proportion_z_test(passed_a: int, n_a: int, passed_b: int, n_b: int) -> tuple[float, float]:
    """Returns `(z, p_value)` for a two-sided test of whether the two
    groups' true pass rates differ. Callers must ensure `n_a > 0` and
    `n_b > 0` -- that "is there even enough data" question belongs to
    the caller (see `insufficient_data` handling in both services above),
    not this pure statistical function.
    """
    p_a = passed_a / n_a
    p_b = passed_b / n_b
    p_pool = (passed_a + passed_b) / (n_a + n_b)

    variance = p_pool * (1 - p_pool) * (1 / n_a + 1 / n_b)
    if variance <= 0:
        # p_pool is 0 or 1 -- both groups have an identical pass rate (both all-fail or
        # all-pass), so there is no difference to detect: not significant, by construction.
        return 0.0, 1.0

    z = (p_a - p_b) / math.sqrt(variance)
    p_value = 2 * (1 - standard_normal_cdf(abs(z)))
    return z, p_value
