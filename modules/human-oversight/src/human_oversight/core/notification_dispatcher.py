"""Notification Dispatcher (LLD §2 sub-components): routes new requests
to the configured channel(s) per tenant, via the pluggable adapter
pattern.
"""
from __future__ import annotations

from human_oversight.core.domain import NotificationLogRecord, OversightRequestRecord
from human_oversight.core.ports import HumanOversightRepository, NotificationChannel


class NotificationDispatcher:
    def __init__(self, channels: dict[str, NotificationChannel]) -> None:
        self._channels = channels

    async def dispatch(
        self, repository: HumanOversightRepository, request: OversightRequestRecord, channel_names: list[str],
    ) -> list[NotificationLogRecord]:
        logs = []
        for name in channel_names:
            channel = self._channels.get(name)
            if channel is None:
                continue
            log = await channel.send(request)
            logs.append(await repository.create_notification_log(log))
        return logs
