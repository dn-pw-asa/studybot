"""Practice question generation, evaluation, and file parsing."""
from __future__ import annotations

import asyncio
from typing import Any

from studybot.practice import PracticeService
from studybot.storage.db import Storage


class PracticeManager:
    """Generates practice questions & evaluates answers via LLM.
    Thin wrapper around PracticeService, keeping `current` state for WebUI.
    """

    def __init__(self, provider: Any, storage: Storage) -> None:
        self.service = PracticeService(storage, provider)
        self.current: dict | None = None
        self.history: list[dict] = []

    async def generate_question(self, bank_names: list[str] | None = None,
                                difficulties: list[str] | None = None,
                                memory_context: str = "") -> dict:
        q = await asyncio.to_thread(self.service.pick_question, bank_names, difficulties)
        if q:
            self.current = q
            return self.current
        diff_label = difficulties[0] if difficulties else "中等"
        data = await self.service.generate_question_llm(diff_label, memory_context)
        self.current = data
        return self.current

    async def evaluate_answer(self, question: str, expected_answer: str, user_answer: str,
                              memory_context: str = "") -> dict:
        return await self.service.evaluate_answer(question, expected_answer, user_answer, memory_context)

    def parse_questions_locally(self, content: str) -> list[dict] | None:
        return self.service.parse_questions_locally(content)

    async def parse_questions(self, content: str) -> list[dict]:
        return await self.service.parse_questions(content)

    async def analyze_content(self, name: str, content: str) -> dict:
        return await self.service.analyze_and_store(name, content)
