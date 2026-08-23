from guardrails.config import RedTeamConfig


async def test_default_adversarial_prompts_all_blocked_no_bypass(harness):
    profile = harness.default_profile()
    run = await harness.red_team_runner.run("t1", profile)
    assert run.attempts_generated == harness.red_team_config.attempts_per_run
    assert run.successful_bypasses == 0
    assert harness.sentinel.alerts == []


async def test_bypassing_prompts_recorded_and_sentinel_alerted(harness_factory):
    from guardrails.core.fakes import StubLLMGatewayClient

    llm_gateway = StubLLMGatewayClient()
    llm_gateway.canned_prompts = ["completely benign text that will not be caught", "another clean-looking prompt"]
    harness = harness_factory(llm_gateway=llm_gateway, red_team_config=RedTeamConfig(attempts_per_run=2))
    profile = harness.default_profile()

    run = await harness.red_team_runner.run("t1", profile)

    assert run.attempts_generated == 2
    assert run.successful_bypasses == 2
    incidents = await harness.repository.list_bypass_incidents(run.id)
    assert len(incidents) == 2
    assert len(harness.sentinel.alerts) == 1
    assert harness.sentinel.alerts[0]["count"] == 2


async def test_run_persists_run_record(harness):
    profile = harness.default_profile()
    run = await harness.red_team_runner.run("t1", profile)
    runs = await harness.repository.list_red_team_runs("t1")
    assert any(r.id == run.id for r in runs)
