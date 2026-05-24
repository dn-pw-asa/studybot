"""LLM Provider base interface."""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def should_execute_tools(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass
class GenerationSettings:
    temperature: float = 0.7
    max_tokens: int = 4096


class LLMProvider(ABC):
    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "",
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.default_model = default_model
        self.generation = GenerationSettings()

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        pass

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str | dict]:
        """Stream text content token by token. Override in subclass."""
        resp = await self.chat(
            messages=messages, tools=tools, model=model,
            max_tokens=max_tokens, temperature=temperature,
        )
        if resp.content:
            yield resp.content

    async def chat_with_retry(self, **kwargs: Any) -> LLMResponse:
        last_err: Exception | None = None
        for delay in (1, 2, 4):
            try:
                return await self.chat(**kwargs)
            except Exception as e:
                last_err = e
                await asyncio.sleep(delay)
        return await self.chat(**kwargs)

    @staticmethod
    def enforce_role_alternation(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fixed: list[dict[str, Any]] = []
        for msg in messages:
            if not fixed:
                if msg["role"] == "assistant":
                    fixed.append({"role": "user", "content": msg.get("content", "")})
                    continue
                fixed.append(msg)
                continue
            if msg["role"] == fixed[-1]["role"]:
                if msg["role"] == "user":
                    fixed.append({"role": "assistant", "content": "..."})
                else:
                    fixed.append({"role": "user", "content": "..."})
            fixed.append(msg)
        return fixed
