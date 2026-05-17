"""OpenAI-compatible LLM provider with streaming support."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from studybot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o",
    ) -> None:
        super().__init__(api_key=api_key, api_base=api_base, default_model=default_model)
        self._client = AsyncOpenAI(api_key=api_key, base_url=api_base)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens or self.generation.max_tokens,
            "temperature": temperature if temperature is not None else self.generation.temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await self._client.chat.completions.create(**kwargs)
        return self._parse_response(resp)

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "max_tokens": max_tokens or self.generation.max_tokens,
            "temperature": temperature if temperature is not None else self.generation.temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _parse_response(self, resp: Any) -> LLMResponse:
        choice = resp.choices[0]
        content = choice.message.content
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))

        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    def update_config(self, api_key: str | None = None, api_base: str | None = None, model: str | None = None) -> None:
        if api_key is not None:
            self.api_key = api_key
        if api_base is not None:
            self.api_base = api_base
        if model is not None:
            self.default_model = model
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base)

    def get_default_model(self) -> str:
        return self.default_model
