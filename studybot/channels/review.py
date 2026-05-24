"""SM-2 spaced repetition review manager — Storage-backed."""
from __future__ import annotations

from typing import Any

from studybot.storage.db import Storage


class ReviewManager:
    """SM-2 spaced repetition review manager backed by shared Storage."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def get_due(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.storage.get_due_review_cards(limit)

    def rate(self, card_id: str, quality: int) -> dict[str, Any] | None:
        return self.storage.rate_review_card(card_id, quality)

    def add_card(
        self, question: str, answer: str, key_points: str, domain: str = ""
    ) -> dict[str, Any]:
        card_id = self.storage.add_review_card(
            question=question, answer=answer,
            key_points=key_points, domain_id=domain,
        )
        return self.storage.get_due_review_cards(1)[0] if self.storage.get_due_review_cards(1) else {"id": card_id}

    def stats(self) -> dict:
        return self.storage.get_review_stats()
