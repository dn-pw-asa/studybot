"""Simplified agent loop with streaming support."""
from __future__ import annotations

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
                # Push stream delta to channel
                from studybot.channels.websocket import WebSocketChannel
                ws_channel = None
                for handler in [self.bus]:
                    pass
                # Stream via outbound with special marker
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
