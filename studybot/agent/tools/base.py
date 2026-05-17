"""Base class for tools."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, **kwargs: Any) -> Any:
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        schema = self.parameters
        if not isinstance(params, dict):
            return ["parameters must be an object"]
        errors = []
        for key in schema.get("required", []):
            if key not in params:
                errors.append(f"missing required parameter: {key}")
        return errors

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
