"""Loads ~/.config/kami/config.toml, with environment overrides for the API key."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kami"
CONFIG_PATH = CONFIG_DIR / "config.toml"
API_KEY_ENV_VARS = ("KAMI_API_KEY", "OPENROUTER_API_KEY")


@dataclass
class LLMConfig:
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openrouter/auto"
    api_key: str = ""


@dataclass
class AppControlConfig:
    allowed_apps: list[str] = field(default_factory=list)

    def is_allowed(self, app: str) -> bool:
        return app.strip().lower() in {a.strip().lower() for a in self.allowed_apps}


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    hotkey: str = "<ctrl>+<alt>+k"
    app_control: AppControlConfig = field(default_factory=AppControlConfig)


def _api_key_from_env() -> str:
    for name in API_KEY_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    data: dict = {}
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f)

    llm = data.get("llm", {})
    defaults = LLMConfig()
    return Config(
        llm=LLMConfig(
            base_url=llm.get("base_url", defaults.base_url).rstrip("/"),
            model=llm.get("model", defaults.model),
            api_key=_api_key_from_env() or llm.get("api_key", ""),
        ),
        hotkey=data.get("hotkey", {}).get("toggle", Config.hotkey),
        app_control=AppControlConfig(
            allowed_apps=list(data.get("app_control", {}).get("allowed_apps", [])),
        ),
    )
