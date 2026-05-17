"""OneBot v11 (QQ) channel via reverse WebSocket."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections import deque
from typing import Any

from websockets.server import serve
from websockets.exceptions import ConnectionClosed

from studybot.bus import InboundMessage, MessageBus, OutboundMessage


class OneBotChannel:
    name = "qq"
    display_name = "QQ (OneBot v11)"

    def __init__(
        self, bus: MessageBus, host: str = "127.0.0.1", port: int = 8766,
        access_token: str = "",
    ) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self.access_token = access_token
        self._connections: dict[str, Any] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._bot_qq: str = ""

    async def start(self) -> None:
        async with serve(
            self._handler, self.host, self.port,
            ping_interval=30, ping_timeout=10,
        ) as server:
            print(f"✓ QQ (OneBot) channel: ws://{self.host}:{self.port}")
            await asyncio.get_running_loop().create_future()

    async def _handler(self, websocket: Any) -> None:
        cid = str(uuid.uuid4())
        self._connections[cid] = websocket
        try:
            async for message in websocket:
                text = message if isinstance(message, str) else message.decode()
                await self._handle_packet(cid, text)
        except ConnectionClosed:
            pass
        finally:
            self._connections.pop(cid, None)
            for k in list(self._pending.keys()):
                fut = self._pending.pop(k, None)
                if fut and not fut.done():
                    fut.cancel()

    async def _handle_packet(self, cid: str, text: str) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return

        # Response to a pending API call
        echo = data.get("echo")
        if echo and echo in self._pending:
            self._pending[echo].set_result(data)
            return

        if data.get("post_type") != "message":
            return

        msg_type = data.get("message_type", "")
        uid = str(data.get("user_id", ""))
        gid = str(data.get("group_id", "")) if msg_type == "group" else ""
        msg_id = data.get("message_id", "")

        if msg_type != "private" and msg_type != "group":
            return

        # Dedup
        if msg_id:
            msg_key = str(msg_id)
            if msg_key in self._processed_ids:
                return
            self._processed_ids.append(msg_key)

        # Learn bot's own QQ from @mention segments
        segments = data.get("message", []) or []
        for seg in segments:
            if seg.get("type") == "self_id":
                self._bot_qq = str(seg.get("data", {}).get("self_id", ""))
            if seg.get("type") == "at" and not self._bot_qq:
                at_qq = str(seg.get("data", {}).get("qq", ""))
                if at_qq and at_qq != "all":
                    self._bot_qq = at_qq

        # Group chat: only respond when bot is @mentioned
        if msg_type == "group":
            mentioned = False
            for seg in segments:
                if seg.get("type") == "at":
                    at_qq = str(seg.get("data", {}).get("qq", ""))
                    if at_qq == "all":
                        mentioned = True
                        break
                    if self._bot_qq and at_qq == self._bot_qq:
                        mentioned = True
                        break
            if not mentioned:
                return

        # Extract text content from message segments
        raw = ""
        for seg in segments:
            seg_type = seg.get("type", "")
            seg_data = seg.get("data", {}) or {}
            if seg_type == "text":
                raw += seg_data.get("text", "")
            elif seg_type == "at":
                raw += f"@{seg_data.get('qq', '')} "
        raw = raw.strip()
        if not raw:
            return

        # chat_id: "qq:g:{group_id}" for group, "qq:u:{user_id}" for private
        if msg_type == "group":
            chat_id = f"qq:g:{gid}"
        else:
            chat_id = f"qq:u:{uid}"

        await self.bus.publish_inbound(InboundMessage(
            channel="qq", sender_id=uid, chat_id=chat_id,
            content=raw,
            metadata={
                "group_id": gid, "msg_type": msg_type,
                "message_id": msg_id, "raw": data,
            },
        ))

    async def send(self, msg: OutboundMessage) -> None:
        if not self._connections:
            print("⚠ No OneBot connection")
            return
        ws = next(iter(self._connections.values()))
        echo = str(uuid.uuid4())

        target = msg.chat_id
        if target.startswith("qq:g:"):
            action = "send_group_msg"
            params = {"group_id": int(target[5:]), "message": msg.content}
        elif target.startswith("qq:u:"):
            action = "send_private_msg"
            params = {"user_id": int(target[5:]), "message": msg.content}
        else:
            return

        payload = {"action": action, "params": params, "echo": echo}
        await ws.send(json.dumps(payload, ensure_ascii=False))

    async def send_stream(self, chat_id: str, content: str, done: bool = False) -> None:
        if done and content:
            await self.send(OutboundMessage(
                channel="qq", chat_id=chat_id, content=content,
            ))

    async def stop(self) -> None:
        for f in self._pending.values():
            f.cancel()
        self._pending.clear()
        self._connections.clear()
