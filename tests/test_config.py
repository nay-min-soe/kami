from pathlib import Path

import pytest

from kami.config import AppControlConfig, ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.delenv("KAMI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = load_config(tmp_path / "missing.toml")
    assert cfg.llm.base_url == "https://openrouter.ai/api/v1"
    assert cfg.llm.api_key == ""
    assert cfg.app_control.allowed_apps == []


def test_env_key_beats_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('[llm]\napi_key = "from-file"\nmodel = "x/y"\n')
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    cfg = load_config(path)
    assert cfg.llm.api_key == "from-env"
    assert cfg.llm.model == "x/y"


def test_allowlist_is_case_insensitive():
    policy = AppControlConfig(allowed_apps=["Firefox", " code "])
    assert policy.is_allowed("firefox")
    assert policy.is_allowed("CODE")
    assert not policy.is_allowed("rm")


def _load(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text)
    return load_config(path)


def test_invalid_toml_raises_config_error_with_path(tmp_path):
    with pytest.raises(ConfigError, match="config.toml") as err:
        _load(tmp_path, "[llm\n")
    assert "line 1" in str(err.value)


def test_allowed_apps_string_is_rejected(tmp_path):
    # Regression: "firefox" used to become ["f", "i", "r", ...] and quietly change the allowlist.
    with pytest.raises(ConfigError, match="allowed_apps must be a list"):
        _load(tmp_path, '[app_control]\nallowed_apps = "firefox"\n')


def test_allowed_apps_non_string_item_rejected(tmp_path):
    with pytest.raises(ConfigError, match="allowed_apps"):
        _load(tmp_path, '[app_control]\nallowed_apps = ["firefox", 3]\n')


def test_llm_section_must_be_table(tmp_path):
    with pytest.raises(ConfigError, match=r"\[llm\] must be a section"):
        _load(tmp_path, 'llm = "x"\n')


def test_model_must_be_string(tmp_path):
    with pytest.raises(ConfigError, match="model must be text"):
        _load(tmp_path, "[llm]\nmodel = 5\n")


def test_base_url_must_be_http(tmp_path):
    with pytest.raises(ConfigError, match="http"):
        _load(tmp_path, '[llm]\nbase_url = "openrouter.ai"\n')


def test_unknown_key_becomes_warning_with_suggestion(tmp_path):
    cfg = _load(tmp_path, "[app_control]\nallowed_app = []\n")
    assert len(cfg.warnings) == 1
    assert "allowed_app" in cfg.warnings[0] and "allowed_apps" in cfg.warnings[0]


def test_error_never_echoes_the_api_key(tmp_path):
    with pytest.raises(ConfigError) as err:
        _load(tmp_path, '[llm]\napi_key = "sk-or-secret123"\nmodel = 5\n')
    assert "secret123" not in str(err.value)


def test_example_config_loads_cleanly():
    cfg = load_config(EXAMPLE)
    assert cfg.warnings == []
    assert cfg.app_control.allowed_apps == ["firefox", "code"]
