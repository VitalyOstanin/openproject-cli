"""Tests for configuration resolution and persistence."""

import pytest

from openproject_cli.config import (
    Config,
    default_config_path,
    load_config_file,
    resolve_config,
    save_config_file,
)
from openproject_cli.errors import AuthError, ConfigError


def test_flags_take_precedence_over_env_and_file(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("url: https://file.example\ntoken: file-token\n")
    env = {"OPENPROJECT_URL": "https://env.example", "OPENPROJECT_TOKEN": "env-token"}
    config = resolve_config(url="https://flag.example", token="flag-token", config_path=cfg_file, env=env)
    assert config.base_url == "https://flag.example"
    assert config.token == "flag-token"


def test_env_takes_precedence_over_file(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("url: https://file.example\ntoken: file-token\n")
    env = {"OPENPROJECT_URL": "https://env.example", "OPENPROJECT_TOKEN": "env-token"}
    config = resolve_config(config_path=cfg_file, env=env)
    assert config.base_url == "https://env.example"
    assert config.token == "env-token"


def test_file_used_when_nothing_else(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("url: https://file.example/\ntoken: file-token\ntimeout: 12\nverify_ssl: false\n")
    config = resolve_config(config_path=cfg_file, env={})
    assert config.base_url == "https://file.example"  # trailing slash stripped
    assert config.token == "file-token"
    assert config.timeout == 12
    assert config.verify_ssl is False


def test_insecure_flag_disables_verification(tmp_path):
    config = resolve_config(
        url="https://x", token="t", insecure=True, config_path=tmp_path / "missing.yaml", env={}
    )
    assert config.verify_ssl is False


def test_missing_file_is_empty(tmp_path):
    assert load_config_file(tmp_path / "nope.yaml") == {}


def test_malformed_file_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError):
        load_config_file(cfg_file)


def test_save_and_reload_roundtrip(tmp_path):
    cfg_file = tmp_path / "sub" / "config.yaml"
    config = Config(base_url="https://op.test", token="secret", timeout=20, verify_ssl=False)
    saved = save_config_file(config, cfg_file)
    assert saved == cfg_file
    # 0600 file permissions for the secret.
    assert (cfg_file.stat().st_mode & 0o777) == 0o600
    reloaded = resolve_config(config_path=cfg_file, env={})
    assert reloaded.base_url == "https://op.test"
    assert reloaded.token == "secret"
    assert reloaded.verify_ssl is False


def test_default_config_path_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENPROJECT_CONFIG", str(tmp_path / "custom.yaml"))
    assert default_config_path() == tmp_path / "custom.yaml"


def test_default_config_path_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENPROJECT_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "openproject-cli" / "config.yaml"


def test_require_credentials():
    Config(base_url="https://x", token="t").require_credentials()  # no raise
    with pytest.raises(AuthError):
        Config(base_url="", token="t").require_credentials()
    with pytest.raises(AuthError):
        Config(base_url="https://x", token="").require_credentials()


def test_bad_timeout_env_raises(tmp_path):
    with pytest.raises(ConfigError):
        resolve_config(config_path=tmp_path / "x.yaml", env={"OPENPROJECT_TIMEOUT": "abc"})
