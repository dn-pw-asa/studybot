"""Simplified agent loop with streaming support."""
from __future__ import annotations

import json

from studybot.agent.runner import AgentRunner, AgentRunSpec
from studybot.agent.tools.registry import ToolRegistry
from studybot.bus import InboundMessage, MessageBus, OutboundMessage
from studybot.providers.base import LLMProvider
from studybot.session import SessionManager


SYSTEM_PROMPT = """You are a smart practice question assistant. Help users learn by:
1. Parsing uploaded question banks
2. Creating study plans
3. Recommending questions with increasing difficulty
4. Evaluating answers and detecting weak knowledge points
5. Providing targeted review on weak topics
6. Looping until mastery

Use the practice_questions tool for all state management.
Always be encouraging. Show one question at a time.
Never give the full answer unless the user asks after 3+ failed attempts.

Support multiple domains. Each domain has independent progress.
When user switches domains, show them their current status in that domain."""


class PracticeAgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        session_manager: SessionManager,
        bus: MessageBus,
        model: str,
        max_iterations: int = 10,
    ) -> None:
        self.provider = provider
        self.runner = AgentRunner(provider)
        self.tools = tools
        self.sessions = session_manager
        self.bus = bus
        self.model = model
        self.max_iterations = max_iterations

    async def run(self) -> None:
        while True:
            msg = await self.bus.consume_inbound()
            try:
                result = await self.process(msg)
                await self.bus.publish_outbound(result)
            except Exception as e:
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=f"Error: {e}",
                ))

    async def process(self, msg: InboundMessage) -> OutboundMessage:
        session_key = f"{msg.channel}:{msg.chat_id}"
        session = self.sessions.get_or_create(session_key)

        if not any(m.get("role") == "system" for m in session.messages):
            session.add_message("system", SYSTEM_PROMPT)

        session.add_message("user", msg.content)

        # Async context compression: summarize old messages when history grows too large
        if len(session.messages) > 55:
            summary_text = await self._compress_history(session)
            if summary_text:
                # Keep original system prompt (not summary)
                keep = []
                for m in session.messages:
                    if m.get("role") == "system" and "历史摘要" not in m.get("content", ""):
                        keep.append(m)
                        break
                # Recent messages (exclude old summaries)
                recent = [m for m in session.messages[-15:] if "历史摘要" not in m.get("content", "")]
                session.messages = keep + [
                    {"role": "system", "content": f"## 历史摘要\n{summary_text[:800]}", "timestamp": 0}
                ] + recent[-10:]

        history = session.get_history(max_messages=50)

        spec = AgentRunSpec(
            initial_messages=history,
            tools=self.tools,
            model=self.provider.default_model,
            max_iterations=self.max_iterations,
        )

        # Collect streamed content
        streamed_content = []

        async def stream_callback(text: str, done: bool) -> None:
            if text:
                streamed_content.append(text)
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=text,
                metadata={"stream": True, "done": done},
            ))

        result = await self.runner.run_stream(spec, stream_callback)

        full_response = "".join(streamed_content) or result.final_content or ""
        session.add_message("assistant", full_response)
        self.sessions.save(session)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=full_response,
        )

    async def _compress_history(self, session) -> str:
        """Async compression: summarize old messages via LLM."""
        recent_raw = "\n".join(
            m.get("content", "")[:300] for m in session.messages[-30:-5]
            if m.get("role") in ("user", "assistant")
        )
        if not recent_raw.strip():
            return ""
        prompt = (
            f"将以下对话历史压缩为3-5句摘要, 涵盖: 讨论主题、用户水平、常见错误、进度.\n\n"
            f"{recent_raw[:3000]}"
        )
        try:
            resp = await self.provider.chat(
                [{"role": "user", "content": prompt}],
                model=self.provider.default_model,
                temperature=0.2,
            )
            return (resp.content or "")[:1200]
        except Exception:
            return ""
