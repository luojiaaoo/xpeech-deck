"""Compose 命令执行器：同步等待、超时控制、同实例互斥。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .errors import CommandTimeoutError, ConflictError
from .console_service import ConsoleBroker, communicate_with_console

# 操作名 -> 命令参数（禁止 shell=True，参数以列表传递，防止注入）
ACTIONS: dict[str, list[str]] = {
    "up": ["docker", "compose", "up", "-d", "--build"],
    "start": ["docker", "compose", "start"],
    "stop": ["docker", "compose", "stop"],
    "restart": ["docker", "compose", "restart"],
    "down": ["docker", "compose", "down"],
    "ps": ["docker", "compose", "ps"],
}

# 各操作的超时时间（秒）
DEFAULT_TIMEOUTS: dict[str, int] = {
    "up": 1800,  # 30 分钟：构建镜像耗时较长
    "start": 300,
    "stop": 300,
    "restart": 300,
    "down": 300,
    "ps": 30,
}


class ComposeService:
    """统一的 Compose 命令执行器。

    runner 可注入以便测试；每个实例一把 asyncio.Lock，保证同一实例
    同一时间只执行一个命令，重复请求返回 409。
    """

    def __init__(
        self,
        runner: Callable[[list[str], str], Awaitable] | None = None,
        timeouts: dict[str, int] | None = None,
        console: ConsoleBroker | None = None,
    ) -> None:
        self._runner = runner or self._spawn
        self._timeouts: dict[str, int] = {**DEFAULT_TIMEOUTS, **(timeouts or {})}
        self._locks: dict[str, asyncio.Lock] = {}
        self._console = console

    async def _spawn(self, cmd: list[str], cwd: str):
        return await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def run(self, name: str, path: str, action: str) -> dict:
        if action not in ACTIONS:
            raise ConflictError(f"不支持的操作：{action}")
        lock = self._locks.setdefault(name, asyncio.Lock())
        if lock.locked():
            raise ConflictError(f"实例 {name} 正在执行命令，请稍后重试")
        async with lock:
            return await self._execute(ACTIONS[action], path, self._timeouts[action])

    async def _execute(self, cmd: list[str], cwd: str, timeout: int) -> dict:
        if self._console is not None:
            await self._console.command(cmd, source="compose", target=cwd, cwd=cwd)
        try:
            proc = await self._runner(cmd, cwd)
        except Exception as exc:
            if self._console is not None:
                await self._console.publish("stderr", f"{exc}\n", source="compose", target=cwd, cwd=cwd)
            raise
        try:
            stdout, stderr = await communicate_with_console(
                proc,
                timeout=timeout,
                console=self._console,
                source="compose",
                target=cwd,
                cwd=cwd,
            )
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), 10)
                except Exception:
                    pass
            if self._console is not None:
                await self._console.publish("system", "命令执行超时\n", source="compose", target=cwd, cwd=cwd)
            raise CommandTimeoutError("命令执行超时")
        if self._console is not None:
            await self._console.publish(
                "exit",
                f"进程退出，代码 {proc.returncode}\n",
                source="compose",
                target=cwd,
                cwd=cwd,
                exit_code=proc.returncode,
            )
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (stdout or b"").decode(errors="replace"),
            "stderr": (stderr or b"").decode(errors="replace"),
        }
