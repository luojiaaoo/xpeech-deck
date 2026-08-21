"""pytest 共享 fixture：构造假的实例源目录、根目录与测试客户端。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xpeech_deck.app import create_app
from xpeech_deck.config import Settings

TOKEN = "test-token"


def make_source(base: Path) -> Path:
    """构造一个最小化的 xpeech 源目录，含需要保留与需要忽略的内容。"""
    src = base / "source"
    src.mkdir()
    # 需要保留的源文件
    (src / ".env.example").write_text(
        "COMPOSE_PROJECT_NAME=xpeech\n"
        "# BACKEND_PORT=7878\n"
        "# WEB_CLIENT_PORT=7939\n"
        "CDP_URL=ws://browserless:3000\n",
        encoding="utf-8",
    )
    (src / "conf.toml.example").write_text(
        '[path]\nsession_path = "data/session"\n', encoding="utf-8"
    )
    (src / "compose.yaml").write_text(
        "services:\n  backend:\n    image: xpeech\n", encoding="utf-8"
    )
    (src / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (src / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (src / "custom_tools").mkdir()
    (src / "custom_tools" / "echo.py").write_text("def echo() -> None: ...\n", encoding="utf-8")

    # 复制时必须忽略的内容
    (src / ".env").write_text("SECRET=should-be-ignored\n", encoding="utf-8")
    (src / "conf.toml").write_text('token = "should-be-ignored"\n', encoding="utf-8")
    for d in (".git", ".venv", ".ruff_cache", "__pycache__", "node_modules", "docker_data"):
        (src / d).mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (src / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")
    return src


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    return make_source(tmp_path)


@pytest.fixture
def root_path(tmp_path: Path) -> Path:
    p = tmp_path / "instances"
    p.mkdir()
    return p


@pytest.fixture
def settings(root_path: Path, source_dir: Path) -> Settings:
    return Settings(token=TOKEN, root_path=root_path, source_dir=source_dir)


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def make_instance(client: TestClient, auth_headers: dict[str, str]):
    """创建一个实例并返回其响应 JSON。"""

    def _make(name: str = "demo01") -> dict:
        r = client.post("/api/instances", json={"name": name}, headers=auth_headers)
        assert r.status_code == 201, r.text
        return r.json()

    return _make
