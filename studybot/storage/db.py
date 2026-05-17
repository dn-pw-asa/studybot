"""SQLite storage layer for studybot.

Schema covers: domains, questions, tags, answer_records, progress,
skill_radar, review_cards, sessions, study_plans.

All methods are synchronous. Use with run_in_executor in async code
for heavy batch operations if needed; single-row queries are fast
enough to call directly (<1ms).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS domains (
    id              TEXT PRIMARY KEY,
    subject         TEXT DEFAULT '',
    domain_prompt   TEXT DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS questions (
    id              TEXT PRIMARY KEY,
    domain_id       TEXT NOT NULL REFERENCES domains(id),
    content         TEXT NOT NULL,
    answer          TEXT DEFAULT '',
    difficulty      INTEGER DEFAULT 1 CHECK(difficulty BETWEEN 1 AND 5),
    content_hash    TEXT NOT NULL,
    hints           TEXT DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_q_domain  ON questions(domain_id);
CREATE INDEX IF NOT EXISTS idx_q_diff    ON questions(difficulty);
CREATE UNIQUE INDEX IF NOT EXISTS idx_q_hash ON questions(content_hash);

CREATE TABLE IF NOT EXISTS question_tags (
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (question_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_tag_tag ON question_tags(tag);

CREATE TABLE IF NOT EXISTS answer_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL REFERENCES questions(id),
    domain_id   TEXT NOT NULL REFERENCES domains(id),
    is_correct  INTEGER NOT NULL,
    answer_text TEXT DEFAULT '',
    attempt     INTEGER DEFAULT 1,
    answered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ar_q  ON answer_records(question_id);
CREATE INDEX IF NOT EXISTS idx_ar_d  ON answer_records(domain_id);
CREATE INDEX IF NOT EXISTS idx_ar_at ON answer_records(answered_at);

CREATE TABLE IF NOT EXISTS domain_progress (
    domain_id           TEXT PRIMARY KEY REFERENCES domains(id),
    current_difficulty  INTEGER DEFAULT 1 CHECK(current_difficulty BETWEEN 1 AND 5),
    streak_correct      INTEGER DEFAULT 0,
    daily_completed     INTEGER DEFAULT 0,
    daily_goal          INTEGER DEFAULT 5,
    last_practice_date  TEXT DEFAULT '',
    total_practice_min  INTEGER DEFAULT 0,
    first_practice_date TEXT DEFAULT '',
    active_plan_id      TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS skill_radar (
    domain_id       TEXT NOT NULL REFERENCES domains(id),
    knowledge_point TEXT NOT NULL,
    mastery         REAL DEFAULT 0.5 CHECK(mastery BETWEEN 0.0 AND 1.0),
    total_count     INTEGER DEFAULT 0,
    fail_count      INTEGER DEFAULT 0,
    PRIMARY KEY (domain_id, knowledge_point)
);
CREATE INDEX IF NOT EXISTS idx_sr_domain ON skill_radar(domain_id);

CREATE TABLE IF NOT EXISTS review_cards (
    id          TEXT PRIMARY KEY,
    domain_id   TEXT REFERENCES domains(id),
    question_id TEXT REFERENCES questions(id),
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL,
    key_points  TEXT DEFAULT '',
    ease_factor REAL DEFAULT 2.5,
    interval    INTEGER DEFAULT 0,
    repetitions INTEGER DEFAULT 0,
    next_review TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rc_due ON review_cards(next_review);

CREATE TABLE IF NOT EXISTS study_plans (
    id              TEXT PRIMARY KEY,
    domain_id       TEXT NOT NULL REFERENCES domains(id),
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    daily_minutes   INTEGER DEFAULT 60,
    total_questions INTEGER DEFAULT 0,
    schedule        TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    key         TEXT PRIMARY KEY,
    messages    TEXT NOT NULL,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    metadata    TEXT DEFAULT '{}'
);
"""


def _content_hash(text: str) -> str:
    return hashlib.md5(re.sub(r"\s+", "", text).encode()).hexdigest()


def _now() -> str:
    return datetime.now().isoformat()


def _today() -> str:
    return date.today().isoformat()


class Storage:
    """High-level data access layer backed by SQLite.

    Usage:
        storage = Storage("~/.studybot/workspace/data.db")
        storage.connect()
        storage.ensure_domain("考公", subject="行测")
        storage.add_questions("考公", parsed_questions)
        q = storage.get_random_question("考公", difficulty=3)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    # ── Connection ──────────────────────────────────────────────

    def connect(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA_SQL)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def _fetchone(self, sql: str, params: list[Any] | None = None) -> sqlite3.Row | None:
        return self.conn.execute(sql, params or []).fetchone()

    def _fetchall(self, sql: str, params: list[Any] | None = None) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params or []).fetchall()

    def _execute(self, sql: str, params: list[Any] | None = None) -> sqlite3.Cursor:
        return self.conn.execute(sql, params or [])

    # ── Row → dict helpers ─────────────────────────────────────

    @staticmethod
    def _row2dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return dict(row)

    @staticmethod
    def _question_from_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        kp_raw = d.pop("knowledge_points", None)
        d["knowledge_points"] = kp_raw.split("||") if kp_raw else []
        if isinstance(d.get("hints"), str):
            try:
                d["hints"] = json.loads(d["hints"])
            except (json.JSONDecodeError, TypeError):
                d["hints"] = []
        return d

    # ── Domain ─────────────────────────────────────────────────

    def ensure_domain(self, domain_id: str, subject: str = "",
                      domain_prompt: str = "") -> str:
        existing = self._fetchone(
            "SELECT id FROM domains WHERE id = ?", [domain_id]
        )
        if existing:
            if subject or domain_prompt:
                updates: list[str] = []
                params: list[Any] = []
                if subject:
                    updates.append("subject = ?")
                    params.append(subject)
                if domain_prompt:
                    updates.append("domain_prompt = ?")
                    params.append(domain_prompt)
                self._execute(
                    f"UPDATE domains SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
                    [*params, _now(), domain_id],
                )
            return domain_id
        self._execute(
            "INSERT INTO domains (id, subject, domain_prompt, created_at) VALUES (?, ?, ?, ?)",
            [domain_id, subject, domain_prompt, _now()],
        )
        self._execute(
            "INSERT OR IGNORE INTO domain_progress (domain_id) VALUES (?)",
            [domain_id],
        )
        return domain_id

    def get_domain(self, domain_id: str) -> dict[str, Any] | None:
        return self._row2dict(
            self._fetchone("SELECT * FROM domains WHERE id = ?", [domain_id])
        )

    def list_domains(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT d.*, COUNT(q.id) as question_count "
            "FROM domains d LEFT JOIN questions q ON q.domain_id = d.id "
            "GROUP BY d.id ORDER BY d.id"
        )
        return [dict(r) for r in rows]

    # ── Questions ───────────────────────────────────────────────

    def add_questions(
        self, domain_id: str, questions: list[dict[str, Any]]
    ) -> tuple[int, int]:
        """Batch insert with content-hash dedup. Returns (added, replaced)."""
        added = replaced = 0
        now = _now()
        for q in questions:
            content = q.get("content", "")
            h = _content_hash(content)
            existing = self._fetchone(
                "SELECT id FROM questions WHERE content_hash = ? AND domain_id = ?",
                [h, domain_id],
            )
            kps = q.get("knowledge_points", [])
            hints = q.get("hints", [])
            diff = q.get("difficulty", 1)

            if existing:
                qid = existing["id"]
                self._execute(
                    "UPDATE questions SET answer=?, difficulty=?, hints=?, "
                    "updated_at=? WHERE id=?",
                    [q.get("answer", ""), diff, json.dumps(hints, ensure_ascii=False),
                     now, qid],
                )
                self._execute("DELETE FROM question_tags WHERE question_id = ?", [qid])
                replaced += 1
            else:
                qid = q.get("id", "")
                if not qid:
                    max_id = self._fetchone(
                        "SELECT id FROM questions WHERE domain_id = ? ORDER BY id DESC LIMIT 1",
                        [domain_id],
                    )
                    if max_id:
                        m = re.search(r"_q(\d+)$", max_id["id"])
                        seq = (int(m.group(1)) + 1) if m else 1
                    else:
                        seq = 1
                    qid = f"{domain_id}_q{seq:03d}"
                self._execute(
                    "INSERT INTO questions (id, domain_id, content, answer, difficulty, "
                    "content_hash, hints, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [qid, domain_id, content, q.get("answer", ""), diff, h,
                     json.dumps(hints, ensure_ascii=False), now],
                )
                added += 1

            for kp in (kps if isinstance(kps, list) else []):
                kp = kp.strip()
                if kp:
                    self._execute(
                        "INSERT OR IGNORE INTO question_tags (question_id, tag) VALUES (?, ?)",
                        [qid, kp],
                    )

        self._execute(
            "UPDATE domains SET updated_at = ? WHERE id = ?", [now, domain_id],
        )
        return added, replaced

    def get_question(self, question_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT q.*, GROUP_CONCAT(t.tag, '||') as knowledge_points "
            "FROM questions q LEFT JOIN question_tags t ON t.question_id = q.id "
            "WHERE q.id = ? GROUP BY q.id",
            [question_id],
        )
        return self._question_from_row(row) if row else None

    def get_question_by_hash(self, content_hash: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT q.*, GROUP_CONCAT(t.tag, '||') as knowledge_points "
            "FROM questions q LEFT JOIN question_tags t ON t.question_id = q.id "
            "WHERE q.content_hash = ? GROUP BY q.id",
            [content_hash],
        )
        return self._question_from_row(row) if row else None

    def count_questions(self, domain_id: str) -> int:
        row = self._fetchone(
            "SELECT COUNT(*) as cnt FROM questions WHERE domain_id = ?", [domain_id]
        )
        return row["cnt"] if row else 0

    def update_question_hints(self, question_id: str, hints: list[str]) -> None:
        self._execute(
            "UPDATE questions SET hints = ? WHERE id = ?",
            [json.dumps(hints, ensure_ascii=False), question_id],
        )

    def find_bank_for_question(self, question_id: str) -> str | None:
        row = self._fetchone(
            "SELECT domain_id FROM questions WHERE id = ?", [question_id]
        )
        return row["domain_id"] if row else None

    # ── Random question selection ───────────────────────────────

    def get_random_question(
        self,
        domain_id: str,
        *,
        difficulty: int | None = None,
        exclude_mastered: bool = True,
        tag: str | None = None,
        exclude_ids: set[str] | None = None,
    ) -> dict[str, Any] | None:
        """Pick a random question matching criteria. Returns None if none found."""
        conditions = ["q.domain_id = ?"]
        params: list[Any] = [domain_id]

        if difficulty is not None:
            conditions.append("q.difficulty = ?")
            params.append(difficulty)

        if exclude_mastered:
            conditions.append(
                "q.id NOT IN ("
                "SELECT question_id FROM answer_records "
                "WHERE is_correct = 1 "
                "GROUP BY question_id "
                "HAVING COUNT(*) >= 2"
                ")"
            )

        if tag:
            conditions.append(
                "q.id IN (SELECT question_id FROM question_tags WHERE tag = ?)"
            )
            params.append(tag)

        if exclude_ids:
            placeholders = ",".join("?" for _ in exclude_ids)
            conditions.append(f"q.id NOT IN ({placeholders})")
            params.extend(exclude_ids)

        sql = (
            "SELECT q.*, GROUP_CONCAT(t.tag, '||') as knowledge_points "
            "FROM questions q "
            "LEFT JOIN question_tags t ON t.question_id = q.id "
            f"WHERE {' AND '.join(conditions)} "
            "GROUP BY q.id "
            "ORDER BY RANDOM() LIMIT 1"
        )
        row = self._fetchone(sql, params)
        if row:
            return self._question_from_row(row)

        if difficulty is not None:
            return self.get_random_question(
                domain_id, difficulty=None,
                exclude_mastered=exclude_mastered,
                tag=tag, exclude_ids=exclude_ids,
            )
        return None

    def get_questions_for_plan(
        self, domain_id: str, limit: int, offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT q.*, GROUP_CONCAT(t.tag, '||') as knowledge_points "
            "FROM questions q LEFT JOIN question_tags t ON t.question_id = q.id "
            "WHERE q.domain_id = ? "
            "GROUP BY q.id ORDER BY q.difficulty ASC LIMIT ? OFFSET ?",
            [domain_id, limit, offset],
        )
        return [self._question_from_row(r) for r in rows]

    def search_questions(
        self, domain_id: str, *, tag: str | None = None,
        difficulty: int | None = None, limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = ["q.domain_id = ?"]
        params: list[Any] = [domain_id]
        count_params: list[Any] = [domain_id]

        if tag:
            conditions.append(
                "q.id IN (SELECT question_id FROM question_tags WHERE tag = ?)"
            )
            params.append(tag)
            count_params.append(tag)

        if difficulty is not None:
            conditions.append("q.difficulty = ?")
            params.append(difficulty)
            count_params.append(difficulty)

        where = " AND ".join(conditions)

        count_row = self._fetchone(
            f"SELECT COUNT(DISTINCT q.id) as cnt FROM questions q "
            f"LEFT JOIN question_tags t ON t.question_id = q.id "
            f"WHERE {where}",
            count_params,
        )
        total = count_row["cnt"] if count_row else 0

        rows = self._fetchall(
            f"SELECT q.*, GROUP_CONCAT(t.tag, '||') as knowledge_points "
            f"FROM questions q LEFT JOIN question_tags t ON t.question_id = q.id "
            f"WHERE {where} "
            f"GROUP BY q.id ORDER BY q.id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return [self._question_from_row(r) for r in rows], total

    # ── Answer recording & progress ────────────────────────────

    def record_answer(
        self, domain_id: str, question_id: str, is_correct: bool,
        answer_text: str = "", knowledge_points: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record an answer attempt and update skill_radar. Returns answer record."""
        attempt_row = self._fetchone(
            "SELECT COUNT(*) as cnt FROM answer_records "
            "WHERE question_id = ?",
            [question_id],
        )
        attempt_num = (attempt_row["cnt"] + 1) if attempt_row else 1

        self._execute(
            "INSERT INTO answer_records (question_id, domain_id, is_correct, "
            "answer_text, attempt, answered_at) VALUES (?, ?, ?, ?, ?, ?)",
            [question_id, domain_id, 1 if is_correct else 0,
             answer_text, attempt_num, _now()],
        )

        for kp in (knowledge_points or []):
            kp = kp.strip()
            if not kp:
                continue
            row = self._fetchone(
                "SELECT mastery, total_count, fail_count FROM skill_radar "
                "WHERE domain_id = ? AND knowledge_point = ?",
                [domain_id, kp],
            )
            if row:
                mastery = row["mastery"]
                tc = row["total_count"] + 1
                fc = row["fail_count"] + (0 if is_correct else 1)
                new_mastery = min(1.0, mastery + 0.1) if is_correct else max(0.0, mastery - 0.15)
                self._execute(
                    "UPDATE skill_radar SET mastery = ?, total_count = ?, "
                    "fail_count = ? WHERE domain_id = ? AND knowledge_point = ?",
                    [new_mastery, tc, fc, domain_id, kp],
                )
            else:
                self._execute(
                    "INSERT INTO skill_radar (domain_id, knowledge_point, mastery, "
                    "total_count, fail_count) VALUES (?, ?, ?, ?, ?)",
                    [domain_id, kp,
                     0.6 if is_correct else 0.35,
                     1, 0 if is_correct else 1],
                )

        return {
            "attempt": attempt_num,
            "is_correct": is_correct,
            "answered_at": _now(),
        }

    def get_question_status(self, question_id: str) -> dict[str, Any]:
        """Return (attempts, is_correct, status) for a question."""
        rows = self._fetchall(
            "SELECT is_correct FROM answer_records WHERE question_id = ? ORDER BY attempt",
            [question_id],
        )
        if not rows:
            return {"attempts": 0, "is_correct": None, "status": "unattempted"}
        recent_correct = sum(1 for r in rows if r["is_correct"])
        total = len(rows)
        return {
            "attempts": total,
            "is_correct": rows[-1]["is_correct"],
            "status": "mastered" if recent_correct >= 2 else
                      ("failed" if not rows[-1]["is_correct"] else "attempted"),
        }

    def get_domain_progress(self, domain_id: str) -> dict[str, Any]:
        row = self._fetchone(
            "SELECT * FROM domain_progress WHERE domain_id = ?", [domain_id],
        )
        if row:
            return dict(row)
        self._execute(
            "INSERT OR IGNORE INTO domain_progress (domain_id) VALUES (?)",
            [domain_id],
        )
        self.conn.commit()
        row = self._fetchone(
            "SELECT * FROM domain_progress WHERE domain_id = ?", [domain_id],
        )
        return dict(row) if row else {}

    def update_domain_progress(self, domain_id: str, **kwargs: Any) -> None:
        allowed = {
            "current_difficulty", "streak_correct", "daily_completed",
            "daily_goal", "last_practice_date", "total_practice_min",
            "first_practice_date", "active_plan_id",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        params: list[Any] = list(updates.values())
        params.append(domain_id)
        self._execute(
            f"UPDATE domain_progress SET {sets} WHERE domain_id = ?",
            params,
        )

    def detect_weak_topics(
        self, domain_id: str, threshold: float = 0.5, min_attempts: int = 2,
    ) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT knowledge_point, total_count, fail_count, mastery "
            "FROM skill_radar "
            "WHERE domain_id = ? AND total_count >= ? "
            "AND (CAST(fail_count AS REAL) / total_count) > ? "
            "ORDER BY (CAST(fail_count AS REAL) / total_count) DESC",
            [domain_id, min_attempts, threshold],
        )
        return [dict(r) for r in rows]

    def get_skill_radar(self, domain_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM skill_radar WHERE domain_id = ? ORDER BY knowledge_point",
            [domain_id],
        )
        return [dict(r) for r in rows]

    def get_domain_summary(self, domain_id: str) -> dict[str, Any]:
        total_q = self.count_questions(domain_id)
        answer_rows = self._fetchall(
            "SELECT q.id, ar.is_correct, ar.attempt FROM answer_records ar "
            "JOIN questions q ON q.id = ar.question_id "
            "WHERE q.domain_id = ?",
            [domain_id],
        )
        per_question: dict[str, list[bool]] = {}
        for r in answer_rows:
            per_question.setdefault(r["id"], []).append(bool(r["is_correct"]))
        total_answered = len(per_question)
        mastered = sum(1 for v in per_question.values() if sum(v) >= 2)
        failed = sum(
            1 for v in per_question.values()
            if v and not v[-1]
        )
        progress = self.get_domain_progress(domain_id)
        weak = self.detect_weak_topics(domain_id)
        radar = self.get_skill_radar(domain_id)

        return {
            "total_questions": total_q,
            "total_answered": total_answered,
            "mastered": mastered,
            "failed": failed,
            "mastery_rate": mastered / total_answered * 100 if total_answered > 0 else 0,
            "current_difficulty": progress.get("current_difficulty", 1),
            "streak_correct": progress.get("streak_correct", 0),
            "daily_completed": progress.get("daily_completed", 0),
            "daily_goal": progress.get("daily_goal", 5),
            "weak_topics": [w["knowledge_point"] for w in weak],
            "skill_radar": {r["knowledge_point"]: r["mastery"] for r in radar},
        }

    def get_all_domains_summary(self) -> dict[str, dict[str, Any]]:
        domains = self.list_domains()
        result = {}
        for d in domains:
            result[d["id"]] = self.get_domain_summary(d["id"])
        return result

    def adjust_difficulty(self, domain_id: str, is_correct: bool) -> int:
        progress = self.get_domain_progress(domain_id)
        streak = progress.get("streak_correct", 0)
        diff = progress.get("current_difficulty", 1)
        if is_correct:
            streak += 1
            if streak >= 3:
                diff = min(5, diff + 1)
                streak = 0
        else:
            streak = 0
            diff = max(1, diff - 1)
        self.update_domain_progress(
            domain_id,
            current_difficulty=diff,
            streak_correct=streak,
        )
        return diff

    def reset_daily_if_new_day(self, domain_id: str) -> bool:
        progress = self.get_domain_progress(domain_id)
        today = _today()
        if progress.get("last_practice_date") != today:
            self.update_domain_progress(
                domain_id, daily_completed=0, last_practice_date=today,
            )
            return True
        return False

    # ── Review cards (SM-2) ────────────────────────────────────

    def add_review_card(
        self, question: str, answer: str, key_points: str = "",
        domain_id: str = "", question_id: str = "",
    ) -> str:
        card_id = uuid.uuid4().hex[:8]
        self._execute(
            "INSERT INTO review_cards (id, domain_id, question_id, question, answer, "
            "key_points, next_review, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [card_id, domain_id, question_id, question, answer, key_points,
             _today(), _now()],
        )
        return card_id

    def get_due_review_cards(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM review_cards WHERE next_review <= ? ORDER BY RANDOM() LIMIT ?",
            [_today(), limit],
        )
        return [dict(r) for r in rows]

    def rate_review_card(self, card_id: str, quality: int) -> dict[str, Any] | None:
        card = self._fetchone(
            "SELECT * FROM review_cards WHERE id = ?", [card_id],
        )
        if not card:
            return None
        ease = max(1.3, card["ease_factor"] + (
            0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        ))
        reps = card["repetitions"]
        interval = card["interval"]
        if quality < 3:
            reps = 0
            interval = 1
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 6
            else:
                interval = round(interval * ease)
            reps += 1
        next_review = (_today_as_date() + timedelta(days=interval)).isoformat()

        self._execute(
            "UPDATE review_cards SET ease_factor=?, interval=?, repetitions=?, "
            "next_review=? WHERE id=?",
            [ease, interval, reps, next_review, card_id],
        )
        return {
            "id": card_id, "ease_factor": ease, "interval": interval,
            "repetitions": reps, "next_review": next_review,
        }

    def get_review_stats(self) -> dict[str, Any]:
        total = self._fetchone("SELECT COUNT(*) as cnt FROM review_cards")
        due = self._fetchone(
            "SELECT COUNT(*) as cnt FROM review_cards WHERE next_review <= ?",
            [_today()],
        )
        return {
            "total": total["cnt"] if total else 0,
            "due": due["cnt"] if due else 0,
        }

    # ── Sessions ───────────────────────────────────────────────

    def get_or_create_session(self, key: str) -> dict[str, Any]:
        row = self._fetchone("SELECT * FROM sessions WHERE key = ?", [key])
        if row:
            return dict(row)
        now = time.time()
        default = {
            "key": key,
            "messages": json.dumps([]),
            "created_at": now,
            "updated_at": now,
            "metadata": "{}",
        }
        self._execute(
            "INSERT INTO sessions (key, messages, created_at, updated_at, metadata) "
            "VALUES (?, ?, ?, ?, ?)",
            [key, "[]", now, now, "{}"],
        )
        return default

    def save_session(self, key: str, messages: list[dict[str, Any]],
                     metadata: dict[str, Any] | None = None) -> None:
        self._execute(
            "UPDATE sessions SET messages = ?, updated_at = ?, metadata = ? WHERE key = ?",
            [json.dumps(messages, ensure_ascii=False), time.time(),
             json.dumps(metadata or {}, ensure_ascii=False), key],
        )

    def update_session(self, key: str, messages: list[dict[str, Any]]) -> None:
        self._execute(
            "UPDATE sessions SET messages = ?, updated_at = ? WHERE key = ?",
            [json.dumps(messages, ensure_ascii=False), time.time(), key],
        )

    # ── Study plans ────────────────────────────────────────────

    def create_plan(self, plan_id: str, domain_id: str, start_date: str,
                    end_date: str, daily_minutes: int, total_questions: int,
                    schedule: list[dict[str, Any]]) -> dict[str, Any]:
        plan = {
            "id": plan_id,
            "domain_id": domain_id,
            "start_date": start_date,
            "end_date": end_date,
            "daily_minutes": daily_minutes,
            "total_questions": total_questions,
            "schedule": json.dumps(schedule, ensure_ascii=False),
            "created_at": _now(),
        }
        self._execute(
            "INSERT INTO study_plans (id, domain_id, start_date, end_date, "
            "daily_minutes, total_questions, schedule, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            list(plan.values()),
        )
        return plan

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        row = self._fetchone("SELECT * FROM study_plans WHERE id = ?", [plan_id])
        if row is None:
            return None
        d = dict(row)
        if isinstance(d.get("schedule"), str):
            try:
                d["schedule"] = json.loads(d["schedule"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    # ── Migration from JSON files ──────────────────────────────

    def migrate_from_json(self, practice_dir: str | Path) -> dict[str, Any]:
        """Import existing JSON data into SQLite. Idempotent.

        Processes:
          - banks/*.json  → domains + questions + tags
          - user_memory.json → domain_progress + skill_radar
          - plans/*.json  → study_plans
          - sessions/*.jsonl → sessions
        """
        base = Path(practice_dir)
        stats: dict[str, Any] = {
            "domains": 0, "questions_added": 0, "questions_replaced": 0,
            "progress": 0, "plans": 0, "sessions": 0,
        }

        banks_dir = base / "banks"
        if banks_dir.exists():
            for bp in sorted(banks_dir.glob("*.json")):
                try:
                    data = json.loads(bp.read_text("utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                domain_id = data.get("name", bp.stem)
                self.ensure_domain(
                    domain_id,
                    subject=data.get("subject", ""),
                    domain_prompt=data.get("domain_prompt", ""),
                )
                qs = data.get("questions", [])
                if qs:
                    a, r = self.add_questions(domain_id, qs)
                    stats["questions_added"] += a
                    stats["questions_replaced"] += r
                stats["domains"] += 1

        mem_path = base / "user_memory.json"
        if mem_path.exists():
            try:
                mem = json.loads(mem_path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                mem = {}
            for domain_id, dp in mem.get("domains", {}).items():
                self.ensure_domain(domain_id)
                allowed = {
                    "current_difficulty", "streak_correct", "daily_completed",
                    "daily_goal", "last_practice_date", "total_practice_min",
                    "first_practice_date", "active_plan_id",
                }
                updates = {k: v for k, v in dp.items() if k in allowed and v}
                if updates:
                    self.update_domain_progress(domain_id, **updates)
                for kp, score in dp.get("skill_radar", {}).items():
                    self._execute(
                        "INSERT OR REPLACE INTO skill_radar "
                        "(domain_id, knowledge_point, mastery, total_count, fail_count) "
                        "VALUES (?, ?, ?, 0, 0)",
                        [domain_id, kp, score],
                    )
                for qid, ans in dp.get("answers", {}).items():
                    if ans.get("is_correct") is not None:
                        self._execute(
                            "INSERT INTO answer_records (question_id, domain_id, "
                            "is_correct, answer_text, attempt, answered_at) "
                            "VALUES (?, ?, ?, '', ?, ?)",
                            [qid, domain_id, 1 if ans["is_correct"] else 0,
                             ans.get("attempts", 1), ans.get("last_attempt", _now())],
                        )
                stats["progress"] += 1

        plans_dir = base / "plans"
        if plans_dir.exists():
            for pp in sorted(plans_dir.glob("*.json")):
                try:
                    plan = json.loads(pp.read_text("utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                self._execute(
                    "INSERT OR IGNORE INTO study_plans (id, domain_id, start_date, "
                    "end_date, daily_minutes, total_questions, schedule, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [plan.get("id", pp.stem), plan.get("bank_name", ""),
                     plan.get("start_date", ""), plan.get("end_date", ""),
                     plan.get("daily_minutes", 60), plan.get("total_questions", 0),
                     json.dumps(plan.get("daily_schedule", []), ensure_ascii=False),
                     plan.get("created_at", _now())],
                )
                stats["plans"] += 1

        sessions_dir = base.parent / "sessions"
        if sessions_dir.exists():
            for sp in sorted(sessions_dir.glob("*.jsonl")):
                try:
                    lines = sp.read_text("utf-8").strip().split("\n")
                except OSError:
                    continue
                messages: list[dict] = []
                meta: dict = {}
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("_type") == "metadata":
                        meta = {k: v for k, v in obj.items() if k != "_type"}
                    else:
                        messages.append(obj)
                key = sp.stem.replace("_", ":").replace("-", "/")
                self._execute(
                    "INSERT OR REPLACE INTO sessions (key, messages, created_at, "
                    "updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
                    [key, json.dumps(messages, ensure_ascii=False),
                     meta.get("created_at", time.time()),
                     meta.get("updated_at", time.time()),
                     json.dumps(meta, ensure_ascii=False)],
                )
                stats["sessions"] += 1

        self.conn.commit()
        return stats

    def has_data(self) -> bool:
        row = self._fetchone("SELECT COUNT(*) as cnt FROM questions")
        return row is not None and row["cnt"] > 0

    def has_json_data(self, practice_dir: str | Path) -> bool:
        banks_dir = Path(practice_dir) / "banks"
        return banks_dir.exists() and any(banks_dir.glob("*.json"))


def _today_as_date() -> date:
    return date.today()
