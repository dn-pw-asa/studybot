"""Session management with JSONL persistence."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Session:
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **kwargs,
        })
        self.updated_at = time.time()

    def get_history(self, max_messages: int = 50) -> list[dict[str, Any]]:
        recent = self.messages[-max_messages:]
        return [
            {"role": m["role"], "content": m["content"]}
            for m in recent
            if m.get("role") in ("system", "user", "assistant")
        ]

    def apply_compression(self, compressor: ContextCompressor, max_messages: int = 50) -> None:
        """Replace old messages with compressed summary in-place."""
        filtered = [
            {"role": m["role"], "content": m["content"], "timestamp": m.get("timestamp", time.time())}
            for m in self.messages
            if m.get("role") in ("system", "user", "assistant")
        ]
        if len(filtered) <= max_messages:
            return
        older = filtered[:-10]
        recent = filtered[-10:]
        summary = compressor.compress(older)
        self.messages = summary + recent


class ContextCompressor:
    """分层上下文压缩: 将旧消息批量压缩为摘要."""

    def __init__(self, summarize_fn: Callable[[str, str], str] | None = None) -> None:
        self.summary: str = ""
        self.summarize_fn = summarize_fn

    def compress(self, older: list[dict]) -> list[dict]:
        if not older:
            return []
        self._update_summary(older)
        return [{"role": "system", "content": f"## 历史摘要\n{self.summary[:800]}", "timestamp": 0}]

    def _update_summary(self, older: list[dict]) -> None:
        text = "\n".join(
            m.get("content", "")[:300] for m in older[-15:]
            if m.get("role") in ("user", "assistant")
        )
        if self.summarize_fn:
            try:
                self.summary = self.summarize_fn(self.summary, text[:3000])[:1200]
                return
            except Exception:
                pass
        self._fallback_summary(older)

    def _fallback_summary(self, older: list[dict]) -> None:
        lines = [self.summary] if self.summary else []
        for m in older[-8:]:
            c = m.get("content", "").strip()
            if len(c) > 30:
                lines.append(c[:150])
        self.summary = "\n".join(lines[-4:])[:800]


class SessionManager:
    def __init__(self, workspace: Path) -> None:
        self._sessions_dir = workspace / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _get_path(self, key: str) -> Path:
        safe = key.replace(":", "_").replace("/", "_")
        return self._sessions_dir / f"{safe}.jsonl"

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]
        session = self._load(key)
        if session is None:
            session = Session(key=key)
        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        path = self._get_path(key)
        if not path.exists():
            return None
        messages = []
        meta = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("_type") == "metadata":
                        meta = {k: v for k, v in obj.items() if k != "_type"}
                    else:
                        messages.append(obj)
                except json.JSONDecodeError:
                    continue
        session = Session(key=key, messages=messages, metadata=meta)
        return session

    def save(self, session: Session) -> None:
        path = self._get_path(session.key)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            meta_line = json.dumps({"_type": "metadata", **session.metadata}, ensure_ascii=False)
            f.write(meta_line + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        os.replace(str(tmp), str(path))
        self._cache[session.key] = session
