"""Compose 命令执行器：同步等待、超时控制、同实例互斥。"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

from .errors import CommandTimeoutError, ConflictError, ValidationError
from .console_service import ConsoleBroker, communicate_with_console
from .command_gate import CommandGate

# 操作名 -> 命令参数（禁止 shell=True，参数以列表传递，防止注入）
ACTIONS: dict[str, list[str]] = {
    "up": ["docker", "compose", "up", "-d", "--build"],
    "start": ["docker", "compose", "start"],
    "stop": ["docker", "compose", "stop"],
    "restart": ["docker", "compose", "restart"],
    "down": ["docker", "compose", "down"],
    "ps": ["docker", "compose", "ps"],
}

SERVICES_COMMAND = ["docker", "compose", "config", "--services"]
LOG_TAIL_LINES = 500
SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# 各操作的超时时间（秒）
DEFAULT_TIMEOUTS: dict[str, int] = {
    "up": 1800,  # 30 分钟：构建镜像耗时较长
    "start": 300,
    "stop": 300,
    "restart": 300,
    "down": 300,
    "ps": 30,
    "services": 30,
    "logs": 30,
}


class ComposeService:
    """统一的 Compose 命令执行器，所有实例共用平台级命令锁。"""

    def __init__(
        self,
        runner: Callable[[list[str], str], Awaitable] | None = None,
        timeouts: dict[str, int] | None = None,
        console: ConsoleBroker | None = None,
        gate: CommandGate | None = None,
    ) -> None:
        self._runner = runner or self._spawn
        self._timeouts: dict[str, int] = {**DEFAULT_TIMEOUTS, **(timeouts or {})}
        self._console = console
        self._gate = gate or CommandGate()

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
        async with self._gate.hold(f"实例 {name}：docker compose {action}"):
            return await self._execute(ACTIONS[action], path, self._timeouts[action])

    async def list_services(self, name: str, path: str) -> dict:
        async with self._gate.hold(f"实例 {name}：读取 Compose 服务列表"):
            result = await self._execute(
                SERVICES_COMMAND,
                path,
                self._timeouts["services"],
            )
        services = (
            [line.strip() for line in result["stdout"].splitlines() if line.strip()]
            if result["success"]
            else []
        )
        return {**result, "services": services}

    async def logs(self, name: str, path: str, service: str) -> dict:
        if not SERVICE_NAME_PATTERN.fullmatch(service):
            raise ValidationError("非法的 Compose 服务名")
        cmd = [
            "docker",
            "compose",
            "logs",
            "-n",
            str(LOG_TAIL_LINES),
            service,
        ]
        async with self._gate.hold(f"实例 {name}：查看 {service} 日志"):
            return await self._execute(cmd, path, self._timeouts["logs"])

    async def _execute(self, cmd: list[str], cwd: str, timeout: int) -> dict:
        if self._console is not None:
            await self._console.command(cmd, source="compose", target=cwd, cwd=cwd)
        try:
            proc = await self._runner(cmd, cwd)
        except OSError as exc:
            message = f"无法启动 Docker 命令：{exc}"
            if self._console is not None:
                await self._console.publish(
                    "stderr",
                    f"{message}\n",
                    source="compose",
                    target=cwd,
                    cwd=cwd,
                )
            return {
                "success": False,
                "exit_code": 127,
                "stdout": "",
                "stderr": message,
            }
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
