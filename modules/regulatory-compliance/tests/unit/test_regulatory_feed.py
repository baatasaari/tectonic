async def test_coverage_uses_non_deprecated_mappings_when_tenant_has_no_profile(harness):
    await harness.feed_manager.seed_defaults()
    # no framework_profile created for t1 at all
    pct, gaps = await harness.coverage_calculator.coverage("t1", "eu_ai_act")
    assert pct == 0.0
    assert "human_oversight" in gaps


async def test_publish_new_version_deprecates_prior(harness):
    await harness.feed_manager.seed_defaults()

    new_mapping = {
        "control_name": "human_oversight", "framework_name": "eu_ai_act", "framework_version": "2025",
        "clause_references": ["Art.14", "Art.14a"], "mapping_rationale": "updated for the 2025 delegated act",
    }
    await harness.feed_manager.publish([new_mapping], deprecate_prior=True)

    all_mappings = await harness.repository.list_control_mappings(control_name="human_oversight", framework_name="eu_ai_act")
    old = [m for m in all_mappings if m.framework_version == "2024"]
    new = [m for m in all_mappings if m.framework_version == "2025"]
    assert old and all(m.deprecated for m in old)
    assert new and all(not m.deprecated for m in new)


async def test_tenant_pinned_to_old_version_still_resolves_after_publish(harness):
    await harness.feed_manager.seed_defaults()
    await harness.enable_framework("t1", "eu_ai_act", "2024")

    await harness.feed_manager.publish(
        [{
            "control_name": "human_oversight", "framework_name": "eu_ai_act", "framework_version": "2025",
            "clause_references": ["Art.14a"], "mapping_rationale": "updated",
        }],
        deprecate_prior=True,
    )

    # t1 is still pinned to 2024 and unaffected by the new version's publish
    results = await harness.crosswalk_engine.map_control("t1", "human_oversight", "human_oversight", "ref-1")
    assert any(r.clause_references == ["Art.14"] for r in results)


async def test_new_tenant_enrolling_after_publish_gets_new_version(harness):
    await harness.feed_manager.seed_defaults()
    await harness.feed_manager.publish(
        [{
            "control_name": "human_oversight", "framework_name": "eu_ai_act", "framework_version": "2025",
            "clause_references": ["Art.14a"], "mapping_rationale": "updated",
        }],
        deprecate_prior=True,
    )
    await harness.enable_framework("t2", "eu_ai_act", "2025")

    results = await harness.crosswalk_engine.map_control("t2", "human_oversight", "human_oversight", "ref-1")
    assert any(r.clause_references == ["Art.14a"] for r in results)


async def test_publish_upsert_does_not_duplicate_same_version(harness):
    mapping = {
        "control_name": "human_oversight", "framework_name": "eu_ai_act", "framework_version": "2024",
        "clause_references": ["Art.14"], "mapping_rationale": "v1",
    }
    await harness.feed_manager.publish([mapping], deprecate_prior=False)
    mapping["mapping_rationale"] = "v1 updated rationale"
    await harness.feed_manager.publish([mapping], deprecate_prior=False)

    mappings = await harness.repository.list_control_mappings(control_name="human_oversight", framework_name="eu_ai_act")
    assert len(mappings) == 1
    assert mappings[0].mapping_rationale == "v1 updated rationale"
