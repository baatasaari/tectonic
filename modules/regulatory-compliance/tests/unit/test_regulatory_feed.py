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

    all_mappings, _total = await harness.repository.list_control_mappings(control_name="human_oversight", framework_name="eu_ai_act")
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

    mappings, total = await harness.repository.list_control_mappings(control_name="human_oversight", framework_name="eu_ai_act")
    assert len(mappings) == 1
    assert total == 1
    assert mappings[0].mapping_rationale == "v1 updated rationale"


async def test_list_control_mappings_paginates_with_stable_order(harness):
    await harness.feed_manager.seed_defaults()

    first_page, total_1 = await harness.repository.list_control_mappings(limit=2, offset=0)
    second_page, total_2 = await harness.repository.list_control_mappings(limit=2, offset=2)

    assert total_1 == total_2
    assert total_1 > 2  # seeded default mapping table has more than 2 rows
    assert len(first_page) == 2

    # ordering (id ascending) is stable across calls/pages: no overlap, and re-fetching the
    # first page again returns the exact same rows in the exact same order.
    ids_page_1 = [m.id for m in first_page]
    ids_page_2 = [m.id for m in second_page]
    assert set(ids_page_1).isdisjoint(ids_page_2)

    repeat_first_page, _ = await harness.repository.list_control_mappings(limit=2, offset=0)
    assert [m.id for m in repeat_first_page] == ids_page_1
    assert ids_page_1 == sorted(ids_page_1)


async def test_list_control_mappings_empty_result_returns_zero_total(harness):
    mappings, total = await harness.repository.list_control_mappings(control_name="no_such_control")
    assert mappings == []
    assert total == 0
