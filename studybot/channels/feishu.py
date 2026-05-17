"""Feishu (飞书) channel using lark-oapi SDK WebSocket."""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from typing import Any

import httpx

from studybot.bus import InboundMessage, MessageBus, OutboundMessage

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
BOT_INFO_URL = "https://open.feishu.cn/open-apis/bot/v3/info"


class FeishuChannel:
    name = "feishu"
    display_name = "飞书"

    def __init__(
        self, bus: MessageBus,
        app_id: str = "", app_secret: str = "",
    ) -> None:
        self.bus = bus
        self.app_id = app_id
        self.app_secret = app_secret
        self._running = False
        self._thread: threading.Thread | None = None
        self._event_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._chat_map: dict[str, dict] = {}
        self._open_to_chat: dict[str, str] = {}
        self._http = httpx.AsyncClient(timeout=30)
        self._token: str = ""
        self._token_expires: float = 0
        self._processed_ids: set[str] = set()
        self._bot_open_id: str | None = None

    async def start(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()

        # Fetch bot's own open_id for @mention detection
        self._bot_open_id = await self._fetch_bot_open_id()
        if self._bot_open_id:
            print(f"✓ Feishu bot open_id: {self._bot_open_id}")
        else:
            print("⚠ Feishu: could not fetch bot open_id")

        self._thread = threading.Thread(target=self._run_sdk, daemon=True)
        self._thread.start()
        asyncio.create_task(self._poll_events())
        print("✓ Feishu channel started (SDK thread)")

    async def _fetch_bot_open_id(self) -> str | None:
        token = await self._ensure_token()
        if not token:
            return None
        try:
            resp = await self._http.get(
                BOT_INFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
            data = resp.json()
            bot = ((data.get("data") or data).get("bot") or data.get("bot")) or {}
            return bot.get("open_id")
        except Exception:
            return None

    def _on_message(self, event_data: Any) -> None:
        """SDK event handler callback (runs in SDK thread's event loop)."""
        self._event_queue.put_nowait(event_data)

    def _run_sdk(self) -> None:
        import lark_oapi as lark
        import lark_oapi.ws.client as _lark_ws_client

        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        _lark_ws_client.loop = ws_loop

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )

        client = lark.ws.Client(
            self.app_id, self.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.ERROR,
        )

        while self._running:
            try:
                client.start()
            except Exception as e:
                print(f"⚠ Feishu WS error: {e}")
                if self._running:
                    import time as _time
                    _time.sleep(5)

    async def _poll_events(self) -> None:
        while self._running:
            try:
                event_data = self._event_queue.get_nowait()
                await self._process_event(event_data)
            except queue.Empty:
                await asyncio.sleep(0.05)

    async def _process_event(self, event_data: Any) -> None:
        event = getattr(event_data, "event", None) or {}
        header = getattr(event_data, "header", None) or {}
        if getattr(header, "event_type", "") != "im.message.receive_v1":
            return

        message = getattr(event, "message", None) or {}
        sender = getattr(event, "sender", None) or {}

        msg_id = getattr(message, "message_id", "") or ""
        if msg_id:
            if msg_id in self._processed_ids:
                return
            self._processed_ids.add(msg_id)
            if len(self._processed_ids) > 1000:
                self._processed_ids.clear()

        msg_type = getattr(message, "message_type", "")
        chat_type = getattr(message, "chat_type", "")
        open_id = getattr(getattr(sender, "sender_id", None) or {}, "open_id", "")
        chat_id = getattr(message, "chat_id", "")

        if not open_id:
            return

        # Group chat: only respond when bot is @mentioned
        if chat_type == "group":
            mentions = getattr(message, "mentions", None) or []
            mentioned = any(
                getattr(getattr(m, "id", None) or {}, "open_id", "") == self._bot_open_id
                for m in mentions
            ) or ("@_all" in (getattr(message, "content", "") or ""))
            if not mentioned:
                return

        # Extract text from different message types
        content_raw = getattr(message, "content", "") or "{}"
        try:
            content_data = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        except (json.JSONDecodeError, TypeError):
            return

        text = ""
        if msg_type == "text":
            text = content_data.get("text", "")
        else:
            return

        text = text.strip()
        if not text:
            return

        if open_id not in self._open_to_chat:
            conv_id = str(uuid.uuid4())
            self._open_to_chat[open_id] = conv_id
            self._chat_map[conv_id] = {
                "open_id": open_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
            }

        await self.bus.publish_inbound(InboundMessage(
            channel="feishu",
            sender_id=open_id,
            chat_id=self._open_to_chat[open_id],
            content=text,
            metadata={
                "open_id": open_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_id": msg_id,
            },
        ))

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires - 120:
            return self._token
        try:
            resp = await self._http.post(
                TOKEN_URL,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()
            if data.get("code") != 0:
                return ""
            self._token = data.get("tenant_access_token", "")
            self._token_expires = time.time() + data.get("expire", 7200)
        except Exception:
            return ""
        return self._token

    async def send(self, msg: OutboundMessage) -> None:
        info = self._chat_map.get(msg.chat_id)
        if not info:
            return
        token = await self._ensure_token()
        if not token:
            return

        content = json.dumps({"text": msg.content}, ensure_ascii=False)
        receive_id = info.get("chat_id") or info["open_id"]
        receive_id_type = "chat_id" if info.get("chat_id") else "open_id"

        try:
            resp = await self._http.post(
                SEND_URL,
                params={"receive_id_type": receive_id_type},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "text",
                    "content": content,
                },
            )
            result = resp.json()
            if result.get("code") != 0:
                print(f"⚠ Feishu send error: {result.get('msg', '')}")
        except Exception as e:
            print(f"⚠ Feishu send error: {e}")

    async def send_stream(self, chat_id: str, content: str, done: bool = False) -> None:
        if done and content:
            await self.send(OutboundMessage(
                channel="feishu", chat_id=chat_id, content=content,
            ))

    async def stop(self) -> None:
        self._running = False
        await self._http.aclose()
        self._chat_map.clear()
        self._open_to_chat.clear()
        self._processed_ids.clear()
