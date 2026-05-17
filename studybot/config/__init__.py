"""Configuration schema."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ProviderConfig(Base):
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"


class GatewayConfig(Base):
    host: str = "127.0.0.1"
    port: int = 8765


class QQConfig(Base):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8766
    access_token: str = ""


class WeChatConfig(Base):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8767
    send_url: str = "http://127.0.0.1:8080/send"
    token: str = ""


class WebUIConfig(Base):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8769


class FeishuConfig(Base):
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""


class Config(BaseSettings):
    provider: ProviderConfig = ProviderConfig()
    gateway: GatewayConfig = GatewayConfig()
    workspace: str = "~/.studybot/workspace"
    max_iterations: int = 10
    qq: QQConfig = QQConfig()
    wechat: WeChatConfig = WeChatConfig()
    feishu: FeishuConfig = FeishuConfig()
    webui: WebUIConfig = WebUIConfig()

    model_config = ConfigDict(env_prefix="STUDYBOT_", env_nested_delimiter="__")

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace).expanduser()
