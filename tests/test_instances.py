"""实例创建与发现测试。"""

from __future__ import annotations

import pytest


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

    # 复制时忽略的内容
    for ignored in (".git", ".venv", ".ruff_cache", "__pycache__", "node_modules", "docker_data"):
        assert not (target / ignored).exists(), f"{ignored} 应被忽略"

    # 原 .env / conf.toml 中的密钥不得带入实例
    assert "SECRET" not in env
    conf = (target / "conf.toml").read_text(encoding="utf-8")
    assert "should-be-ignored" not in conf

    # 源文件保持原样
    assert (target / "compose.yaml").is_file()
    assert (target / "Dockerfile").is_file()
    assert (target / "main.py").is_file()
    assert (target / "custom_tools" / "echo.py").is_file()
    assert (target / "conf.toml").is_file()
    assert (target / ".env.example").is_file()


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
