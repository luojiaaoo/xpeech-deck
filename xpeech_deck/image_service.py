"""Docker 镜像状态检查与拉取。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .errors import CommandTimeoutError, ConflictError, NotFoundError
from .console_service import ConsoleBroker, communicate_with_console


@dataclass(frozen=True)
class ImageSpec:
    key: str
    label: str
    name: str


# Xpeech 当前模板直接依赖的两个远程镜像。
IMAGE_SPECS: tuple[ImageSpec, ...] = (
    ImageSpec(
        key="xpeech-base",
        label="Xpeech 基础镜像",
        name="docker.1panel.live/library/ubuntu:22.04",
    ),
    ImageSpec(
        key="browserless",
        label="Browserless 镜像",
        name="ghcr.io/browserless/chromium:v2.55.0",
    ),
)


class ImageService:
    """检查和拉取平台使用的 Docker 镜像。"""

    def __init__(
        self,
        runner: Callable[[list[str]], Awaitable[Any]] | None = None,
        *,
        inspect_timeout: int = 30,
        pull_timeout: int = 1800,
        console: ConsoleBroker | None = None,
    ) -> None:
        self._runner = runner or self._spawn
        self._inspect_timeout = inspect_timeout
        self._pull_timeout = pull_timeout
        self._locks = {spec.key: asyncio.Lock() for spec in IMAGE_SPECS}
        self._console = console

    async def _spawn(self, cmd: list[str]):
        return await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    @staticmethod
    def _spec(key: str) -> ImageSpec:
        for spec in IMAGE_SPECS:
            if spec.key == key:
                return spec
        raise NotFoundError(f"未知镜像：{key}")

    async def _execute(self, cmd: list[str], timeout: int) -> tuple[int, str, str]:
        target = cmd[-1]
        if self._console is not None:
            await self._console.command(cmd, source="image", target=target)
        try:
            proc = await self._runner(cmd)
        except Exception as exc:
            if self._console is not None:
                await self._console.publish("stderr", f"{exc}\n", source="image", target=target)
            raise
        try:
            stdout, stderr = await communicate_with_console(
                proc,
                timeout=timeout,
                console=self._console,
                source="image",
                target=target,
            )
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), 10)
                except Exception:
                    pass
            if self._console is not None:
                await self._console.publish("system", "镜像操作超时\n", source="image", target=target)
            raise CommandTimeoutError("镜像操作超时")
        if self._console is not None:
            await self._console.publish(
                "exit",
                f"进程退出，代码 {proc.returncode}\n",
                source="image",
                target=target,
                exit_code=proc.returncode,
            )
        return (
            int(proc.returncode),
            (stdout or b"").decode(errors="replace"),
            (stderr or b"").decode(errors="replace"),
        )

    async def inspect(self, key: str) -> dict[str, Any]:
        spec = self._spec(key)
        exit_code, stdout, stderr = await self._execute(
            ["docker", "image", "inspect", spec.name],
            self._inspect_timeout,
        )
        base = {
            "key": spec.key,
            "label": spec.label,
            "name": spec.name,
            "image_id": None,
            "size_bytes": None,
            "created_at": None,
        }
        if exit_code != 0:
            missing = "no such image" in stderr.lower()
            return {
                **base,
                "status": "missing" if missing else "error",
                "message": "" if missing else (stderr.strip() or "镜像状态检查失败"),
            }

        try:
            values = json.loads(stdout)
            detail = values[0] if isinstance(values, list) and values else {}
            image_id = str(detail.get("Id", "")).removeprefix("sha256:")
            return {
                **base,
                "status": "available",
                "image_id": image_id[:12] or None,
                "size_bytes": detail.get("Size"),
                "created_at": detail.get("Created"),
                "message": "",
            }
        except (json.JSONDecodeError, TypeError, AttributeError):
            return {**base, "status": "error", "message": "无法解析 Docker 镜像信息"}

    async def list_statuses(self) -> list[dict[str, Any]]:
        return await asyncio.gather(*(self.inspect(spec.key) for spec in IMAGE_SPECS))

    async def pull(self, key: str) -> dict[str, Any]:
        spec = self._spec(key)
        lock = self._locks[key]
        if lock.locked():
            raise ConflictError(f"{spec.label}正在拉取，请稍后重试")
        async with lock:
            exit_code, stdout, stderr = await self._execute(
                ["docker", "pull", spec.name],
                self._pull_timeout,
            )
            image = await self.inspect(key)
            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "image": image,
            }
