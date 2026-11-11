"""实例创建与发现测试。"""

from __future__ import annotations

import pytest

from xpeech_deck.git_service import (
    GIT_NETWORK_OPTIONS,
    VERSION_HISTORY_LIMIT,
    XPEECH_REPOSITORY_URL,
)


def test_create_instance_success(client, auth_headers, root_path, make_instance):
    data = make_instance("demo01")
    assert data["name"] == "demo01"
    assert data["backend_port"] is None
    assert data["web_client_port"] is None
    assert data["ports"] == []
    assert data["path"] == str(root_path / "demo01")

    target = root_path / "demo01"
    assert target.is_dir()

    # 完整保留示例文件，仅将 Compose 项目名设置为实例名。
    env = (target / ".env").read_text(encoding="utf-8")
    assert "COMPOSE_PROJECT_NAME=demo01" in env
    assert "BACKEND_PORT=7878" in env
    assert "WEB_CLIENT_PORT=7939" in env
    assert "CDP_URL=ws://browserless:3000" in env
    assert (target / ".env").read_bytes() == (target / ".env.example").read_bytes().replace(
        b"COMPOSE_PROJECT_NAME=xpeech", b"COMPOSE_PROJECT_NAME=demo01"
    )

    # 每个实例都是可 fetch/切换版本的独立 Git 工作树。
    assert (target / ".git").is_dir()

    # conf.toml 由示例文件初始化。
    conf = (target / "conf.toml").read_text(encoding="utf-8")
    assert 'session_path = "data/session"' in conf

    # 源文件保持原样
    assert (target / "compose.yaml").is_file()
    assert (target / "Dockerfile").is_file()
    assert (target / "main.py").is_file()
    assert (target / "custom_tools" / "echo.py").is_file()
    assert (target / "conf.toml").is_file()
    assert (target / ".env.example").is_file()

    clone_cmd, clone_cwd = client.app.state.test_git_commands[0]
    assert clone_cmd == [
        "git",
        *GIT_NETWORK_OPTIONS,
        "clone",
        "--depth",
        str(VERSION_HISTORY_LIMIT),
        "--no-single-branch",
        XPEECH_REPOSITORY_URL,
        str(target),
    ]
    assert clone_cwd == str(root_path)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_create_preserves_template_configuration(
    client, auth_headers, root_path, repository_template, make_instance, newline
):
    template = newline.join([
        "# 自定义配置",
        'export COMPOSE_PROJECT_NAME = "upstream" # 项目名',
        "",
        "POSTGRES_PASSWORD=custom-password",
        "# BACKEND_PORT=7878",
        "BACKEND_PORT=8787",
        "WEB_CLIENT_PORT=8939",
        "POSTGRES_PORT=7890",
        "",
    ])
    source = repository_template / ".env.example"
    source.write_bytes(template.encode("utf-8"))

    data = make_instance("demo01")

    target = root_path / "demo01"
    expected = template.replace('"upstream"', "demo01").encode("utf-8")
    assert (target / ".env").read_bytes() == expected
    assert (target / ".env.example").read_bytes() == source.read_bytes()
    assert data["backend_port"] == 8787
    assert data["web_client_port"] == 8939
    assert data["ports"] == ["8787", "8939", "7890"]
    listed = client.get("/api/instances", headers=auth_headers).json()["instances"][0]
    assert listed == data


@pytest.mark.parametrize("template", ["", "# COMPOSE_PROJECT_NAME=xpeech\r\nCUSTOM=value"])
def test_create_adds_missing_project_name(root_path, repository_template, make_instance, template):
    (repository_template / ".env.example").write_bytes(template.encode("utf-8"))

    make_instance("demo01")

    newline = "\r\n" if "\r\n" in template else "\n"
    expected = (template + newline if template else "") + f"COMPOSE_PROJECT_NAME=demo01{newline}"
    assert (root_path / "demo01" / ".env").read_bytes() == expected.encode("utf-8")


def test_create_missing_env_template_rolls_back(client, auth_headers, root_path, repository_template):
    (repository_template / ".env.example").unlink()

    response = client.post("/api/instances", json={"name": "demo01"}, headers=auth_headers)

    assert response.status_code == 500
    assert ".env.example" in response.json()["detail"]
    assert not (root_path / "demo01").exists()


@pytest.mark.parametrize("value", ["", "invalid", "0", "-1", "65536"])
def test_invalid_ports_have_no_fallback(
    client, auth_headers, repository_template, make_instance, value
):
    (repository_template / ".env.example").write_text(
        f"COMPOSE_PROJECT_NAME=xpeech\nBACKEND_PORT={value}\nWEB_CLIENT_PORT={value}\n",
        encoding="utf-8",
    )
    data = make_instance("demo01")
    assert data["backend_port"] is None
    assert data["web_client_port"] is None
    listed = client.get("/api/instances", headers=auth_headers).json()["instances"][0]
    assert listed["backend_port"] is None
    assert listed["web_client_port"] is None


def test_create_duplicate_conflict(client, auth_headers, make_instance):
    make_instance("demo01")
    r = client.post("/api/instances", json={"name": "demo01"}, headers=auth_headers)
    assert r.status_code == 409
    assert "已存在" in r.json()["detail"]


@pytest.mark.parametrize(
    "name",
    ["../demo", "demo/test", "demo test", ".demo", "-demo", "_demo", "a" * 64, ""],
)
def test_invalid_names_rejected(client, auth_headers, name):
    r = client.post("/api/instances", json={"name": name}, headers=auth_headers)
    assert r.status_code == 400
    assert r.json()["detail"]


@pytest.mark.parametrize("name", ["demo", "demo01", "demo-test", "demo_test", "a" * 63])
def test_valid_names_accepted(client, auth_headers, name):
    r = client.post("/api/instances", json={"name": name}, headers=auth_headers)
    assert r.status_code == 201, r.text


def test_path_traversal_does_not_escape(client, auth_headers, root_path):
    r = client.post("/api/instances", json={"name": "../escape"}, headers=auth_headers)
    assert r.status_code == 400
    assert not (root_path.parent / "escape").exists()


def test_list_instances(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    make_instance("demo02")

    # 非实例目录（缺少 .env 或 compose.yaml）不应出现在列表里
    (root_path / "not-an-instance").mkdir()

    r = client.get("/api/instances", headers=auth_headers)
    assert r.status_code == 200
    names = {i["name"] for i in r.json()["instances"]}
    assert names == {"demo01", "demo02"}


def test_list_instances_collects_all_port_variables(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    env = (
        'COMPOSE_PROJECT_NAME=demo01\n'
        '# IGNORED_PORT=1111\n'
        'BACKEND_PORT=8000 # backend\n'
        'WEB_CLIENT_PORT="9000"\n'
        "export METRICS_PORT='9100' # custom\n"
        'ADMIN_PORT=9200\n'
        'PORT=1234\n'
        'PORT_SUFFIX=2345\n'
        'OTHER=value\n'
        'EMPTY_PORT=\n'
        'QUOTED_EMPTY_PORT=""\n'
    )
    env_file = root_path / "demo01" / ".env"
    env_file.write_text(env, encoding="utf-8")
    original = env_file.read_bytes()

    response = client.get("/api/instances", headers=auth_headers)

    assert response.status_code == 200
    instance = response.json()["instances"][0]
    assert instance["ports"] == ["8000", "9000", "9100", "9200"]
    assert instance["backend_port"] == 8000
    assert instance["web_client_port"] == 9000
    assert env_file.read_bytes() == original


def test_list_instances_ports_only_use_values_present_in_env(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    env_file = root_path / "demo01" / ".env"
    env_file.write_text('COMPOSE_PROJECT_NAME=demo01\n', encoding="utf-8")
    assert client.get("/api/instances", headers=auth_headers).json()["instances"][0]["ports"] == []

    env_file.write_text(
        'COMPOSE_PROJECT_NAME=demo01\nCUSTOM_PORT=8123\n', encoding="utf-8"
    )
    assert client.get("/api/instances", headers=auth_headers).json()["instances"][0]["ports"] == ["8123"]
