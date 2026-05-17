"""Practice question generation, evaluation, and file parsing."""
from __future__ import annotations

import json
import random
from typing import Any


_JSON_PROMPT = "Return valid JSON only, no markdown wrapping."


class PracticeManager:
    """Generates practice questions & evaluates answers via LLM."""

    def __init__(self, provider: Any, banks: list[dict]) -> None:
        self.provider = provider
        self.banks = banks
        self.current: dict | None = None
        self.history: list[dict] = []

    async def generate_question(self, bank_names: list[str] | None = None, difficulties: list[str] | None = None,
                                memory_context: str = "") -> dict:
        bank_names = bank_names or []
        difficulties = difficulties or []
        all_questions: list[tuple[dict, str]] = []
        for b in self.banks:
            b_name = b.get("name", "")
            b_questions = b.get("questions") or b.get("_questions", [])
            if not b_questions:
                continue
            if bank_names and b_name not in bank_names:
                continue
            if difficulties:
                for q in b_questions:
                    qd = q.get("difficulty", "")
                    if not qd or qd in difficulties:
                        all_questions.append((q, b_name))
            else:
                for q in b_questions:
                    all_questions.append((q, b_name))
        if all_questions:
            q, src_bank = random.choice(all_questions)
            self.current = {
                "question": q["question"],
                "expected_answer": q.get("answer", q.get("expected_answer", "")),
                "key_points": q.get("key_points", []),
                "domain": "",
                "difficulty": difficulties[0] if difficulties else "",
                "bank_name": src_bank,
            }
            return self.current
        diff_label = difficulties[0] if difficulties else "中等"
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
        self.current = data
        self.current["domain"] = ""
        self.current["difficulty"] = diff_label
        return self.current

    async def evaluate_answer(self, question: str, expected_answer: str, user_answer: str,
                              memory_context: str = "") -> dict:
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

    def parse_questions_locally(self, content: str) -> list[dict] | None:
        """Parse structured formats (JSON/CSV) without LLM. Returns None if format unrecognized."""
        content = content.strip()
        # JSON array of questions
        if content.startswith("["):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        # JSON object with questions key
        if content.startswith("{"):
            try:
                data = json.loads(content)
                for key in ("questions", "items", "data", "results"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            except json.JSONDecodeError:
                pass
        # CSV: question|answer|key_points per line
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
        # Markdown: ## header as question, following text as answer
        if any(l.strip().startswith("##") for l in lines):
            clean = []; in_code = False
            for l in lines:
                if l.strip().startswith("```"): in_code = not in_code; continue
                if not in_code: clean.append(l)
            qs = []; cur_q = None; cur_a = []
            for l in clean:
                s = l.strip()
                m = None
                if s.startswith("### "): m = s[4:]
                elif s.startswith("## ") and not s.startswith("### "): m = s[3:]
                if m:
                    if cur_q: qs.append({"question": cur_q, "answer": "\n".join(cur_a).strip(), "key_points": []})
                    cur_q = m; cur_a = []
                elif cur_q:
                    cur_a.append(l)
            if cur_q: qs.append({"question": cur_q, "answer": "\n".join(cur_a).strip(), "key_points": []})
            if len(qs) >= 2:
                return qs
        # Bullet list: each line starting with - * or number is a question
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
        """Parse file content into structured Q&A pairs. Tries local first, falls back to LLM."""
        local = self.parse_questions_locally(content)
        if local is not None:
            return local
        chars_per_chunk = 3000
        all_questions: list[dict] = []
        for i in range(0, len(content), chars_per_chunk):
            chunk = content[i : i + chars_per_chunk]
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

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
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
            text = text[start : end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    async def analyze_content(self, name: str, content: str) -> dict:
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
        return {
            "count": len(questions),
            "domains": domains,
            "_questions": questions,
        }
