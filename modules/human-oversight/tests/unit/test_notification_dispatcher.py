from human_oversight.core.fakes import InMemoryNotificationChannel


async def test_dispatch_sends_to_configured_channels(harness):
    channel_a = InMemoryNotificationChannel("channel-a")
    channel_b = InMemoryNotificationChannel("channel-b")
    dispatcher_channels = {"channel-a": channel_a, "channel-b": channel_b}
    from human_oversight.core.notification_dispatcher import NotificationDispatcher

    dispatcher = NotificationDispatcher(dispatcher_channels)
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )

    logs = await dispatcher.dispatch(harness.repository, request, ["channel-a", "channel-b"])

    assert len(logs) == 2
    assert len(channel_a.sent) == 1
    assert len(channel_b.sent) == 1
    assert len(harness.repository.notification_logs) == 2


async def test_dispatch_skips_unknown_channel_names(harness):
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    logs = await harness.notification_dispatcher.dispatch(harness.repository, request, ["nonexistent-channel"])
    assert logs == []


async def test_failed_delivery_recorded_as_failed(harness):
    from human_oversight.core.notification_dispatcher import NotificationDispatcher

    failing_channel = InMemoryNotificationChannel("flaky", should_fail=True)
    dispatcher = NotificationDispatcher({"flaky": failing_channel})
    request = await harness.queue_manager.enqueue(
        tenant_id="t1", requesting_module="guardrails", requesting_ref="ref-1", context={},
    )
    logs = await dispatcher.dispatch(harness.repository, request, ["flaky"])
    assert logs[0].delivery_status == "failed"
    assert logs[0].delivered_at is None
