"""Xpeech Git 仓库克隆、更新与版本切换。"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .command_gate import CommandGate
from .console_service import ConsoleBroker
from .errors import CommandTimeoutError, FileOperationError, ValidationError

XPEECH_REPOSITORY_URL = "https://gitee.com/luojiaaoo/xpeech.git"
VERSION_HISTORY_LIMIT = 20
GIT_NETWORK_OPTIONS = [
    "-c",
    "http.sslVersion=tlsv1.2",
    "-c",
    "http.version=HTTP/1.1",
]


class GitService:
    """所有 Git 子进程的统一执行器。"""

    def __init__(
        self,
        runner: Callable[[list[str], str], Awaitable[Any]] | None = None,
        *,
        console: ConsoleBroker | None = None,
        gate: CommandGate | None = None,
        clone_timeout: int = 1800,
        fetch_timeout: int = 300,
        command_timeout: int = 30,
        clone_attempts: int = 3,
        sleeper: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    ) -> None:
        self._runner = runner or self._spawn
        self._console = console
        self._gate = gate or CommandGate()
        self._clone_timeout = clone_timeout
        self._fetch_timeout = fetch_timeout
        self._command_timeout = command_timeout
        self._clone_attempts = max(1, clone_attempts)
        self._sleeper = sleeper

    async def _spawn(self, cmd: list[str], cwd: str):
        return await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def _execute(self, cmd: list[str], cwd: str, timeout: int) -> dict:
        target = cwd
        if self._console is not None:
            await self._console.command(cmd, source="git", target=target, cwd=cwd)
        try:
            proc = await self._runner(cmd, cwd)
        except OSError as exc:
            if self._console is not None:
                await self._console.publish(
                    "stderr", f"{exc}\n", source="git", target=target, cwd=cwd
                )
            return {
                "success": False,
                "exit_code": 127,
                "stdout": "",
                "stderr": str(exc),
            }

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
                try:
                    await asyncio.wait_for(proc.communicate(), 10)
                except Exception:
                    pass
            if self._console is not None:
                await self._console.publish(
                    "system", "Git 操作超时\n", source="git", target=target, cwd=cwd
                )
            raise CommandTimeoutError("Git 操作超时")

        stdout = stdout or b""
        stderr = stderr or b""
        if self._console is not None:
            if stdout:
                await self._console.publish(
                    "stdout",
                    stdout.decode(errors="replace"),
                    source="git",
                    target=target,
                    cwd=cwd,
                )
            if stderr:
                await self._console.publish(
                    "stderr",
                    stderr.decode(errors="replace"),
                    source="git",
                    target=target,
                    cwd=cwd,
                )
        if self._console is not None:
            await self._console.publish(
                "exit",
                f"进程退出，代码 {proc.returncode}\n",
                source="git",
                target=target,
                cwd=cwd,
                exit_code=proc.returncode,
            )
        return {
            "success": proc.returncode == 0,
            "exit_code": int(proc.returncode),
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }

    @staticmethod
    def _is_transient_network_failure(result: dict) -> bool:
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
        markers = (
            "tls connect error",
            "ssl_error_syscall",
            "failed to connect",
            "could not resolve host",
            "connection reset",
            "connection timed out",
            "operation timed out",
            "remote end hung up unexpectedly",
            "unexpected disconnect",
            "early eof",
            "invalid index-pack output",
        )
        return any(marker in output for marker in markers)

    @staticmethod
    def _clear_clone_target(target: Path) -> None:
        """清理本次克隆留下的半成品，保留已原子占位的目标目录。"""
        for child in target.iterdir():
            if child.is_symlink() or child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

    async def clone(self, target: Path) -> dict:
        async with self._gate.hold(f"克隆实例：{target.name}"):
            result: dict = {}
            for attempt in range(1, self._clone_attempts + 1):
                result = await self._execute(
                    [
                        "git",
                        *GIT_NETWORK_OPTIONS,
                        "clone",
                        "--depth",
                        str(VERSION_HISTORY_LIMIT),
                        "--no-single-branch",
                        XPEECH_REPOSITORY_URL,
                        str(target),
                    ],
                    str(target.parent),
                    self._clone_timeout,
                )
                if result["success"] or not self._is_transient_network_failure(result):
                    return result
                if attempt == self._clone_attempts:
                    result["stderr"] = (
                        f"{result['stderr'].rstrip()}\n"
                        f"Gitee 网络连接在 {self._clone_attempts} 次尝试后仍失败，"
                        "请检查 WSL 的 HTTP_PROXY/HTTPS_PROXY 或稍后重试。"
                    )
                    return result

                try:
                    self._clear_clone_target(target)
                except OSError as exc:
                    result["stderr"] = (
                        f"{result['stderr'].rstrip()}\n清理克隆半成品失败：{exc}"
                    )
                    return result
                delay = float(attempt)
                if self._console is not None:
                    await self._console.publish(
                        "system",
                        f"克隆网络失败（{attempt}/{self._clone_attempts}），"
                        f"{delay:g} 秒后重试\n",
                        source="git",
                        target=str(target),
                        cwd=str(target.parent),
                    )
                await self._sleeper(delay)
            return result

    async def fetch_all(self, instances: list[tuple[str, Path]]) -> list[dict]:
        async with self._gate.hold("更新全部实例 Git 引用"):
            results: list[dict] = []
            for name, path in instances:
                if not (path / ".git").exists():
                    results.append(
                        {
                            "name": name,
                            "success": False,
                            "exit_code": 128,
                            "stdout": "",
                            "stderr": "实例不是 Git 仓库",
                        }
                    )
                    continue
                try:
                    result = await self._execute(
                        [
                            "git",
                            *GIT_NETWORK_OPTIONS,
                            "fetch",
                            f"--depth={VERSION_HISTORY_LIMIT}",
                            "--all",
                            "--prune",
                            "--tags",
                        ],
                        str(path),
                        self._fetch_timeout,
                    )
                except CommandTimeoutError as exc:
                    result = {
                        "success": False,
                        "exit_code": 124,
                        "stdout": "",
                        "stderr": exc.message,
                    }
                results.append({"name": name, **result})
            return results

    @staticmethod
    def _parse_versions(stdout: str, head: str) -> list[dict]:
        versions: list[dict] = []
        for line in stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            ref, object_name, peeled_name, symbolic_ref = parts
            if symbolic_ref or ref == "refs/remotes/origin/HEAD":
                continue
            commit = peeled_name or object_name
            if ref.startswith("refs/remotes/origin/"):
                label = ref.removeprefix("refs/remotes/")
                kind = "branch"
                order = 0
            elif ref.startswith("refs/tags/"):
                label = ref.removeprefix("refs/tags/")
                kind = "tag"
                order = 1
            else:
                continue
            versions.append(
                {
                    "ref": ref,
                    "label": label,
                    "kind": kind,
                    "commit": commit[:12],
                    "_order": order,
                    "_current": commit == head,
                }
            )
        versions.sort(key=lambda item: (item["_order"], item["label"].lower()))
        return versions

    @staticmethod
    def _parse_commits(stdout: str, head: str) -> list[dict]:
        commits: list[dict] = []
        for line in stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            commit, committed_at, subject = parts
            commits.append(
                {
                    "ref": commit,
                    "label": subject or commit[:12],
                    "kind": "commit",
                    "commit": commit[:12],
                    "committed_at": committed_at,
                    "_order": 2,
                    "_current": commit == head,
                }
            )
        return commits

    async def _versions_unlocked(self, path: Path) -> dict:
        if not (path / ".git").exists():
            raise FileOperationError("实例不是 Git 仓库")

        head_result = await self._execute(
            ["git", "rev-parse", "HEAD"], str(path), self._command_timeout
        )
        if not head_result["success"]:
            detail = head_result["stderr"].strip() or "无法读取当前版本"
            raise FileOperationError(detail)
        head = head_result["stdout"].strip()

        refs_result = await self._execute(
            [
                "git",
                "for-each-ref",
                "--format=%(refname)%09%(objectname)%09%(*objectname)%09%(symref)",
                "refs/remotes/origin",
                "refs/tags",
            ],
            str(path),
            self._command_timeout,
        )
        if not refs_result["success"]:
            detail = refs_result["stderr"].strip() or "无法读取可用版本"
            raise FileOperationError(detail)

        history_result = await self._execute(
            [
                "git",
                "log",
                "--all",
                f"--max-count={VERSION_HISTORY_LIMIT}",
                "--date-order",
                "--format=%H%x09%cI%x09%s",
            ],
            str(path),
            self._command_timeout,
        )
        if not history_result["success"]:
            detail = history_result["stderr"].strip() or "无法读取提交历史"
            raise FileOperationError(detail)

        versions = self._parse_versions(refs_result["stdout"], head)
        versions.extend(self._parse_commits(history_result["stdout"], head))
        current = next((item for item in versions if item["_current"]), None)
        clean_versions = [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in versions
        ]
        return {
            "current_ref": current["ref"] if current else head,
            "current_label": current["label"] if current else head[:12],
            "current_commit": head[:12],
            "versions": clean_versions,
        }

    async def versions(self, name: str, path: Path) -> dict:
        async with self._gate.hold(f"读取实例 {name} 版本"):
            return await self._versions_unlocked(path)

    async def switch(self, name: str, path: Path, ref: str) -> dict:
        async with self._gate.hold(f"切换实例 {name} 版本"):
            version_data = await self._versions_unlocked(path)
            allowed_refs = {item["ref"] for item in version_data["versions"]}
            if ref not in allowed_refs:
                raise ValidationError("版本不存在，请 fetch 后重试")

            result = await self._execute(
                ["git", "reset", "--hard", ref], str(path), self._command_timeout
            )
            if not result["success"]:
                detail = (
                    result["stderr"].strip()
                    or result["stdout"].strip()
                    or "未知错误"
                )
                raise FileOperationError(f"切换版本失败：{detail}")
            current = await self._versions_unlocked(path)
            current_fields = {
                key: current[key]
                for key in ("current_ref", "current_label", "current_commit")
            }
            return {**result, **current_fields}
