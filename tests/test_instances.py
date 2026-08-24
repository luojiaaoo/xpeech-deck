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
    assert data["backend_port"] == 7878
    assert data["web_client_port"] == 7939
    assert data["path"] == str(root_path / "demo01")

    target = root_path / "demo01"
    assert target.is_dir()

    # 默认 .env 内容：Compose 项目名 = 实例名
    env = (target / ".env").read_text(encoding="utf-8")
    assert "COMPOSE_PROJECT_NAME=demo01" in env
    assert "BACKEND_PORT=7878" in env
    assert "WEB_CLIENT_PORT=7939" in env
    assert "CDP_URL=ws://browserless:3000" in env

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
