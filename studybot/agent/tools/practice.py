"""Smart practice question tool with multi-domain support."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from studybot.agent.tools.base import Tool
from studybot.providers.base import LLMProvider
from studybot.storage import Storage


def estimate_difficulty(content: str, knowledge_points: list[str]) -> int:
    score = 1 + len(knowledge_points) * 0.5
    if len(content) > 500:
        score += 1
    if any(w in content for w in ["证明", "推导", "prove", "derive"]):
        score += 1
    return min(5, max(1, round(score)))


def _parse_questions_from_text(text: str, bank_name: str, subject: str) -> list[dict[str, Any]]:
    questions = []
    q_pattern = re.compile(
        r"^(?:Q(?:uestion)?\.?\s*\d+[\.\)\s:：]|题目\s*\d+[\.\)\s:：]|第\s*\d+\s*题[\.\)\s:：])",
        re.IGNORECASE,
    )
    answer_pattern = re.compile(r"^(?:答案|Answer|解答)[\s:：]*", re.IGNORECASE)
    kp_pattern = re.compile(r"^(?:知识点|Knowledge\s*Points?|考点)[\s:：]*", re.IGNORECASE)

    current_q: dict[str, Any] | None = None
    current_content: list[str] = []
    current_answer: list[str] = []
    current_kps: list[str] = []
    in_answer = False

    def _flush() -> None:
        nonlocal current_q, current_content, current_answer, current_kps, in_answer
        if current_q:
            content = "\n".join(current_content).strip()
            if content:
                current_q["content"] = content
                current_q["answer"] = "\n".join(current_answer).strip()
                current_q["difficulty"] = estimate_difficulty(
                    current_q.get("content", ""), current_q.get("knowledge_points", []),
                )
                current_q["hints"] = []
                if current_kps:
                    current_q["knowledge_points"] = current_kps
                questions.append(current_q)
        current_q = None
        current_content = []
        current_answer = []
        current_kps = []
        in_answer = False

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if q_pattern.match(stripped):
            _flush()
            current_q = {"id": f"{bank_name}_q{len(questions) + 1:03d}"}
            cleaned = q_pattern.sub("", stripped).strip()
            if cleaned:
                current_content.append(cleaned)
        elif answer_pattern.match(stripped):
            in_answer = True
            cleaned = answer_pattern.sub("", stripped).strip()
            if cleaned:
                current_answer.append(cleaned)
        elif kp_pattern.match(stripped):
            cleaned = kp_pattern.sub("", stripped).strip()
            if cleaned:
                current_kps = [k.strip() for k in re.split(r"[,，;；]", cleaned) if k.strip()]
        elif current_q:
            (current_answer if in_answer else current_content).append(stripped)
    _flush()

    if not questions:
        for i, part in enumerate(re.split(r"\n\s*\n", text)):
            part = part.strip()
            if len(part) > 20:
                questions.append({
                    "id": f"{bank_name}_q{i + 1:03d}",
                    "content": part,
                    "answer": "",
                    "knowledge_points": [],
                    "difficulty": estimate_difficulty(part, []),
                    "hints": [],
                })
    return questions


_CLASSIFY_PROMPT = """You are a domain classifier for a practice question system.
Given the following questions extracted from a file, determine:
1. What domain/subject they belong to (e.g. 考公, 力扣, 考研数学, TOEFL, 执业医师, etc.)
2. Whether this matches any **existing domain** listed below
3. A concise subject category

Existing domains: {existing_domains}

Questions sample:
{sample}

Respond with valid JSON only (no markdown, no extra text):
{{
  "domain": "short domain identifier",
  "is_new": true/false,
  "subject": "subject category",
  "reasoning": "one-sentence explanation"
}}"""

_GENERATE_PROMPT = """You are configuring a practice question assistant for the domain "{domain}" ({subject}).
Based on the following questions, generate a system prompt that will guide an AI assistant.

The prompt MUST include:
- Domain name and subject area
- Typical question types and formats in this domain
- Key knowledge points or topics covered
- Evaluation criteria for answers
- Common difficulty levels

Questions:
{sample}

Output a concise system prompt (2-4 paragraphs, in the same language as the questions)."""


class PracticeQuestionsTool(Tool):
    def __init__(self, workspace: str, provider: LLMProvider | None = None) -> None:
        self._workspace = workspace
        self._provider = provider
        self._practice_dir = Path(workspace) / "practice"
        self._storage = Storage(Path(workspace) / "studybot.db")
        self._storage.connect()
        self._auto_migrate()

    def _auto_migrate(self) -> None:
        if not self._storage.has_data() and self._storage.has_json_data(self._practice_dir):
            stats = self._storage.migrate_from_json(self._practice_dir)
            if stats["questions_added"] or stats["domains"]:
                print(f"[storage] Migrated from JSON: {stats['domains']} domains, "
                      f"{stats['questions_added']} questions added, "
                      f"{stats['progress']} progress records, "
                      f"{stats['plans']} plans, {stats['sessions']} sessions")

    @property
    def name(self) -> str:
        return "practice_questions"

    @property
    def description(self) -> str:
        return (
            "Smart practice question system with multi-domain support. "
            "Each question bank (e.g. 考公, 力扣) has independent progress, "
            "difficulty level, and skill radar. "
            "Actions: upload_bank, create_plan, next_question, submit_answer, "
            "get_hint, show_progress, review_weak_topics, list_banks, "
            "set_daily_goal, all_domains_summary. "
            "For upload_bank: just provide file_path; bank_name is optional "
            "as the domain is auto-classified by LLM. Re-uploading to an "
            "existing domain merges questions with dedup."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "upload_bank", "create_plan", "next_question",
                        "submit_answer", "get_hint", "show_progress",
                        "review_weak_topics", "list_banks", "set_daily_goal",
                        "all_domains_summary",
                    ],
                    "description": "Action to perform",
                },
                "file_path": {"type": "string", "description": "Path to question bank file (required)"},
                "bank_name": {"type": "string", "description": "Optional domain hint; auto-classified by LLM if omitted"},
                "subject": {"type": "string", "description": "Optional subject hint"},
                "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                "daily_minutes": {"type": "integer", "description": "Daily study minutes"},
                "question_id": {"type": "string", "description": "Question ID"},
                "answer": {"type": "string", "description": "User's answer"},
                "is_correct": {"type": "boolean", "description": "Whether answer is correct"},
                "hint_level": {"type": "integer", "description": "Hint level 1-3"},
                "topic": {"type": "string", "description": "Knowledge topic for review"},
                "daily_goal": {"type": "integer", "description": "Daily question target"},
            },
            "required": ["action"],
        }

    async def _classify_domain(
        self, questions: list[dict[str, Any]], existing: list[str], hint: str | None = None,
    ) -> dict[str, Any]:
        if hint and hint in existing:
            return {"domain": hint, "is_new": False, "subject": "", "reasoning": "user-specified"}
        if not self._provider:
            domain = hint or f"domain_{len(existing) + 1}"
            return {"domain": domain, "is_new": domain not in existing, "subject": "General", "reasoning": "no LLM provider"}

        sample_text = "\n---\n".join(
            f"Q{i+1}: {q.get('content', '')[:300]}"
            for i, q in enumerate(questions[:8])
        )
        existing_str = ", ".join(existing) if existing else "(none)"
        prompt = _CLASSIFY_PROMPT.format(existing_domains=existing_str, sample=sample_text)

        try:
            resp = await self._provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._provider.default_model,
                temperature=0.1,
            )
            text = (resp.content or "").strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            result = json.loads(text)
            result["is_new"] = result.get("domain", "") not in existing
            return result
        except Exception:
            domain = hint or f"domain_{len(existing) + 1}"
            return {"domain": domain, "is_new": domain not in existing, "subject": "General", "reasoning": "classification failed"}

    async def _generate_domain_prompt(self, domain: str, subject: str, questions: list[dict[str, Any]]) -> str:
        if not self._provider:
            return ""
        sample_text = "\n---\n".join(
            f"Q{i+1}: {q.get('content', '')[:400]}"
            for i, q in enumerate(questions[:6])
        )
        prompt = _GENERATE_PROMPT.format(domain=domain, subject=subject, sample=sample_text)
        try:
            resp = await self._provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model=self._provider.default_model,
                temperature=0.3,
            )
            return (resp.content or "").strip()
        except Exception:
            return ""

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "")
        if action == "upload_bank":
            return await self._upload_bank(kwargs)
        sync_handlers = {
            "create_plan": lambda: self._create_plan(kwargs),
            "next_question": lambda: self._next_question(kwargs),
            "submit_answer": lambda: self._submit_answer(kwargs),
            "get_hint": lambda: self._get_hint(kwargs),
            "show_progress": lambda: self._show_progress(kwargs),
            "review_weak_topics": lambda: self._review_weak_topics(kwargs),
            "list_banks": lambda: self._list_banks(),
            "set_daily_goal": lambda: self._set_daily_goal(kwargs),
            "all_domains_summary": lambda: self._all_domains_summary(),
        }
        handler = sync_handlers.get(action)
        if not handler:
            return f"Error: Unknown action '{action}'"
        return handler()

    async def _upload_bank(self, kwargs: dict[str, Any]) -> str:
        file_path = kwargs.get("file_path")
        hint_name = kwargs.get("bank_name")
        hint_subject = kwargs.get("subject")
        if not file_path:
            return "Error: file_path is required."
        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error: Failed to read file: {e}"

        domains_list = self._storage.list_domains()
        existing_domains = [d["id"] for d in domains_list]
        questions = _parse_questions_from_text(text, hint_name or "unknown", hint_subject or "General")
        if not questions:
            return "Error: No questions parsed. Use format: Q1. ... 答案: ..."

        for q in questions:
            kps = q.get("knowledge_points", [])
            q["difficulty"] = estimate_difficulty(q.get("content", ""), kps)

        result = await self._classify_domain(questions, existing_domains, hint=hint_name)
        domain = result["domain"]
        is_new = result["is_new"]
        subject = hint_subject or result.get("subject", "General")

        self._storage.ensure_domain(domain, subject=subject)

        if is_new:
            domain_prompt = await self._generate_domain_prompt(domain, subject, questions)
            self._storage.ensure_domain(domain, subject=subject, domain_prompt=domain_prompt)

        added, replaced = self._storage.add_questions(domain, questions)
        total = self._storage.count_questions(domain)

        summary = self._storage.get_domain_summary(domain)
        dist = {}
        for d in range(1, 6):
            count = self._storage._fetchone(
                "SELECT COUNT(*) as cnt FROM questions WHERE domain_id = ? AND difficulty = ?",
                [domain, d],
            )
            if count and count["cnt"]:
                dist[d] = count["cnt"]
        dist_str = ", ".join(f"难度{d}: {c}题" for d, c in sorted(dist.items()))

        if is_new:
            lines = [
                f"✅ New domain '{domain}' created! ({subject})",
                f"Total: {total} questions",
                f"Difficulty: {dist_str}",
            ]
            if domain_prompt:
                lines.append(f"\n🧠 Generated domain prompt ({len(domain_prompt)} chars)")
            lines.append(f"\nDomain '{domain}' initialized with independent progress tracking.")
            lines.append("Next: Use create_plan to schedule, or next_question to start.")
            return "\n".join(lines)
        else:
            old_total = total - added
            return (
                f"✅ Domain '{domain}' updated!\n"
                f"Previously: {old_total} questions\n"
                f"Added: {added} new | Replaced: {replaced} (kept newer version)\n"
                f"Now: {total} questions total\n"
                f"Difficulty distribution: {dist_str}\n"
                f"Domain progress preserved. Continue practicing!"
            )

    def _create_plan(self, kwargs: dict[str, Any]) -> str:
        bank_name = kwargs.get("bank_name")
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        daily_minutes = kwargs.get("daily_minutes", 60)
        if not bank_name or not start_date or not end_date:
            return "Error: bank_name, start_date, end_date are required."
        domain = self._storage.get_domain(bank_name)
        if not domain:
            return f"Error: Bank '{bank_name}' not found."
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            return "Error: Use YYYY-MM-DD format."
        if end <= start:
            return "Error: end_date must be after start_date."
        total_days = (end - start).days + 1
        per_day = max(1, daily_minutes // 15)
        needed = total_days * per_day
        sorted_qs = self._storage.get_questions_for_plan(bank_name, limit=needed)
        schedule = []
        for i in range(total_days):
            day_qs = sorted_qs[i * per_day: (i + 1) * per_day]
            if day_qs:
                schedule.append({
                    "date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
                    "question_ids": [q["id"] for q in day_qs],
                    "target_difficulty": day_qs[0].get("difficulty", 1),
                })
        plan_id = f"plan_{bank_name}_{start_date}"
        self._storage.create_plan(
            plan_id, bank_name, start_date, end_date,
            daily_minutes, len(sorted_qs), schedule,
        )
        self._storage.update_domain_progress(bank_name, active_plan_id=plan_id)
        preview = "\n".join(
            f"  {ds['date']}: {len(ds['question_ids'])} questions (difficulty ~{ds['target_difficulty']})"
            for ds in schedule[:5]
        )
        if len(schedule) > 5:
            preview += f"\n  ... and {len(schedule) - 5} more days"
        return (
            f"📅 Study plan created!\nPlan: {plan_id}\n"
            f"Domain: {bank_name} ({len(sorted_qs)} questions)\n"
            f"Period: {start_date} to {end_date} ({total_days} days)\n"
            f"Daily: ~{per_day} questions ({daily_minutes} min)\n\n"
            f"Schedule:\n{preview}\n\n"
            f"Ready? Say '开始' or use next_question!"
        )

    def _next_question(self, kwargs: dict[str, Any]) -> str:
        bank_name = kwargs.get("bank_name")
        if not bank_name:
            return "Error: bank_name is required. Use list_banks to see available domains."
        domain = self._storage.get_domain(bank_name)
        if not domain:
            return f"Error: Bank '{bank_name}' not found."
        self._storage.reset_daily_if_new_day(bank_name)
        progress = self._storage.get_domain_progress(bank_name)
        target_diff = progress.get("current_difficulty", 1)

        selected = self._storage.get_random_question(
            bank_name, difficulty=target_diff, exclude_mastered=True,
        )
        if not selected:
            selected = self._storage.get_random_question(
                bank_name, difficulty=None, exclude_mastered=True,
            )
        if not selected:
            summary = self._storage.get_domain_summary(bank_name)
            if summary["mastered"] >= summary["total_questions"]:
                return f"🎉 All {summary['total_questions']} questions in '{bank_name}' mastered!"
            return f"No available questions in '{bank_name}'."

        q_id = selected["id"]
        kp_str = ", ".join(selected.get("knowledge_points", ["未分类"]))
        diff_stars = "★" * selected.get("difficulty", 1)
        summary = self._storage.get_domain_summary(bank_name)
        return (
            f"📝 [{bank_name}] Question (Difficulty: {diff_stars})\n"
            f"Knowledge points: {kp_str}\nID: {q_id}\n\n"
            f"{selected['content']}\n\n"
            f"Domain progress: {summary['mastered']}/{summary['total_answered']} mastered\n"
            f"Please answer. Type '提示' for hint, '跳过' to skip."
        )

    def _submit_answer(self, kwargs: dict[str, Any]) -> str:
        question_id = kwargs.get("question_id")
        answer = kwargs.get("answer", "")
        is_correct = kwargs.get("is_correct")
        if not question_id or not answer:
            return "Error: question_id and answer are required."
        bank_name = self._storage.find_bank_for_question(question_id)
        if not bank_name:
            return f"Error: Question '{question_id}' not found."
        question = self._storage.get_question(question_id)
        if not question:
            return f"Error: Question '{question_id}' not found."
        kps = question.get("knowledge_points", [])
        if is_correct is None:
            std = question.get("answer", "")
            if std:
                is_correct = self._evaluate_answer(answer, std)
            else:
                return f"Answer recorded. No standard answer. Tell me if correct (is_correct=true/false)."
        record = self._storage.record_answer(bank_name, question_id, is_correct, answer, kps)
        new_diff = self._storage.adjust_difficulty(bank_name, is_correct)
        progress = self._storage.get_domain_progress(bank_name)
        dc = progress.get("daily_completed", 0) + 1
        self._storage.update_domain_progress(bank_name, daily_completed=dc)

        if is_correct:
            attempts = record.get("attempt", 1)
            msg = f"✅ Correct!"
            if attempts > 1:
                msg += f" (After {attempts} attempts)"
            msg += f"\nDifficulty: {'★' * new_diff}"
            goal = progress.get("daily_goal", 5)
            if dc >= goal:
                msg += f"\n🎉 Daily goal reached! ({dc}/{goal})"
            else:
                msg += f"\nToday: {dc}/{goal}"
            return msg
        else:
            weak = self._storage.detect_weak_topics(bank_name)
            weak_names = [w["knowledge_point"] for w in weak]
            weak_str = f"\nWeak topics: {', '.join(weak_names)}" if weak_names else ""
            return (
                f"❌ Not correct.\n\n"
                f"Your answer: {answer}\n"
                f"Reference: {question.get('answer', 'N/A')}\n\n"
                f"Knowledge points: {', '.join(kps) or 'N/A'}\n"
                f"Attempt #{record.get('attempt', 1)}{weak_str}\n\n"
                f"Options:\n"
                f"- '提示' for hint\n"
                f"- '专题提升' for targeted practice on weak points\n"
                f"- '跳过' to move on"
            )

    @staticmethod
    def _evaluate_answer(user: str, std: str) -> bool:
        u, s = user.lower().strip(), std.lower().strip()
        if u == s or u == s.replace(" ", ""):
            return True
        if len(s) > 100:
            from difflib import SequenceMatcher
            return SequenceMatcher(None, u, s).ratio() > 0.7
        return False

    def _get_hint(self, kwargs: dict[str, Any]) -> str:
        question_id = kwargs.get("question_id")
        hint_level = kwargs.get("hint_level", 1)
        if not question_id:
            return "Error: question_id is required."
        question = self._storage.get_question(question_id)
        if not question:
            return f"Error: Question '{question_id}' not found."
        hints = question.get("hints", [])
        level = min(hint_level, 3)
        if hints and len(hints) >= level:
            return f"💡 Hint (Level {level}/3):\n{hints[level - 1]}"
        kps = question.get("knowledge_points", [])
        answer = question.get("answer", "")
        if level == 1:
            return f"💡 Hint (Level 1/3):\nThis involves: {', '.join(kps) or 'general concepts'}.\nThink about the core approach."
        elif level == 2:
            return f"💡 Hint (Level 2/3):\nKey steps: Identify main variables, break into smaller parts.\nKnowledge points: {', '.join(kps) or 'N/A'}"
        else:
            preview = answer[:200] + "..." if len(answer) > 200 else answer
            return f"💡 Hint (Level 3/3):\nSolution outline:\n{preview}\n\nTry to understand, then write full answer yourself."

    def _show_progress(self, kwargs: dict[str, Any]) -> str:
        bank_name = kwargs.get("bank_name")
        if not bank_name:
            return "Error: bank_name is required."
        domain = self._storage.get_domain(bank_name)
        if not domain:
            return f"Error: Bank '{bank_name}' not found."
        summary = self._storage.get_domain_summary(bank_name)
        progress = self._storage.get_domain_progress(bank_name)
        weak_str = "\n".join(f"  - {t}" for t in summary["weak_topics"]) if summary["weak_topics"] else "  None yet"
        skill_str = "\n".join(
            f"  - {k}: {v:.0%}" for k, v in sorted(summary["skill_radar"].items())
        ) if summary["skill_radar"] else "  Not enough data yet"
        return (
            f"📊 Progress: [{bank_name}]\n{'=' * 40}\n"
            f"Total questions: {summary['total_questions']}\n"
            f"✅ Mastered: {summary['mastered']}\n"
            f"❌ Failed: {summary['failed']}\n"
            f"📝 Answered: {summary['total_answered']}\n"
            f"⬜ Unattempted: {summary['total_questions'] - summary['total_answered']}\n"
            f"Mastery rate: {summary['mastery_rate']:.1f}%\n\n"
            f"Today: {progress.get('daily_completed', 0)}/{progress.get('daily_goal', 5)}\n"
            f"Current difficulty: {'★' * summary['current_difficulty']}\n"
            f"Streak: {summary['streak_correct']} correct\n\n"
            f"Skill radar:\n{skill_str}\n\n"
            f"Weak topics:\n{weak_str}"
        )

    def _review_weak_topics(self, kwargs: dict[str, Any]) -> str:
        bank_name = kwargs.get("bank_name")
        topic = kwargs.get("topic")
        if not bank_name:
            return "Error: bank_name is required."
        domain = self._storage.get_domain(bank_name)
        if not domain:
            return f"Error: Bank '{bank_name}' not found."
        if not topic:
            weak = self._storage.detect_weak_topics(bank_name)
            if not weak:
                return "No weak topics detected."
            names = [w["knowledge_point"] for w in weak]
            return "Weak topics:\n" + "\n".join(f"  - {t}" for t in names) + "\n\nUse review_weak_topics topic=<name>"

        progress = self._storage.get_domain_progress(bank_name)
        selected = self._storage.get_random_question(
            bank_name,
            tag=topic,
            exclude_mastered=True,
        )
        if not selected:
            selected = self._storage.get_random_question(
                bank_name, tag=topic, exclude_mastered=False,
            )
        if not selected:
            return f"No questions for topic '{topic}'."
        return (
            f"🎯 Targeted Practice: [{bank_name}] {topic}\n{'=' * 40}\n"
            f"Difficulty: {'★' * selected.get('difficulty', 1)}\n"
            f"ID: {selected['id']}\n\n"
            f"{selected['content']}\n\n"
            f"Answer to strengthen '{topic}'. Type '提示' for hints."
        )

    def _list_banks(self) -> str:
        domains = self._storage.list_domains()
        if not domains:
            return "No question banks found. Upload one first."
        lines = ["Available domains:\n"]
        for d in sorted(domains, key=lambda x: x["id"]):
            summary = self._storage.get_domain_summary(d["id"])
            lines.append(
                f"  📚 {d['id']} ({d.get('subject', 'General')})\n"
                f"     {summary['total_questions']} questions | {summary['mastered']} mastered | "
                f"Difficulty: {'★' * summary['current_difficulty']} | "
                f"Mastery: {summary['mastery_rate']:.0f}%"
            )
        return "\n".join(lines)

    def _set_daily_goal(self, kwargs: dict[str, Any]) -> str:
        bank_name = kwargs.get("bank_name")
        daily_goal = kwargs.get("daily_goal", 5)
        if not bank_name:
            return "Error: bank_name is required."
        if daily_goal <= 0:
            return "Error: daily_goal must be positive."
        self._storage.update_domain_progress(bank_name, daily_goal=daily_goal)
        return f"Daily goal for '{bank_name}' set to {daily_goal} questions."

    def _all_domains_summary(self) -> str:
        summary = self._storage.get_all_domains_summary()
        if not summary:
            return "No domains yet. Upload a question bank first."
        lines = ["📊 All Domains Summary\n" + "=" * 40]
        for name, s in summary.items():
            lines.append(
                f"\n📚 {name}:\n"
                f"  Mastered: {s['mastered']}/{s['total_answered']}\n"
                f"  Mastery rate: {s['mastery_rate']:.0f}%\n"
                f"  Difficulty: {'★' * s['current_difficulty']}\n"
                f"  Weak topics: {', '.join(s['weak_topics']) or 'None'}"
            )
        return "\n".join(lines)
