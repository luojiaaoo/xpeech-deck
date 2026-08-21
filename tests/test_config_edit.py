"""配置编辑测试：端口校验与 conf.toml 读写。"""

from __future__ import annotations

import pytest

VALID_CONF = '[path]\nsession_path = "data/session"\n'


def _save(client, auth_headers, backend="8000", web="9000", conf=VALID_CONF):
    return client.put(
        "/api/instances/demo01/config",
        headers=auth_headers,
        json={"backend_port": backend, "web_client_port": web, "conf_toml": conf},
    )


def test_get_config(client, auth_headers, make_instance):
    make_instance("demo01")
    r = client.get("/api/instances/demo01/config", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "demo01"
    assert data["backend_port"] == 7878
    assert data["web_client_port"] == 7939
    assert "session_path" in data["conf_toml"]


def test_save_config_updates_ports(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    r = _save(client, auth_headers, backend="8000", web="9000")
    assert r.status_code == 200
    assert r.json() == {"success": True}

    env = (root_path / "demo01" / ".env").read_text(encoding="utf-8")
    assert "BACKEND_PORT=8000" in env
    assert "WEB_CLIENT_PORT=9000" in env
    # 项目名与 CDP_URL 保持不变
    assert "COMPOSE_PROJECT_NAME=demo01" in env
    assert "CDP_URL=ws://browserless:3000" in env
    # conf.toml 已保存
    assert (root_path / "demo01" / "conf.toml").read_text(encoding="utf-8") == VALID_CONF


def test_save_accepts_numeric_strings(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    r = _save(client, auth_headers, backend="8000", web="9000")
    assert r.status_code == 200
    env = (root_path / "demo01" / ".env").read_text(encoding="utf-8")
    assert "BACKEND_PORT=8000" in env


@pytest.mark.parametrize(
    ("backend", "web"),
    [
        ("abc", "9000"),
        ("8000", "abc"),
        ("-1", "9000"),
        ("0", "9000"),
        ("65536", "9000"),
        ("8000", "65536"),
        ("8000.5", "9000"),
    ],
)
def test_invalid_ports_rejected(client, auth_headers, make_instance, backend, web):
    make_instance("demo01")
    r = _save(client, auth_headers, backend=backend, web=web)
    assert r.status_code == 400


def test_equal_ports_rejected(client, auth_headers, make_instance):
    make_instance("demo01")
    r = _save(client, auth_headers, backend="8000", web="8000")
    assert r.status_code == 400
    assert "不能相同" in r.json()["detail"]


def test_invalid_toml_does_not_overwrite(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    conf_file = root_path / "demo01" / "conf.toml"
    before = conf_file.read_text(encoding="utf-8")

    r = _save(client, auth_headers, backend="8000", web="9000", conf="[unclosed")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "语法错误" in detail

    # 原 conf.toml 未被覆盖，端口也未修改
    assert conf_file.read_text(encoding="utf-8") == before
    env = (root_path / "demo01" / ".env").read_text(encoding="utf-8")
    assert "BACKEND_PORT=7878" in env


def test_config_of_missing_instance_404(client, auth_headers):
    assert client.get("/api/instances/ghost/config", headers=auth_headers).status_code == 404
    r = client.put(
        "/api/instances/ghost/config",
        headers=auth_headers,
        json={"backend_port": "8000", "web_client_port": "9000", "conf_toml": VALID_CONF},
    )
    assert r.status_code == 404
