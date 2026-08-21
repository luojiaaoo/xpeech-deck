"""Compose 执行器与 Compose API 测试。"""

from __future__ import annotations

import asyncio

import pytest

from xpeech_deck.compose_service import ACTIONS, ComposeService
from xpeech_deck.errors import CommandTimeoutError, ConflictError


class FakeProcess:
    """模拟子进程：可配置输出、退出码、挂起行为。"""

    def __init__(
        self,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        hang: bool = False,
        release: asyncio.Event | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self._returncode = returncode
        self.hang = hang
        self.release = release
        self.killed = False

    @property
    def returncode(self) -> int:
        return self._returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        if self.hang and self.release is not None:
            await self.release.wait()
        if self.killed:
            self._returncode = -9
            return b"", b""
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True
        self._returncode = -9
        if self.release is not None:
            self.release.set()


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("up", ["docker", "compose", "up", "-d", "--build"]),
        ("start", ["docker", "compose", "start"]),
        ("stop", ["docker", "compose", "stop"]),
        ("restart", ["docker", "compose", "restart"]),
        ("down", ["docker", "compose", "down"]),
        ("ps", ["docker", "compose", "ps"]),
    ],
)
async def test_command_mapping(action, expected):
    captured: dict = {}

    async def runner(cmd, cwd):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return FakeProcess()

    svc = ComposeService(runner=runner)
    await svc.run("demo01", "/instances/demo01", action)
    assert captured["cmd"] == expected
    assert captured["cwd"] == "/instances/demo01"


async def test_no_shell_usage():
    """命令必须为参数列表，实例名/路径绝不拼进命令行。"""
    captured: dict = {}

    async def runner(cmd, cwd):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return FakeProcess()

    svc = ComposeService(runner=runner)
    await svc.run("demo; rm -rf /", "/x/demo; rm -rf /", "down")
    assert isinstance(captured["cmd"], list)
    assert all(isinstance(p, str) for p in captured["cmd"])
    assert captured["cmd"] == ["docker", "compose", "down"]
    assert captured["cwd"] == "/x/demo; rm -rf /"


async def test_output_and_exit_code():
    async def runner(cmd, cwd):
        return FakeProcess(stdout=b"stdout-text\n", stderr=b"stderr-text\n", returncode=1)

    svc = ComposeService(runner=runner)
    result = await svc.run("demo01", "/instances/demo01", "stop")
    assert result == {
        "success": False,
        "exit_code": 1,
        "stdout": "stdout-text\n",
        "stderr": "stderr-text\n",
    }


async def test_success_result():
    async def runner(cmd, cwd):
        return FakeProcess(stdout=b"Container Started\n", returncode=0)

    svc = ComposeService(runner=runner)
    result = await svc.run("demo01", "/instances/demo01", "up")
    assert result["success"] is True
    assert result["exit_code"] == 0
    assert result["stdout"] == "Container Started\n"


async def test_timeout_kills_process():
    async def runner(cmd, cwd):
        return FakeProcess(hang=True, release=asyncio.Event())

    svc = ComposeService(runner=runner, timeouts={"stop": 0.05})
    with pytest.raises(CommandTimeoutError):
        await svc.run("demo01", "/instances/demo01", "stop")


async def test_concurrent_same_instance_409():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def runner(cmd, cwd):
        entered.set()
        return FakeProcess(hang=True, release=release)

    svc = ComposeService(runner=runner)
    first = asyncio.create_task(svc.run("demo01", "/instances/demo01", "up"))
    await entered.wait()

    with pytest.raises(ConflictError):
        await svc.run("demo01", "/instances/demo01", "up")

    release.set()
    result = await first
    assert result["exit_code"] == 0  # 未被 kill，正常结束


async def test_unknown_action_rejected():
    svc = ComposeService()
    with pytest.raises(ConflictError):
        await svc.run("demo01", "/instances/demo01", "destroy")


def test_actions_timeout_table():
    """超时表与计划书一致。"""
    from xpeech_deck.compose_service import DEFAULT_TIMEOUTS

    assert DEFAULT_TIMEOUTS == {
        "up": 1800,
        "start": 300,
        "stop": 300,
        "restart": 300,
        "down": 300,
        "ps": 30,
    }
    assert set(ACTIONS) == set(DEFAULT_TIMEOUTS)


# ---------- API 层测试（用假 runner 替换 app.state.compose） ----------


def test_compose_endpoint_up(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    captured: dict = {}

    async def runner(cmd, cwd):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return FakeProcess(stdout=b"Container Started\n", returncode=0)

    client.app.state.compose = ComposeService(runner=runner)

    r = client.post("/api/instances/demo01/compose/up", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert data["stdout"] == "Container Started\n"
    assert captured["cmd"] == ["docker", "compose", "up", "-d", "--build"]
    assert captured["cwd"] == str(root_path / "demo01")


def test_compose_endpoint_ps(client, auth_headers, make_instance):
    make_instance("demo01")
    captured: dict = {}

    async def runner(cmd, cwd):
        captured["cmd"] = cmd
        return FakeProcess(stdout=b"NAME  STATE\n", returncode=0)

    client.app.state.compose = ComposeService(runner=runner)

    r = client.get("/api/instances/demo01/compose/ps", headers=auth_headers)
    assert r.status_code == 200
    assert captured["cmd"] == ["docker", "compose", "ps"]


def test_compose_failure_still_returns_result(client, auth_headers, make_instance):
    make_instance("demo01")

    async def runner(cmd, cwd):
        return FakeProcess(stderr=b"Bind for 0.0.0.0:7878 failed: port is already allocated", returncode=1)

    client.app.state.compose = ComposeService(runner=runner)

    r = client.post("/api/instances/demo01/compose/up", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is False
    assert data["exit_code"] == 1
    assert "port is already allocated" in data["stderr"]


def test_compose_missing_instance_404(client, auth_headers):
    r = client.post("/api/instances/ghost/compose/up", headers=auth_headers)
    assert r.status_code == 404
