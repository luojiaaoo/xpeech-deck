"""配置文件全文编辑：保留自定义内容，校验失败不覆盖原文件。"""

from __future__ import annotations

import pytest

VALID_CONF = '[path]\nsession_path = "data/session"\n'
CUSTOM_ENV = (
    '# 自定义运行参数\r\n'
    'COMPOSE_PROJECT_NAME=custom-project\r\n'
    '\r\n'
    'BACKEND_PORT=${CUSTOM_BACKEND_PORT:-8000}\r\n'
    'WEB_CLIENT_PORT=9000\r\n'
    'CDP_URL="ws://custom-browser:3001"\r\n'
    'export EXTRA_OPTIONS="--flag=value # keep"\r\n'
    'CUSTOM_TOKEN=abc=def\r\n'
    'EMPTY_VALUE=\r\n'
    '# 无末尾换行'
)


def _save(client, auth_headers, env=CUSTOM_ENV, conf=VALID_CONF):
    return client.put(
        "/api/instances/demo01/config",
        headers=auth_headers,
        json={"env_content": env, "conf_toml": conf},
    )


def test_get_config_returns_file_contents(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    path = root_path / "demo01"
    (path / ".env").write_bytes(CUSTOM_ENV.encode("utf-8"))
    conf = '# 保留注释\r\n[path]\r\nsession_path = "custom/path"'
    (path / "conf.toml").write_bytes(conf.encode("utf-8"))

    response = client.get("/api/instances/demo01/config", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "name": "demo01", "env_content": CUSTOM_ENV, "conf_toml": conf,
    }


def test_save_config_preserves_submitted_files(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    conf = '# 自定义配置\r\n[path]\r\nsession_path = "custom/session"'
    response = _save(client, auth_headers, conf=conf)

    assert response.status_code == 200
    assert response.json() == {"success": True}
    path = root_path / "demo01"
    assert (path / ".env").read_bytes() == CUSTOM_ENV.encode("utf-8")
    assert (path / "conf.toml").read_bytes() == conf.encode("utf-8")
    assert client.get("/api/instances/demo01/config", headers=auth_headers).json()["env_content"] == CUSTOM_ENV


def test_editing_conf_preserves_existing_env(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    env_file = root_path / "demo01" / ".env"
    env_file.write_bytes(CUSTOM_ENV.encode("utf-8"))
    data = client.get("/api/instances/demo01/config", headers=auth_headers).json()

    response = _save(client, auth_headers, env=data["env_content"], conf='debug = true\n')

    assert response.status_code == 200
    assert env_file.read_bytes() == CUSTOM_ENV.encode("utf-8")


def test_editing_env_preserves_existing_conf(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    conf_file = root_path / "demo01" / "conf.toml"
    conf = '# Keep formatting\r\nflag = true'
    conf_file.write_bytes(conf.encode("utf-8"))
    data = client.get("/api/instances/demo01/config", headers=auth_headers).json()

    assert _save(client, auth_headers, conf=data["conf_toml"]).status_code == 200
    assert conf_file.read_bytes() == conf.encode("utf-8")


def test_save_does_not_inject_default_parameters(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    env = 'COMPOSE_PROJECT_NAME=renamed\nMY_CUSTOM_SETTING=value\n'

    assert _save(client, auth_headers, env=env).status_code == 200
    assert (root_path / "demo01" / ".env").read_bytes() == env.encode("utf-8")
    assert client.get("/api/instances/demo01/config", headers=auth_headers).status_code == 200


@pytest.mark.parametrize("env", ["", "# comment\n", "COMPOSE_PROJECT_NAME=\nEXTRA=1\n"])
def test_missing_project_name_does_not_overwrite(client, auth_headers, make_instance, root_path, env):
    make_instance("demo01")
    path = root_path / "demo01"
    before = {name: (path / name).read_bytes() for name in (".env", "conf.toml")}

    response = _save(client, auth_headers, env=env)

    assert response.status_code == 400
    assert "COMPOSE_PROJECT_NAME" in response.json()["detail"]
    assert {name: (path / name).read_bytes() for name in before} == before


def test_invalid_toml_does_not_overwrite(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    path = root_path / "demo01"
    before = {name: (path / name).read_bytes() for name in (".env", "conf.toml")}

    r = _save(client, auth_headers, conf="[unclosed")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "语法错误" in detail

    assert {name: (path / name).read_bytes() for name in before} == before


def test_port_only_request_cannot_overwrite_env(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    env_file = root_path / "demo01" / ".env"
    env_file.write_bytes(CUSTOM_ENV.encode("utf-8"))

    response = client.put(
        "/api/instances/demo01/config",
        headers=auth_headers,
        json={"backend_port": "8000", "web_client_port": "9000", "conf_toml": VALID_CONF},
    )

    assert response.status_code == 422
    assert env_file.read_bytes() == CUSTOM_ENV.encode("utf-8")


def test_config_of_missing_instance_404(client, auth_headers):
    assert client.get("/api/instances/ghost/config", headers=auth_headers).status_code == 404
    r = client.put(
        "/api/instances/ghost/config",
        headers=auth_headers,
        json={"env_content": CUSTOM_ENV, "conf_toml": VALID_CONF},
    )
    assert r.status_code == 404
