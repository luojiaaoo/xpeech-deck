"""平台级 Docker 命令锁测试。"""

from __future__ import annotations

import asyncio

import pytest

from xpeech_deck.command_gate import CommandGate
from xpeech_deck.compose_service import ComposeService
from xpeech_deck.errors import ConflictError
from xpeech_deck.image_service import ImageService


class FakeProcess:
    def __init__(self, *, release: asyncio.Event | None = None) -> None:
        self.release = release
        self.returncode = 0
        self.stdout = b""
        self.stderr = b""

    async def communicate(self):
        if self.release is not None:
            await self.release.wait()
        return b"", b""

    def kill(self) -> None:
        self.returncode = -9
        if self.release is not None:
            self.release.set()


async def test_different_instances_share_one_global_lock():
    gate = CommandGate()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def runner(cmd, cwd):
        entered.set()
        return FakeProcess(release=release)

    service = ComposeService(runner=runner, gate=gate)
    first = asyncio.create_task(service.run("demo01", "/instances/demo01", "up"))
    await entered.wait()

    with pytest.raises(ConflictError, match="demo01"):
        await service.run("demo02", "/instances/demo02", "ps")

    release.set()
    await first


async def test_compose_and_image_operations_share_one_global_lock():
    gate = CommandGate()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def compose_runner(cmd, cwd):
        entered.set()
        return FakeProcess(release=release)

    async def image_runner(cmd):
        return FakeProcess()

    compose = ComposeService(runner=compose_runner, gate=gate)
    images = ImageService(runner=image_runner, gate=gate)
    first = asyncio.create_task(compose.run("demo01", "/instances/demo01", "up"))
    await entered.wait()

    with pytest.raises(ConflictError, match="demo01"):
        await images.list_statuses()

    release.set()
    await first


async def test_global_lock_is_released_after_command():
    gate = CommandGate()

    async def runner(cmd, cwd):
        return FakeProcess()

    service = ComposeService(runner=runner, gate=gate)
    await service.run("demo01", "/instances/demo01", "ps")
    await service.run("demo02", "/instances/demo02", "ps")
    assert gate.busy is False


def test_application_services_use_same_gate(app):
    assert app.state.compose._gate is app.state.command_gate
    assert app.state.images._gate is app.state.command_gate
    assert app.state.git._gate is app.state.command_gate
