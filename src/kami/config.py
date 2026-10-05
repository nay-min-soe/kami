"""Loads ~/.config/kami/config.toml, with environment overrides for the API key.

A broken file raises ConfigError with a message naming the file, the key and the fix.
Wrong types are refused, never coerced. Unknown keys become `Config.warnings`.
"""
from __future__ import annotations

import difflib
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kami"
CONFIG_PATH = CONFIG_DIR / "config.toml"
API_KEY_ENV_VARS = ("KAMI_API_KEY", "OPENROUTER_API_KEY")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Every section and key load_config reads. Anything else becomes a warning.
KNOWN_KEYS = {
    "llm": {"base_url", "model", "api_key"},
    "hotkey": {"toggle"},
    "app_control": {"allowed_apps"},
}


class ConfigError(ValueError):
    """The config file can't be used. The message says where and how to fix it."""


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
    warnings: list[str] = field(default_factory=list)


def _api_key_from_env() -> str:
    for name in API_KEY_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _shown(path: Path) -> str:
    """The path as the user would write it: ~/.config/... instead of /home/me/.config/..."""
    home = str(Path.home())
    text = str(path)
    return "~" + text[len(home):] if text.startswith(home + os.sep) else text


def _table(data: dict, section: str, where: str) -> dict:
    value = data.get(section, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: [{section}] must be a section, written as [{section}] "
                          "on its own line with its keys below it.")
    return value


def _str(table: dict, section: str, key: str, default: str, where: str) -> str:
    value = table.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f'{where}: [{section}] {key} must be text in quotes, '
                          f'e.g. {key} = "{default}"')
    return value


def _str_list(table: dict, section: str, key: str, where: str) -> list[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f'{where}: [{section}] {key} must be a list of app names, '
                          'e.g. ["firefox"]')
    return list(value)


def _unknown_key_warnings(data: dict) -> list[str]:
    def hint(name: str, known) -> str:
        close = difflib.get_close_matches(name, known, n=1)
        return f" Did you mean '{close[0]}'?" if close else ""

    warnings = []
    for section, table in data.items():
        if section not in KNOWN_KEYS:
            warnings.append(f"Unknown section [{section}].{hint(section, KNOWN_KEYS)}")
        elif isinstance(table, dict):
            for key in table:
                if key not in KNOWN_KEYS[section]:
                    warnings.append(f"Unknown key '{key}' in [{section}]."
                                    f"{hint(key, KNOWN_KEYS[section])}")
    return warnings


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    where = _shown(path)
    data: dict = {}
    if path.exists():
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{where}: not valid TOML ({exc}). Fix that line, or move the "
                              "file away to start with defaults.") from exc
        except OSError as exc:
            raise ConfigError(f"{where}: can't be read ({exc.strerror}).") from exc

    defaults = LLMConfig()
    llm = _table(data, "llm", where)
    base_url = _str(llm, "llm", "base_url", defaults.base_url, where).rstrip("/")
    url = urlsplit(base_url)
    local = url.scheme == "http" and url.hostname in LOCAL_HOSTS
    if not (url.scheme == "https" and url.hostname) and not local:
        # Plain http would send the API key unencrypted, so only allow it for local models.
        raise ConfigError(f'{where}: [llm] base_url must start with https:// '
                          f'(http:// only for localhost), e.g. base_url = "{defaults.base_url}"')

    return Config(
        llm=LLMConfig(
            base_url=base_url,
            model=_str(llm, "llm", "model", defaults.model, where),
            api_key=_api_key_from_env() or _str(llm, "llm", "api_key", "", where),
        ),
        hotkey=_str(_table(data, "hotkey", where), "hotkey", "toggle", Config.hotkey, where),
        app_control=AppControlConfig(
            allowed_apps=_str_list(_table(data, "app_control", where), "app_control",
                                   "allowed_apps", where),
        ),
        warnings=_unknown_key_warnings(data),
    )
