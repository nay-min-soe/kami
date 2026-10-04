from kami.config import AppControlConfig, load_config


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
