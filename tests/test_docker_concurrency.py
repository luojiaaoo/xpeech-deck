"""Docker 请求不互斥：慢命令不阻塞其他 Compose 及日志请求。"""

from __future__ import annotations

import asyncio

import httpx
import pytest


class FakeProcess:
    def __init__(self, *, release: asyncio.Event | None = None, stdout: bytes = b""):
        self.release = release
        self.stdout = stdout
        self.returncode = 0

    async def communicate(self):
        if self.release is not None:
            await self.release.wait()
        return self.stdout, b""

    def kill(self):
        self.returncode = -9
        if self.release is not None:
            self.release.set()


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "/api/instances/demo01/compose/start"),
        ("POST", "/api/instances/demo02/compose/up"),
        ("GET", "/api/instances/demo01/compose/ps"),
        ("GET", "/api/instances/demo01/compose/services"),
        ("GET", "/api/instances/demo01/compose/logs/backend"),
    ],
)
async def test_docker_requests_complete_during_compose_up(
    app, auth_headers, make_instance, method, url
):
    make_instance("demo01")
    make_instance("demo02")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def compose_runner(cmd, cwd):
        if cmd[:3] == ["docker", "compose", "up"] and cwd.endswith("demo01"):
            entered.set()
            return FakeProcess(release=release)
        return FakeProcess(stdout=b"backend\n")

    app.state.compose._runner = compose_runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=auth_headers
    ) as client:
        first = asyncio.create_task(client.post("/api/instances/demo01/compose/up"))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            second = await asyncio.wait_for(client.request(method, url), 1)
            assert second.status_code == 200, second.text
            assert not first.done()
        finally:
            release.set()
            completed = await first
        assert completed.status_code == 200
        assert completed.json()["success"] is True
