"""Agent runner with streaming support."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from studybot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from studybot.agent.tools.registry import ToolRegistry


@dataclass
class AgentRunSpec:
    initial_messages: list[dict[str, Any]]
    tools: ToolRegistry
    model: str
    max_iterations: int = 10
    max_tool_result_chars: int = 8000


@dataclass
class AgentRunResult:
    final_content: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    stop_reason: str = "completed"


class AgentRunner:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        return await self._run_internal(spec, stream_callback=None)

    async def run_stream(
        self,
        spec: AgentRunSpec,
        stream_callback: Callable[[str, bool], Any],
    ) -> AgentRunResult:
        return await self._run_internal(spec, stream_callback=stream_callback)

    async def _run_internal(
        self,
        spec: AgentRunSpec,
        stream_callback: Callable[[str, bool], Any] | None = None,
    ) -> AgentRunResult:
        messages = list(spec.initial_messages)
        tools_used: list[str] = []

        for iteration in range(spec.max_iterations):
            messages = LLMProvider.enforce_role_alternation(messages)

            if stream_callback:
                tool_calls, full_content = await self._chat_stream_with_tools(
                    spec, messages, stream_callback,
                )
            else:
                response = await self.provider.chat_with_retry(
                    messages=messages,
                    tools=spec.tools.get_definitions(),
                    model=spec.model,
                )
                tool_calls = response.tool_calls
                full_content = response.content

            if not tool_calls:
                return AgentRunResult(
                    final_content=full_content,
                    messages=messages,
                    tools_used=tools_used,
                )

            for tc in tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }],
                })
                if stream_callback:
                    await stream_callback(f"\n\n🔧 Calling {tc.name}...", False)
                result = await spec.tools.execute(tc.name, tc.arguments)
                truncated = result[: spec.max_tool_result_chars]
                if len(result) > spec.max_tool_result_chars:
                    truncated += f"\n\n[Truncated]"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": truncated,
                })
                tools_used.append(tc.name)

        return AgentRunResult(
            final_content="Max iterations reached",
            messages=messages,
            tools_used=tools_used,
            stop_reason="max_iterations",
        )

    async def _chat_stream_with_tools(
        self,
        spec: AgentRunSpec,
        messages: list[dict[str, Any]],
        stream_callback: Callable[[str, bool], Any],
    ) -> tuple[list[Any], str | None]:
        """Stream chat response and collect tool calls + full content."""
        tool_calls: list[ToolCallRequest] = []
        full_content = ""
        accumulated_calls: dict[int, dict[str, str]] = {}

        async for delta in self.provider.chat_stream(
            messages=messages,
            tools=spec.tools.get_definitions(),
            model=spec.model,
        ):
            if isinstance(delta, dict) and "tool_calls" in delta:
                for tc in delta["tool_calls"]:
                    idx = tc.get("index", 0)
                    if idx not in accumulated_calls:
                        accumulated_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    entry = accumulated_calls[idx]
                    if "id" in tc:
                        entry["id"] = tc["id"]
                    if "function" in tc:
                        fn = tc["function"]
                        if "name" in fn:
                            entry["name"] = fn["name"]
                        if "arguments" in fn:
                            entry["arguments"] += fn["arguments"]
                continue

            if isinstance(delta, str):
                full_content += delta
                await stream_callback(delta, False)

        if accumulated_calls:
            for idx in sorted(accumulated_calls.keys()):
                entry = accumulated_calls[idx]
                try:
                    args = json.loads(entry["arguments"]) if entry["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCallRequest(
                    id=entry["id"], name=entry["name"], arguments=args,
                ))

        await stream_callback("", True)
        return tool_calls, full_content
