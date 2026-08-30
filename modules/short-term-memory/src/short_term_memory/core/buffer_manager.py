"""Buffer Manager (LLD §2 sub-components, §Level 3 "Sequence: message
append triggering overflow and summarisation"). Appends messages, tracks
token count, and on overflow summarises low-salience content via LLM
Gateway while retaining high-salience items verbatim.
"""
from __future__ import annotations

from short_term_memory.config import BufferConfig, SalienceConfig
from short_term_memory.core import salience_scorer
from short_term_memory.core.domain import AppendResult, BufferState, MessageRecord
from short_term_memory.core.ports import BufferStore, LLMGatewayClient
from short_term_memory.core.tokenization import SimpleTokenCounter, TokenCounter


class BufferManager:
    def __init__(
        self,
        store: BufferStore,
        llm_gateway: LLMGatewayClient,
        buffer_config: BufferConfig,
        salience_config: SalienceConfig,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._store = store
        self._llm_gateway = llm_gateway
        self._buffer_config = buffer_config
        self._salience_config = salience_config
        self._token_counter = token_counter or SimpleTokenCounter()

    async def append(self, session_id: str, tenant_id: str, content: str, role: str) -> AppendResult:
        state = await self._store.get(session_id) or BufferState(session_id=session_id)

        salience = salience_scorer.score(content)
        token_count = self._token_counter.count(content)
        state.messages.append(MessageRecord(content=content, role=role, token_count=token_count, salience_score=salience))
        state.token_count += token_count

        overflow = state.token_count > self._buffer_config.default_token_budget
        if overflow:
            state = await self._handle_overflow(state, tenant_id)

        await self._store.save(session_id, state, self._buffer_config.session_ttl_seconds)
        return AppendResult(state=state, overflow_triggered=overflow)

    async def _handle_overflow(self, state: BufferState, tenant_id: str) -> BufferState:
        threshold = self._salience_config.retention_priority_threshold
        high = [m for m in state.messages if m.salience_score >= threshold]
        low = [m for m in state.messages if m.salience_score < threshold]

        if not low:
            # Nothing low-salience left to compress — over budget but
            # every retained item is deemed too important to drop.
            return state

        low_salience_text = "\n".join(f"{m.role}: {m.content}" for m in low)
        summary_text = await self._llm_gateway.summarise(low_salience_text, tenant_id)
        new_summary = f"{state.summary}\n{summary_text}" if state.summary else summary_text
        new_token_count = sum(m.token_count for m in high) + self._token_counter.count(new_summary)

        return BufferState(session_id=state.session_id, messages=high, summary=new_summary, token_count=new_token_count)

    async def get(self, session_id: str) -> BufferState | None:
        return await self._store.get(session_id)

    async def delete(self, session_id: str) -> bool:
        existing = await self._store.get(session_id)
        await self._store.delete(session_id)
        return existing is not None
