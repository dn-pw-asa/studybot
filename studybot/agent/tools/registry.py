"""Tool registry for managing and executing tools."""
from __future__ import annotations

import json
from typing import Any

from studybot.agent.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in sorted(self._tools.values(), key=lambda x: x.name)]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        errors = tool.validate_params(params)
        if errors:
            return f"Error: Invalid parameters: {'; '.join(errors)}"
        try:
            result = await tool.execute(**params)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return f"Error executing {name}: {e}"
