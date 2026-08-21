"""进程内系统控制台：缓存并实时广播 Docker 命令输出。"""

from __future__ import annotations

import asyncio
import shlex
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

ConsoleKind = Literal["command", "stdout", "stderr", "exit", "system"]


class ConsoleBroker:
    """保存本次进程运行期间的控制台事件，并广播给在线页面。"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._sequence = 0

    async def publish(
        self,
        kind: ConsoleKind,
        text: str,
        *,
        source: str,
        target: str = "",
        cwd: str = "",
        exit_code: int | None = None,
    ) -> None:
        if not text and kind in {"stdout", "stderr"}:
            return
        self._sequence += 1
        event = {
            "sequence": self._sequence,
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": kind,
            "source": source,
            "target": target,
            "cwd": cwd,
            "text": text,
            "exit_code": exit_code,
        }
        self._events.append(event)
        for queue in tuple(self._subscribers):
            queue.put_nowait(event)

    async def command(
        self,
        cmd: list[str],
        *,
        source: str,
        target: str = "",
        cwd: str = "",
    ) -> None:
        await self.publish(
            "command",
            f"$ {shlex.join(cmd)}",
            source=source,
            target=target,
            cwd=cwd,
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._events)

    async def subscribe(self) -> AsyncIterator[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        history = list(self._events)
        self._subscribers.add(queue)
        try:
            for event in history:
                yield event
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield None
        finally:
            self._subscribers.discard(queue)


async def communicate_with_console(
    proc: Any,
    *,
    timeout: int,
    console: ConsoleBroker | None,
    source: str,
    target: str = "",
    cwd: str = "",
) -> tuple[bytes, bytes]:
    """实时读取真实子进程；测试假进程则兼容原 communicate 接口。"""

    stdout_stream = getattr(proc, "stdout", None)
    stderr_stream = getattr(proc, "stderr", None)
    can_stream = hasattr(stdout_stream, "read") and hasattr(stderr_stream, "read")

    async def publish(kind: Literal["stdout", "stderr"], data: bytes) -> None:
        if console is not None and data:
            await console.publish(
                kind,
                data.decode(errors="replace"),
                source=source,
                target=target,
                cwd=cwd,
            )

    if not can_stream:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        stdout = stdout or b""
        stderr = stderr or b""
        await publish("stdout", stdout)
        await publish("stderr", stderr)
        return stdout, stderr

    async def pump(stream: Any, kind: Literal["stdout", "stderr"]) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
            await publish(kind, chunk)
        return b"".join(chunks)

    async def stream_all() -> tuple[bytes, bytes]:
        stdout_task = asyncio.create_task(pump(stdout_stream, "stdout"))
        stderr_task = asyncio.create_task(pump(stderr_stream, "stderr"))
        try:
            await proc.wait()
            return await asyncio.gather(stdout_task, stderr_task)
        except BaseException:
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise

    return await asyncio.wait_for(stream_all(), timeout)
