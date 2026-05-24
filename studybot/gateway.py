"""Gateway: main entry point for studybot."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from studybot.agent.loop import PracticeAgentLoop
from studybot.agent.tools.practice import PracticeQuestionsTool
from studybot.agent.tools.registry import ToolRegistry
from studybot.bus import MessageBus, OutboundMessage
from studybot.channels.websocket import WebSocketChannel
from studybot.config import Config
from studybot.providers.openai_compat import OpenAICompatProvider
from studybot.session import SessionManager
from studybot.storage.db import Storage


def load_config(config_path: str | None = None) -> Config:
    if config_path:
        path = Path(config_path)
    else:
        path = Path.home() / ".studybot" / "config.json"
    if path.exists():
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return Config(**data)
    return Config()


def _build_channels(config, bus, storage, provider=None, config_path=None):
    if config_path is None:
        config_path = str(Path.home() / ".studybot" / "config.json")
    channels: dict[str, object] = {}

    ws = WebSocketChannel(
        bus=bus, host=config.gateway.host, port=config.gateway.port,
    )
    channels["websocket"] = ws
    print(f"✓ WebSocket channel: ws://{config.gateway.host}:{config.gateway.port}")

    if config.qq.enabled:
        from studybot.channels.onebot import OneBotChannel
        qq = OneBotChannel(
            bus=bus, host=config.qq.host, port=config.qq.port,
            access_token=config.qq.access_token,
        )
        channels["qq"] = qq
        print(f"✓ QQ (OneBot) channel: ws://{config.qq.host}:{config.qq.port}")

    if config.wechat.enabled:
        from studybot.channels.wechat import WeChatChannel
        wechat = WeChatChannel(
            bus=bus, host=config.wechat.host, port=config.wechat.port,
            send_url=config.wechat.send_url, token=config.wechat.token,
        )
        channels["wechat"] = wechat
        print(f"✓ WeChat channel: http://{config.wechat.host}:{config.wechat.port}/webhook/wechat")

    if config.feishu.enabled:
        from studybot.channels.feishu import FeishuChannel
        feishu = FeishuChannel(
            bus=bus, app_id=config.feishu.app_id, app_secret=config.feishu.app_secret,
        )
        channels["feishu"] = feishu

    if config.webui.enabled:
        from studybot.channels.webui import WebUIChannel
        webui = WebUIChannel(
            bus=bus, storage=storage,
            host=config.webui.host, port=config.webui.port,
            ws_host=config.gateway.host, ws_port=config.gateway.port,
            provider=provider, config_path=config_path,
        )
        channels["webui"] = webui
        print(f"✓ Web UI channel (Storage-backed): http://{config.webui.host}:{config.webui.port}")

    return channels


async def run_gateway(config_path: str | None = None) -> None:
    config = load_config(config_path)
    workspace = config.workspace_path
    workspace.mkdir(parents=True, exist_ok=True)

    print(f"📚 Starting studybot gateway...\n")

    bus = MessageBus()
    provider = OpenAICompatProvider(
        api_key=config.provider.api_key,
        api_base=config.provider.api_base,
        default_model=config.provider.model,
    )
    session_manager = SessionManager(workspace)

    # Shared Storage instance — single source of truth
    storage = Storage(workspace / "studybot.db")
    storage.connect()

    tools = ToolRegistry()
    tools.register(PracticeQuestionsTool(workspace=str(workspace), provider=provider, storage=storage))

    agent = PracticeAgentLoop(
        provider=provider, tools=tools, session_manager=session_manager,
        bus=bus, model=config.provider.model,
        max_iterations=config.max_iterations,
    )

    channels = _build_channels(config, bus, storage, provider=provider, config_path=config_path)

    async def outbound_consumer() -> None:
        while True:
            msg = await bus.consume_outbound()
            ch = channels.get(msg.channel)
            if not ch:
                continue
            is_stream = msg.metadata.get("stream", False)
            is_done = msg.metadata.get("done", False)
            if is_stream:
                await ch.send_stream(msg.chat_id, msg.content, done=is_done)
            else:
                await ch.send(msg)

    def health_server() -> None:
        import http.server

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass

        server = http.server.HTTPServer((config.gateway.host, config.gateway.port + 1000), Handler)
        print(f"✓ Health endpoint: http://{config.gateway.host}:{config.gateway.port + 1000}/health")
        server.serve_forever()

    print(f"✓ Registered tools: {list(tools._tools.keys())}")
    print(f"✓ Workspace: {workspace}")
    print()
    label = ", ".join(channels.keys())
    print(f"Ready! Active channels: {label}")

    coros = [agent.run(), outbound_consumer()]
    for ch in channels.values():
        coros.append(ch.start())
    coros.append(asyncio.to_thread(health_server))

    await asyncio.gather(*coros)


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        asyncio.run(run_gateway(config_path))
    except KeyboardInterrupt:
        print("\n👋 studybot stopped.")


if __name__ == "__main__":
    main()
