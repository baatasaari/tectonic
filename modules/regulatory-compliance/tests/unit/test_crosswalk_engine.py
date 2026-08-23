async def test_seed_defaults_is_idempotent(harness):
    first = await harness.feed_manager.seed_defaults()
    second = await harness.feed_manager.seed_defaults()
    assert first > 0
    assert second == first
    mappings = await harness.repository.list_control_mappings()
    assert len(mappings) == first  # no duplicates on the second seed


async def test_map_control_returns_mappings_for_enabled_frameworks(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")

    results = await harness.crosswalk_engine.map_control("t1", "human_oversight", "human_oversight", "ref-1")

    assert any(r.framework_name == "eu_ai_act" and "Art.14" in r.clause_references for r in results)


async def test_map_control_records_implementation_event(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")

    await harness.crosswalk_engine.map_control("t1", "human_oversight", "human_oversight", "ref-1")

    events = await harness.repository.list_control_events("t1")
    assert len(events) == 1
    assert events[0].control_name == "human_oversight"
    assert events[0].source_module == "human_oversight"


async def test_map_control_ignores_disabled_frameworks(harness):
    await harness.feed_manager.seed_defaults()
    profile = await harness.enable_framework("t1", "eu_ai_act", "2024")
    harness.repository.framework_profiles[profile.id].enabled = False

    results = await harness.crosswalk_engine.map_control("t1", "human_oversight", "human_oversight", "ref-1")

    assert results == []


async def test_map_control_no_mapping_for_unknown_control(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")

    results = await harness.crosswalk_engine.map_control("t1", "some_unmapped_control", "x", "ref-1")

    assert results == []
    # the event is still recorded even though nothing maps to it yet
    events = await harness.repository.list_control_events("t1")
    assert len(events) == 1


async def test_coverage_full_when_all_controls_implemented(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")
    for control in ("human_oversight", "guardrails_policy_check", "sentinel_monitoring", "audit_logging", "workflow_confidence_gating"):
        await harness.crosswalk_engine.map_control("t1", control, "x", f"ref-{control}")

    pct, gaps = await harness.coverage_calculator.coverage("t1", "eu_ai_act")

    assert pct == 100.0
    assert gaps == []


async def test_coverage_reports_gaps_for_missing_controls(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")
    await harness.crosswalk_engine.map_control("t1", "human_oversight", "x", "ref-1")

    pct, gaps = await harness.coverage_calculator.coverage("t1", "eu_ai_act")

    assert 0.0 < pct < 100.0
    assert "audit_logging" in gaps
