"""Process-wide wiring, mirroring the other modules' app_context.py."""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from short_term_memory.config import ShortTermMemorySettings
from short_term_memory.core.buffer_manager import BufferManager


@dataclass
class AppContext:
    settings: ShortTermMemorySettings
    redis: Redis
    buffer_manager: BufferManager
