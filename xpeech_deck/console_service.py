"""系统控制台：持久化并实时广播外部命令输出。"""

from __future__ import annotations

import asyncio
import json
import shlex
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

ConsoleKind = Literal["command", "stdout", "stderr", "exit", "system"]
CONSOLE_HISTORY_LIMIT = 200


class ConsoleBroker:
    """将控制台事件按 JSONL 追加到文件，并广播给在线页面。"""

    def __init__(self, log_path: Path | None = None) -> None:
        self._log_path = log_path
        # 未指定文件时保留内存模式，便于独立使用和单元测试。
        self._events: list[dict[str, Any]] = []
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = self._read_last_sequence()

    @property
    def log_path(self) -> Path | None:
        return self._log_path

    @staticmethod
    def _decode_line(line: str) -> dict[str, Any] | None:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(event, dict) or not isinstance(event.get("sequence"), int):
            return None
        return event

    def _read_last_sequence(self) -> int:
        if self._log_path is None or not self._log_path.is_file():
            return 0
        last_sequence = 0
        try:
            with self._log_path.open("r", encoding="utf-8") as log_file:
                for line in log_file:
                    event = self._decode_line(line)
                    if event is not None:
                        last_sequence = max(last_sequence, event["sequence"])
        except OSError:
            return 0
        return last_sequence

    def _append(self, event: dict[str, Any]) -> None:
        if self._log_path is None:
            self._events.append(event)
            return
        try:
            with self._log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
                log_file.write("\n")
        except OSError:
            # 日志文件短暂不可写时不阻断命令，本进程内暂存该事件。
            self._events.append(event)

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
        self._append(event)
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

    def snapshot(self, limit: int | None = None) -> list[dict[str, Any]]:
        if self._log_path is None:
            events = list(self._events)
            return events[-limit:] if limit is not None else events

        events: list[dict[str, Any]] = []
        if self._log_path.is_file():
            try:
                with self._log_path.open("r", encoding="utf-8") as log_file:
                    for line in log_file:
                        event = self._decode_line(line)
                        if event is not None:
                            events.append(event)
            except OSError:
                pass
        events.extend(self._events)
        events.sort(key=lambda event: event["sequence"])
        return events[-limit:] if limit is not None else events

    async def subscribe(self) -> AsyncIterator[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        # 只在前端打开 Console 建立订阅时从文件读取历史。
        history = self.snapshot(limit=CONSOLE_HISTORY_LIMIT)
        self._subscribers.add(queue)
        try:
            for event in history:
                yield event
            history.clear()
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
