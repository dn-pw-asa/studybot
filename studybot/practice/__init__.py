"""Unified practice service — single source of truth for practice operations."""
from __future__ import annotations

import json
import random
import uuid
from datetime import date
from typing import Any

from studybot.storage.db import Storage


_JSON_PROMPT = "Return valid JSON only, no markdown wrapping."


class PracticeService:
    def __init__(self, storage: Storage, provider: Any = None) -> None:
        self.storage = storage
        self.provider = provider

    # ── Question selection ──────────────────────────────────────

    def pick_question(self, bank_names: list[str] | None = None,
                      difficulties: list[str] | None = None) -> dict | None:
        bank_names = bank_names or []
        difficulties = difficulties or []
        candidates: list[dict] = []
        domains = self.storage.list_domains()
        for d in domains:
            did = d["id"]
            if bank_names and did not in bank_names:
                continue
            for q in self.storage.list_domain_questions(did):
                if difficulties:
                    diff = q["difficulty"]
                    label = "简单" if diff <= 2 else ("中等" if diff <= 4 else "困难")
                    if label not in difficulties:
                        continue
                candidates.append({
                    "question": q["content"],
                    "expected_answer": q.get("answer", ""),
                    "key_points": q.get("knowledge_points", []),
                    "domain": did,
                    "difficulty": difficulties[0] if difficulties else "",
                    "bank_name": did,
                })
        return random.choice(candidates) if candidates else None

    # ── LLM operations ──────────────────────────────────────────

    async def generate_question_llm(self, diff_label: str = "中等",
                                    memory_context: str = "") -> dict:
        weak_hint = ""
        if memory_context:
            weak_hint = "\nTarget the user's weak areas if possible:\n" + memory_context[:500]
        prompt = (
            f"{_JSON_PROMPT}\n"
            f"Generate ONE {diff_label} practice question. Format:\n"
            '{"question":"...","expected_answer":"...","key_points":["...","..."]}'
            f"{weak_hint}"
        )
        resp = await self.provider.chat(
            [{"role": "user", "content": prompt}],
            model=self.provider.default_model,
        )
        data = self._parse_json(resp.content or "")
        data["domain"] = ""
        data["difficulty"] = diff_label
        return data

    async def evaluate_answer(self, question: str, expected_answer: str,
                              user_answer: str, memory_context: str = "") -> dict:
        has_answer = bool(expected_answer and expected_answer.strip())
        prompt = (
            f"{_JSON_PROMPT}\n"
            "Evaluate the user's answer. Return:\n"
            '{"score":0-100,"correct":true/false,"feedback":"...","missing_points":["...","..."]}\n\n'
            f"Question: {question}\n"
        )
        if has_answer:
            prompt += f"Expected answer: {expected_answer}\n"
        else:
            prompt += "(No reference answer provided; evaluate based on question correctness.)\n"
        prompt += f"User answer: {user_answer}"
        if memory_context:
            prompt += f"\n\nRelevant context:\n{memory_context}"
        resp = await self.provider.chat(
            [{"role": "user", "content": prompt}],
            model=self.provider.default_model,
        )
        return self._parse_json(resp.content or "")

    @staticmethod
    def simple_evaluate(user: str, std: str) -> bool:
        u, s = user.lower().strip(), std.lower().strip()
        if u == s or u == s.replace(" ", ""):
            return True
        if len(s) > 100:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, u, s).ratio() > 0.7
        return False

    # ── Answer recording & progress ─────────────────────────────

    def record_and_progress(self, domain_id: str, question: dict,
                            is_correct: bool, answer_text: str) -> dict:
        qid = question.get("id", "") or f"webui_{uuid.uuid4().hex[:12]}"
        kps = question.get("key_points", question.get("knowledge_points", []))
        record = self.storage.record_answer(domain_id, qid, is_correct, answer_text, kps)
        new_diff = self.storage.adjust_difficulty(domain_id, is_correct)
        progress = self.storage.get_domain_progress(domain_id)
        dc = progress.get("daily_completed", 0) + 1
        self.storage.update_domain_progress(
            domain_id,
            daily_completed=dc,
            last_practice_date=date.today().isoformat(),
        )
        return {"record": record, "new_difficulty": new_diff, "daily_completed": dc}

    # ── File parsing ────────────────────────────────────────────

    def parse_questions_locally(self, content: str) -> list[dict] | None:
        content = content.strip()
        if content.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        if content.startswith("{"):
            try:
                data = json.loads(content)
                for key in ("questions", "items", "data", "results"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            except json.JSONDecodeError:
                pass
        lines = content.split("\n")
        if len(lines) > 1 and ("question" in lines[0].lower() or "|" in content or "\t" in content):
            sep = "\t" if "\t" in content else ("|" if "|" in content else ",")
            header = [h.strip().lower() for h in lines[0].split(sep)]
            q_idx = next((i for i, h in enumerate(header) if h in ("question", "题目", "题")), -1)
            a_idx = next((i for i, h in enumerate(header) if h in ("answer", "答案", "答")), -1)
            if q_idx >= 0:
                result = []
                for line in lines[1:]:
                    parts = line.split(sep)
                    if len(parts) <= q_idx:
                        continue
                    result.append({
                        "question": parts[q_idx].strip() if q_idx < len(parts) else "",
                        "answer": parts[a_idx].strip() if a_idx >= 0 and a_idx < len(parts) else "",
                        "key_points": [],
                    })
                if result:
                    return result
        if any(l.strip().startswith("##") for l in lines):
            clean = []; in_code = False
            for l in lines:
                if l.strip().startswith("```"):
                    in_code = not in_code; continue
                if not in_code:
                    clean.append(l)
            qs = []; cur_q = None; cur_a = []
            for l in clean:
                s = l.strip()
                m = None
                if s.startswith("### "):
                    m = s[4:]
                elif s.startswith("## ") and not s.startswith("### "):
                    m = s[3:]
                if m:
                    if cur_q:
                        qs.append({"question": cur_q, "answer": "\n".join(cur_a).strip(), "key_points": []})
                    cur_q = m; cur_a = []
                elif cur_q:
                    cur_a.append(l)
            if cur_q:
                qs.append({"question": cur_q, "answer": "\n".join(cur_a).strip(), "key_points": []})
            if len(qs) >= 2:
                return qs
        questions = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped[0] in ("-", "*", "•") or (
                stripped[0].isdigit() and len(stripped) > 2 and stripped[1] in (".", "、", ")")
            ):
                text = stripped[2:].strip() if stripped[0] in ("-", "*", "•") else stripped[2:].strip()
                if text:
                    questions.append({"question": text, "answer": "", "key_points": []})
        if len(questions) >= 3:
            return questions
        return None

    async def parse_questions(self, content: str) -> list[dict]:
        local = self.parse_questions_locally(content)
        if local is not None:
            return local
        if not self.provider:
            return []
        chars_per_chunk = 3000
        all_questions: list[dict] = []
        for i in range(0, len(content), chars_per_chunk):
            chunk = content[i: i + chars_per_chunk]
            prompt = (
                f"{_JSON_PROMPT}\n"
                "Extract ALL practice questions from the following study material.\n"
                "Return a JSON array of objects with keys: question, answer, key_points (array of strings).\n"
                "IMPORTANT: Only extract answers that are explicitly present in the source text. "
                "If the material does not contain an answer for a question, set answer to empty string.\n"
                "If none found, return [].\n\n"
                f"Material (chunk {i // chars_per_chunk + 1}):\n{chunk}"
            )
            try:
                resp = await self.provider.chat(
                    [{"role": "user", "content": prompt}],
                    model=self.provider.default_model,
                )
                parsed = self._parse_json_list(resp.content or "")
                if parsed:
                    all_questions.extend(parsed)
            except Exception:
                continue
        return all_questions

    async def analyze_and_store(self, name: str, content: str) -> dict:
        questions = await self.parse_questions(content)
        domains: list[str] = []
        if questions:
            sample = json.dumps(questions[:3], ensure_ascii=False)
            prompt = (
                f"{_JSON_PROMPT}\n"
                "Detect domains/categories for these questions.\n"
                'Return: {"domains":["domain1","domain2"]}\n\n'
                f"Questions:\n{sample}"
            )
            try:
                resp = await self.provider.chat(
                    [{"role": "user", "content": prompt}],
                    model=self.provider.default_model,
                )
                info = self._parse_json(resp.content or "")
                domains = info.get("domains", [])
            except Exception:
                pass
            if not domains:
                domains = ["综合"]
            domain = domains[0]
            self.storage.ensure_domain(domain, subject=name)
            mapped = []
            for q in questions:
                mapped.append({
                    "content": q.get("question", q.get("content", "")),
                    "answer": q.get("answer", q.get("expected_answer", "")),
                    "knowledge_points": q.get("key_points", q.get("knowledge_points", [])),
                    "difficulty": 3,
                })
            self.storage.add_questions(domain, mapped)
        return {"count": len(questions), "domains": domains, "_questions": questions}

    # ── JSON helpers ────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start: end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"question": text, "expected_answer": "", "key_points": []}

    @staticmethod
    def _parse_json_list(text: str) -> list[dict]:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            text = text[start: end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
