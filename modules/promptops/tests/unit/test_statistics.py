"""Tests for core/statistics.py -- the two-proportion z-test both the
A/B Testing Service and Drift Detection Service reuse."""
from __future__ import annotations

from promptops.core.statistics import two_proportion_z_test


def test_identical_pass_rates_are_never_significant():
    _, p_value = two_proportion_z_test(passed_a=8, n_a=10, passed_b=8, n_b=10)

    assert p_value == 1.0


def test_a_large_real_difference_is_significant():
    # 95/100 vs 50/100 -- an enormous, unmistakable difference.
    _, p_value = two_proportion_z_test(passed_a=95, n_a=100, passed_b=50, n_b=100)

    assert p_value < 0.001


def test_a_small_difference_on_a_small_sample_is_not_significant():
    # 6/10 vs 5/10 -- barely different, and far too small a sample to trust.
    _, p_value = two_proportion_z_test(passed_a=6, n_a=10, passed_b=5, n_b=10)

    assert p_value > 0.05


def test_all_pass_both_sides_is_not_significant():
    _, p_value = two_proportion_z_test(passed_a=10, n_a=10, passed_b=10, n_b=10)

    assert p_value == 1.0


def test_all_fail_both_sides_is_not_significant():
    _, p_value = two_proportion_z_test(passed_a=0, n_a=10, passed_b=0, n_b=10)

    assert p_value == 1.0


def test_z_score_sign_reflects_direction():
    z_a_better, _ = two_proportion_z_test(passed_a=90, n_a=100, passed_b=50, n_b=100)
    z_b_better, _ = two_proportion_z_test(passed_a=50, n_a=100, passed_b=90, n_b=100)

    assert z_a_better > 0
    assert z_b_better < 0
