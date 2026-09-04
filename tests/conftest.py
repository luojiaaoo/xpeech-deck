"""pytest 共享 fixture：构造假的 Git 仓库、实例根目录与测试客户端。"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xpeech_deck.app import create_app
from xpeech_deck.config import Settings
from xpeech_deck.git_service import GitService

TOKEN = "test-token"


def make_repository_template(base: Path) -> Path:
    """构造一个最小化的 xpeech Git 仓库模板。"""
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

    # 克隆后应保留 Git 元数据，本地配置由平台生成。
    for d in (".git", ".venv", ".ruff_cache", "__pycache__", "node_modules", "docker_data"):
        (src / d).mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (src / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\x00")
    return src


@pytest.fixture
def repository_template(tmp_path: Path) -> Path:
    return make_repository_template(tmp_path)


@pytest.fixture
def root_path(tmp_path: Path) -> Path:
    p = tmp_path / "instances"
    p.mkdir()
    return p


@pytest.fixture
def settings(root_path: Path) -> Settings:
    return Settings(
        token=TOKEN,
        root_path=root_path,
        console_log_path=root_path.parent / "console.jsonl",
        global_config_path=root_path.parent / "global_config.json",
    )


@pytest.fixture
def app(settings: Settings, repository_template: Path):
    application = create_app(settings)
    git_commands: list[tuple[list[str], str]] = []

    class FakeProcess:
        returncode = 0
        stdout = b""
        stderr = b""

        async def communicate(self):
            return self.stdout, self.stderr

        def kill(self) -> None:
            self.returncode = -9

    async def git_runner(cmd: list[str], cwd: str):
        git_commands.append((cmd, cwd))
        if "clone" in cmd:
            shutil.copytree(repository_template, Path(cmd[-1]), dirs_exist_ok=True)
        return FakeProcess()

    application.state.git = GitService(
        runner=git_runner,
        console=application.state.console,
        gate=application.state.command_gate,
    )
    application.state.test_git_commands = git_commands
    return application


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
