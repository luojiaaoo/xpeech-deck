"""平台自身配置读取测试。"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from xpeech_deck.config import (
    DEFAULT_CONSOLE_LOG_PATH,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_GLOBAL_CONFIG_PATH,
    Settings,
    load_settings,
)


def write_config(path: Path, extra: str = "") -> Path:
    config_path = path / "conf.toml"
    config_path.write_text(
        f'token = "test-token"\nroot_path = "{path.as_posix()}/instances"\n{extra}',
        encoding="utf-8",
    )
    return config_path


def test_listen_port_defaults_to_7801(tmp_path: Path) -> None:
    settings = load_settings(write_config(tmp_path))

    assert settings.listen_port == 7801


def test_listen_port_can_be_configured(tmp_path: Path) -> None:
    settings = load_settings(write_config(tmp_path, "listen_port = 9123\n"))

    assert settings.listen_port == 9123


def test_global_settings_have_project_file_defaults(tmp_path: Path) -> None:
    settings = load_settings(write_config(tmp_path))

    assert settings.display_name == DEFAULT_DISPLAY_NAME
    assert settings.global_host is None
    assert settings.global_config_path == DEFAULT_GLOBAL_CONFIG_PATH
    assert settings.console_log_path == DEFAULT_CONSOLE_LOG_PATH


def test_global_settings_can_be_configured(tmp_path: Path) -> None:
    settings = load_settings(
        write_config(
            tmp_path,
            'display_name = "My Deck"\n'
            'global_host = "https://deck.example.com"\n'
            'global_config_path = "runtime/global.json"\n',
        )
    )

    assert settings.display_name == "My Deck"
    assert settings.global_host == "https://deck.example.com"
    assert settings.global_config_path == (
        DEFAULT_GLOBAL_CONFIG_PATH.parent / "runtime" / "global.json"
    )


@pytest.mark.parametrize(
    "value",
    [
        '"example.com"',
        '"ftp://example.com"',
        '"https://example.com:7801"',
        '"https://example.com/path"',
        '"https://999.1.1.1"',
        '"https://user@example.com"',
        "123",
    ],
)
def test_global_host_rejects_invalid_hosts(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="global_host"):
        load_settings(write_config(tmp_path, f"global_host = {value}\n"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://203.0.113.8", "http://203.0.113.8"),
        ("https://[2001:db8::1]", "https://[2001:db8::1]"),
        ("https://deck.example.com", "https://deck.example.com"),
        ("HTTP://deck.example.com/", "http://deck.example.com"),
    ],
)
def test_global_host_accepts_http_and_https_origins(
    tmp_path: Path, value: str, expected: str
) -> None:
    settings = load_settings(write_config(tmp_path, f'global_host = "{value}"\n'))

    assert settings.global_host == expected


def test_main_starts_uvicorn_on_configured_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main_module = importlib.import_module("xpeech_deck.__main__")
    settings = Settings(token="test-token", root_path=tmp_path, listen_port=9123)
    app = object()
    uvicorn_call: dict[str, object] = {}

    monkeypatch.setattr(main_module, "load_settings", lambda: settings)
    monkeypatch.setattr(main_module, "ensure_root_path", lambda _path: None)
    monkeypatch.setattr(main_module, "docker_available", lambda: True)
    monkeypatch.setattr(main_module, "git_available", lambda: True)
    monkeypatch.setattr(main_module, "create_app", lambda _settings: app)

    def fake_run(received_app: object, **kwargs: object) -> None:
        uvicorn_call.update(app=received_app, **kwargs)

    monkeypatch.setattr(main_module.uvicorn, "run", fake_run)

    main_module.main()

    assert uvicorn_call == {"app": app, "host": "0.0.0.0", "port": 9123}


@pytest.mark.parametrize("value", ["0", "65536", "true", '"9123"'])
def test_listen_port_must_be_a_valid_integer(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="listen_port"):
        load_settings(write_config(tmp_path, f"listen_port = {value}\n"))
