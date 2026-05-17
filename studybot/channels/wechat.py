"""WeChat channel via HTTP webhook."""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

import httpx

from studybot.bus import InboundMessage, MessageBus, OutboundMessage


class WeChatChannel:
    name = "wechat"
    display_name = "WeChat"

    def __init__(
        self, bus: MessageBus, host: str = "127.0.0.1", port: int = 8767,
        send_url: str = "http://127.0.0.1:8080/send",
        token: str = "",
    ) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self.send_url = send_url
        self.token = token
        self._chat_map: dict[str, str] = {}
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._client = httpx.AsyncClient(timeout=30)
        self._server: HTTPServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._server = HTTPServer((self.host, self.port), self._make_handler())
        print(f"✓ WeChat channel: http://{self.host}:{self.port}/webhook/wechat")
        await self._loop.run_in_executor(None, self._server.serve_forever)

    def _make_handler(self):
        channel = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/webhook/wechat":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    self.send_response(400)
                    self.end_headers()
                    return
                recv_token = self.headers.get("X-Wechat-Token", "")
                if channel.token and recv_token != channel.token:
                    self.send_response(403)
                    self.end_headers()
                    return
                coro = channel._handle_message(data)
                asyncio.run_coroutine_threadsafe(coro, channel._loop)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"code": 0}).encode())

            def log_message(self, format, *args):
                pass

        return Handler

    async def _handle_message(self, data: dict[str, Any]) -> None:
        content = (
            data.get("content") or data.get("message") or data.get("text") or ""
        )
        wx_id = (
            data.get("from_user") or data.get("sender") or data.get("wx_id") or ""
        )
        if not content or not wx_id:
            return

        # Dedup
        dedup_key = hashlib.md5(
            f"{wx_id}:{content.strip()}".encode()
        ).hexdigest()
        if dedup_key in self._processed_ids:
            return
        self._processed_ids.append(dedup_key)

        if wx_id not in self._chat_map:
            self._chat_map[wx_id] = str(uuid.uuid4())
        await self.bus.publish_inbound(InboundMessage(
            channel="wechat", sender_id=wx_id,
            chat_id=self._chat_map[wx_id],
            content=content.strip(),
            metadata={"raw": data},
        ))

    async def send(self, msg: OutboundMessage) -> None:
        wx_id = next(
            (uid for uid, cid in self._chat_map.items() if cid == msg.chat_id),
            None,
        )
        if not wx_id:
            try:
                wx_id = msg.chat_id.split(":", 1)[1]
            except IndexError:
                return
        headers = {}
        if self.token:
            headers["X-Wechat-Token"] = self.token
        try:
            await self._client.post(
                self.send_url,
                json={"to_user": wx_id, "content": msg.content},
                headers=headers,
            )
        except Exception as e:
            print(f"⚠ WeChat send error: {e}")

    async def send_stream(self, chat_id: str, content: str, done: bool = False) -> None:
        if done and content:
            await self.send(OutboundMessage(
                channel="wechat", chat_id=chat_id, content=content,
            ))

    async def stop(self) -> None:
        await self._client.aclose()
        if self._server:
            self._server.shutdown()
        self._chat_map.clear()
