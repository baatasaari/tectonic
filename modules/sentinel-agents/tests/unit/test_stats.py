from sentinel_agents.core.stats import WelfordState, update, variance, z_score


def test_running_mean_matches_simple_average():
    state = WelfordState(mean=0.0, m2=0.0, count=0)
    for v in [2.0, 4.0, 6.0, 8.0]:
        state = update(state, v)
    assert state.mean == 5.0
    assert state.count == 4


def test_variance_matches_population_variance():
    state = WelfordState(mean=0.0, m2=0.0, count=0)
    for v in [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]:
        state = update(state, v)
    # Known population variance of this classic example set is 4.0.
    assert abs(variance(state) - 4.0) < 1e-9


def test_z_score_zero_for_value_equal_to_mean():
    state = WelfordState(mean=10.0, m2=8.0, count=4)
    assert z_score(10.0, state) == 0.0


def test_z_score_scales_with_distance_from_mean():
    state = WelfordState(mean=10.0, m2=8.0, count=4)  # variance = 2.0, std ~= 1.414
    z = z_score(14.0, state)
    assert z > 2.0


def test_z_score_infinite_when_no_variance_and_value_differs():
    state = WelfordState(mean=5.0, m2=0.0, count=10)
    assert z_score(6.0, state) == float("inf")
