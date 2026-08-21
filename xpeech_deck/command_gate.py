"""平台级 Docker 命令互斥门闩。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from .errors import ConflictError


class CommandGate:
    """保证整个 Xpeech Deck 同一时间只运行一个 Docker 命令。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._label = ""

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    @property
    def label(self) -> str:
        return self._label

    @asynccontextmanager
    async def hold(self, label: str) -> AsyncIterator[None]:
        if self._lock.locked():
            current = f"：{self._label}" if self._label else ""
            raise ConflictError(f"当前有命令正在执行{current}，请稍后重试")
        await self._lock.acquire()
        self._label = label
        try:
            yield
        finally:
            self._label = ""
            self._lock.release()
