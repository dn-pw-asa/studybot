"""Self-evolving memory: reflection, user profiling, cross-session reuse, consolidation."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass
class Experience:
    id: str
    category: str
    content: str
    source_question: str = ""
    domain: str = ""
    confidence: float = 0.5
    created_at: str = ""
    last_accessed_at: str = ""
    access_count: int = 0


class MemoryManager:
    """Self-evolving memory: reflection, user profiling, cross-session reuse, consolidation."""

    _REFLECT_PROMPT = """You are a learning analysis system. Based on the following question, user's answer, and your evaluation, extract insights.

Question: {question}
Expected answer: {expected}
User answer: {answer}
Evaluation score: {score}/100
Feedback: {feedback}
Missing points: {missing}
User profile so far: {profile}

Return JSON only:
{{
  "experience": "one specific lesson extracted from this interaction (1-2 sentences, actionable, self-contained)",
  "category": "concept_misunderstanding|careless_error|knowledge_gap|strategy|correct_insight",
  "weak_areas": ["topic1", "topic2"],
  "strong_areas": ["topic1"],
  "error_pattern": "a recurring mistake pattern if any, or empty string"
}}"""

    def __init__(self, data_dir: str | Path, provider: Any = None) -> None:
        self.path = Path(data_dir) / "memory.json"
        self.provider = provider
        self.experiences: list[Experience] = []
        self.profile: dict = {
            "weak_areas": [], "strong_areas": [],
            "error_patterns": [], "estimated_level": "beginner",
            "total_practiced": 0, "avg_score": 0.0,
            "last_updated": datetime.now().isoformat(),
        }
        self._add_count = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text("utf-8-sig"))
            self.experiences = [Experience(**e) for e in data.get("experiences", [])]
            self.profile = data.get("profile", self.profile)
            self._add_count = len(self.experiences)
        except Exception:
            pass

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "experiences": [asdict(e) for e in self.experiences],
            "profile": self.profile,
        }, ensure_ascii=False, indent=2), "utf-8")

    async def reflect(self, question: str, expected: str, answer: str,
                      score: int, feedback: str, missing: list[str],
                      domain: str) -> None:
        if not self.provider:
            return
        profile_summary = f"level={self.profile['estimated_level']}, weak={self.profile['weak_areas']}, patterns={self.profile['error_patterns']}"
        prompt = self._REFLECT_PROMPT.format(
            question=question, expected=expected, answer=answer,
            score=score, feedback=feedback, missing=json.dumps(missing, ensure_ascii=False),
            profile=profile_summary,
        )
        try:
            resp = await self.provider.chat(
                [{"role": "user", "content": prompt}],
                model=self.provider.default_model,
                temperature=0.3,
            )
            result = json.loads((resp.content or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        except Exception:
            return

        exp = Experience(
            id=uuid.uuid4().hex[:12],
            category=result.get("category", "knowledge_gap"),
            content=result.get("experience", "").strip(),
            source_question=question[:120],
            domain=domain,
            created_at=datetime.now().isoformat(),
            last_accessed_at=datetime.now().isoformat(),
        )
        if not exp.content:
            return
        self._add_experience(exp)
        self._update_profile(result, score)
        self._save()

    def _add_experience(self, exp: Experience) -> None:
        for existing in self.experiences:
            if existing.category == exp.category and self._content_similar(existing.content, exp.content):
                existing.confidence = min(1.0, existing.confidence + 0.15)
                existing.access_count += 1
                existing.last_accessed_at = datetime.now().isoformat()
                return
        self.experiences.append(exp)
        self._add_count += 1
        if self._add_count % 10 == 0:
            self._prune_and_merge()

    @staticmethod
    def _content_similar(a: str, b: str) -> bool:
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return False
        return len(a_set & b_set) / max(len(a_set), len(b_set)) > 0.45

    def _update_profile(self, result: dict, score: int = 0) -> None:
        weak = result.get("weak_areas", [])
        strong = result.get("strong_areas", [])
        error_pattern = result.get("error_pattern", "")

        merged_weak = list(dict.fromkeys(self.profile.get("weak_areas", []) + weak))[:10]
        merged_strong = list(dict.fromkeys(self.profile.get("strong_areas", []) + strong))[:10]
        patterns = self.profile.get("error_patterns", [])
        if error_pattern and error_pattern not in patterns:
            patterns.insert(0, error_pattern)
        self.profile["weak_areas"] = merged_weak
        self.profile["strong_areas"] = merged_strong
        self.profile["error_patterns"] = patterns[:6]
        self.profile["total_practiced"] = self.profile.get("total_practiced", 0) + 1

        n = self.profile["total_practiced"]
        prev_avg = self.profile.get("avg_score", 0.0)
        score_val = float(score)
        self.profile["avg_score"] = prev_avg + (score_val - prev_avg) / n

        avg = self.profile["avg_score"]
        if avg >= 80 and len(merged_weak) <= 2:
            self.profile["estimated_level"] = "advanced"
        elif avg >= 60:
            self.profile["estimated_level"] = "intermediate"
        else:
            self.profile["estimated_level"] = "beginner"
        self.profile["last_updated"] = datetime.now().isoformat()

    def get_context(self, domain: str = "", limit: int = 4) -> str:
        scored = []
        for e in self.experiences:
            if domain and e.domain and e.domain != domain:
                continue
            score = e.confidence * (1.0 + 0.2 * e.access_count)
            scored.append((score, e))
        scored.sort(key=lambda x: -x[0])
        top = scored[:limit]

        parts = []
        if top:
            parts.append("## 过往经验")
            for _, e in top:
                parts.append(f"- [{e.category}] {e.content}")
        profile = self.profile
        if profile.get("weak_areas"):
            parts.append(f"\n## 用户画像\n薄弱领域: {', '.join(profile['weak_areas'][:5])}")
        if profile.get("strong_areas"):
            parts.append(f"擅长领域: {', '.join(profile['strong_areas'][:4])}")
        if profile.get("error_patterns"):
            parts.append(f"常见错误: {', '.join(profile['error_patterns'][:3])}")
        parts.append(f"预估水平: {profile.get('estimated_level', 'beginner')}")
        parts.append(f"总练习: {profile.get('total_practiced', 0)}次, 平均分: {profile.get('avg_score', 0):.0f}")
        return "\n".join(parts)

    def _prune_and_merge(self) -> None:
        cutoff = (datetime.now() - timedelta(days=60)).isoformat()
        self.experiences = [
            e for e in self.experiences
            if not (e.confidence < 0.2 and e.created_at < cutoff)
        ]
        merged: list[Experience] = []
        for e in sorted(self.experiences, key=lambda x: -x.confidence):
            found = False
            for m in merged:
                if m.category == e.category and self._content_similar(m.content, e.content):
                    m.confidence = max(m.confidence, e.confidence)
                    m.access_count += e.access_count
                    m.last_accessed_at = max(m.last_accessed_at, e.last_accessed_at)
                    found = True
                    break
            if not found:
                merged.append(e)
        self.experiences = merged[:50]
