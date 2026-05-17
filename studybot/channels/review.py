"""SM-2 spaced repetition review manager."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any


@dataclass
class ReviewCard:
    id: str = ""
    question: str = ""
    answer: str = ""
    key_points: str = ""
    domain: str = ""
    ease_factor: float = 2.5
    interval: int = 0
    repetitions: int = 0
    next_review: str = ""
    created_at: str = ""


class ReviewManager:
    """SM-2 spaced repetition review manager."""

    def __init__(self, data_dir: str | Path) -> None:
        self.path = Path(data_dir) / "review_cards.json"
        self.cards: list[ReviewCard] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8-sig"))
                self.cards = [ReviewCard(**c) for c in data]
            except Exception:
                self.cards = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([asdict(c) for c in self.cards], ensure_ascii=False, indent=2),
            "utf-8",
        )

    def reload(self) -> None:
        self._load()

    def get_due(self, limit: int = 20) -> list[ReviewCard]:
        self.reload()
        today = date.today().isoformat()
        return [c for c in self.cards if c.next_review <= today][:limit]

    def rate(self, card_id: str, quality: int) -> ReviewCard | None:
        card = next((c for c in self.cards if c.id == card_id), None)
        if not card:
            return None
        card.ease_factor = max(
            1.3,
            card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
        )
        if quality < 3:
            card.repetitions = 0
            card.interval = 1
        else:
            if card.repetitions == 0:
                card.interval = 1
            elif card.repetitions == 1:
                card.interval = 6
            else:
                card.interval = round(card.interval * card.ease_factor)
            card.repetitions += 1
        card.next_review = (date.today() + timedelta(days=card.interval)).isoformat()
        self._save()
        return card

    def add_card(
        self, question: str, answer: str, key_points: str, domain: str = ""
    ) -> ReviewCard:
        card = ReviewCard(
            id=str(uuid.uuid4())[:8],
            question=question,
            answer=answer,
            key_points=key_points,
            domain=domain,
            next_review=date.today().isoformat(),
            created_at=date.today().isoformat(),
        )
        self.cards.append(card)
        self._save()
        return card

    def stats(self) -> dict:
        self.reload()
        today = date.today().isoformat()
        total = len(self.cards)
        due = len([c for c in self.cards if c.next_review <= today])
        return {"total": total, "due": due}
