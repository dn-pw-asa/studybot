"""WebSocket channel with streaming support."""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from websockets.server import serve
from websockets.exceptions import ConnectionClosed

from studybot.bus import InboundMessage, MessageBus, OutboundMessage


class WebSocketChannel:
    name = "websocket"
    display_name = "WebSocket"

    def __init__(self, bus: MessageBus, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self._connections: dict[str, Any] = {}
        self._stream_tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        async with serve(
            self._handler,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
        ) as server:
            print(f"✓ WebSocket channel started on ws://{self.host}:{self.port}")
            await asyncio.get_running_loop().create_future()

    async def _handler(self, websocket: Any) -> None:
        chat_id = str(uuid.uuid4())
        self._connections[chat_id] = websocket
        try:
            async for message in websocket:
                text = message if isinstance(message, str) else message.decode()
                content = self._parse_payload(text)
                if content:
                    await self.bus.publish_inbound(InboundMessage(
                        channel="websocket",
                        sender_id="user",
                        chat_id=chat_id,
                        content=content,
                    ))
        except ConnectionClosed:
            pass
        finally:
            self._connections.pop(chat_id, None)
            task = self._stream_tasks.pop(chat_id, None)
            if task and not task.done():
                task.cancel()

    def _parse_payload(self, text: str) -> str | None:
        try:
            data = json.loads(text)
            return data.get("content") or data.get("message") or data.get("text")
        except json.JSONDecodeError:
            return text.strip() or None

    async def send(self, msg: OutboundMessage) -> None:
        ws = self._connections.get(msg.chat_id)
        if ws:
            payload = json.dumps({
                "event": "message",
                "content": msg.content,
                "reply_to": msg.reply_to,
            }, ensure_ascii=False)
            await ws.send(payload)

    async def send_stream(self, chat_id: str, content: str, done: bool = False) -> None:
        """Stream a text delta to the client."""
        ws = self._connections.get(chat_id)
        if ws:
            payload = json.dumps({
                "event": "stream" if not done else "message",
                "content": content,
                "done": done,
            }, ensure_ascii=False)
            await ws.send(payload)

    async def stop(self) -> None:
        for task in self._stream_tasks.values():
            if not task.done():
                task.cancel()
        self._stream_tasks.clear()
        self._connections.clear()
