from evaluation_framework.core.sampler import ProductionSampler


def test_sample_rate_zero_never_samples():
    sampler = ProductionSampler(0.0)
    assert all(not sampler.should_sample(f"interaction-{i}") for i in range(50))


def test_sample_rate_one_always_samples():
    sampler = ProductionSampler(1.0)
    assert all(sampler.should_sample(f"interaction-{i}") for i in range(50))


def test_sample_decision_deterministic_for_same_id():
    sampler = ProductionSampler(0.5)
    decision1 = sampler.should_sample("interaction-42")
    decision2 = sampler.should_sample("interaction-42")
    assert decision1 == decision2


def test_sample_rate_roughly_matches_over_many_ids():
    sampler = ProductionSampler(0.1)
    sampled = sum(1 for i in range(5000) if sampler.should_sample(f"interaction-{i}"))
    observed_rate = sampled / 5000
    assert 0.07 < observed_rate < 0.13
