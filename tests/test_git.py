"""Git fetch、版本列表与 reset --hard 切换测试。"""

from __future__ import annotations

import asyncio
import os
import subprocess

import pytest

from xpeech_deck.errors import CommandTimeoutError
from xpeech_deck.git_service import (
    GIT_NETWORK_OPTIONS,
    VERSION_HISTORY_LIMIT,
    GitService,
)

HEAD = "a" * 40
TAG_COMMIT = "b" * 40
REFS = (
    f"refs/remotes/origin/HEAD\t{HEAD}\t\trefs/remotes/origin/main\n"
    f"refs/remotes/origin/main\t{HEAD}\t\t\n"
    f"refs/tags/v1.0.0\t{'c' * 40}\t{TAG_COMMIT}\t\n"
)
LOG = (
    f"{HEAD}\t2026-08-24T09:00:00+08:00\tlatest commit\n"
    f"{TAG_COMMIT}\t2026-08-23T09:00:00+08:00\tprevious commit\n"
)


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.returncode = -9


async def test_clone_retries_transient_tls_failure(tmp_path):
    target = tmp_path / "demo01"
    target.mkdir()
    attempts = 0
    delays: list[float] = []

    async def runner(cmd, cwd):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return FakeProcess(
                stderr=b"fatal: TLS connect error: connection reset\n",
                returncode=128,
            )
        return FakeProcess()

    async def sleeper(delay):
        delays.append(delay)

    result = await GitService(runner=runner, sleeper=sleeper).clone(target)

    assert result["success"] is True
    assert attempts == 3
    assert delays == [1.0, 2.0]


async def test_clone_retries_ssl_read_early_eof(tmp_path):
    target = tmp_path / "demo01"
    target.mkdir()
    attempts = 0

    async def runner(cmd, cwd):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return FakeProcess(
                stderr=(
                    b"curl 56 OpenSSL SSL_read: SSL_ERROR_SYSCALL\n"
                    b"fatal: early EOF\n"
                    b"fatal: fetch-pack: invalid index-pack output\n"
                ),
                returncode=128,
            )
        return FakeProcess()

    async def sleeper(delay):
        return None

    result = await GitService(runner=runner, sleeper=sleeper).clone(target)

    assert result["success"] is True
    assert attempts == 2


async def test_clone_does_not_retry_non_network_failure(tmp_path):
    target = tmp_path / "demo01"
    target.mkdir()
    attempts = 0

    async def runner(cmd, cwd):
        nonlocal attempts
        attempts += 1
        return FakeProcess(stderr=b"repository not found\n", returncode=128)

    result = await GitService(runner=runner).clone(target)

    assert result["success"] is False
    assert attempts == 1


def test_fetch_all_instances_api(client, auth_headers, make_instance):
    make_instance("demo01")
    commands: list[tuple[list[str], str]] = []

    async def runner(cmd, cwd):
        commands.append((cmd, cwd))
        return FakeProcess(stderr=b"updated\n")

    client.app.state.git = GitService(runner=runner)
    response = client.post("/api/instances/fetch", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "demo01"
    assert commands[0][0] == [
        "git",
        *GIT_NETWORK_OPTIONS,
        "fetch",
        f"--depth={VERSION_HISTORY_LIMIT}",
        "--all",
        "--prune",
        "--tags",
    ]


def test_failed_clone_removes_reserved_directory(client, auth_headers, root_path):
    async def runner(cmd, cwd):
        return FakeProcess(stderr=b"repository unavailable\n", returncode=1)

    client.app.state.git = GitService(runner=runner)
    response = client.post(
        "/api/instances", json={"name": "broken"}, headers=auth_headers
    )

    assert response.status_code == 500
    assert "repository unavailable" in response.json()["detail"]
    assert not (root_path / "broken").exists()


def test_versions_and_reset_hard_api(client, auth_headers, make_instance):
    make_instance("demo01")
    commands: list[list[str]] = []

    async def runner(cmd, cwd):
        commands.append(cmd)
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            # reset 后返回 tag 指向的 commit。
            head = TAG_COMMIT if any(item[:3] == ["git", "reset", "--hard"] for item in commands) else HEAD
            return FakeProcess(stdout=f"{head}\n".encode())
        if cmd[:2] == ["git", "for-each-ref"] and any(arg.startswith("--contains=") for arg in cmd):
            return FakeProcess(stdout=b"refs/remotes/origin/main\t\n")
        if cmd[:2] == ["git", "for-each-ref"]:
            return FakeProcess(stdout=REFS.encode())
        if cmd[:2] == ["git", "log"]:
            return FakeProcess(stdout=LOG.encode())
        if cmd[:3] == ["git", "reset", "--hard"]:
            return FakeProcess(stdout=b"HEAD is now at bbbbbbbbbbbb\n")
        raise AssertionError(cmd)

    client.app.state.git = GitService(runner=runner)

    versions = client.get("/api/instances/demo01/versions", headers=auth_headers)
    assert versions.status_code == 200
    assert versions.json()["current_label"] == "origin/main"
    assert all(item["branches"] == ["origin/main"] for item in versions.json()["versions"])
    assert [item["label"] for item in versions.json()["versions"]] == [
        "origin/main",
        "v1.0.0",
        "latest commit",
        "previous commit",
    ]

    switched = client.post(
        "/api/instances/demo01/version",
        json={"ref": "refs/tags/v1.0.0"},
        headers=auth_headers,
    )
    assert switched.status_code == 200
    assert switched.json()["current_label"] == "v1.0.0"
    assert ["git", "reset", "--hard", "refs/tags/v1.0.0"] in commands


def test_switch_rejects_unknown_ref(client, auth_headers, make_instance):
    make_instance("demo01")

    async def runner(cmd, cwd):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return FakeProcess(stdout=f"{HEAD}\n".encode())
        if cmd[:2] == ["git", "for-each-ref"] and any(arg.startswith("--contains=") for arg in cmd):
            return FakeProcess(stdout=b"refs/remotes/origin/main\t\n")
        if cmd[:2] == ["git", "for-each-ref"]:
            return FakeProcess(stdout=REFS.encode())
        if cmd[:2] == ["git", "log"]:
            return FakeProcess(stdout=LOG.encode())
        raise AssertionError("reset 不应被执行")

    client.app.state.git = GitService(runner=runner)
    response = client.post(
        "/api/instances/demo01/version",
        json={"ref": "--keep"},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_fetch_one_instance_api(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    make_instance("demo02")
    commands = []

    async def runner(cmd, cwd):
        commands.append((cmd, cwd))
        return FakeProcess(stderr=b"updated\n")

    client.app.state.git = GitService(runner=runner)
    response = client.post("/api/instances/demo02/fetch", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["name"] == "demo02"
    assert len(commands) == 1
    assert commands[0][1] == str(root_path / "demo02")
    assert "fetch" in commands[0][0]
    assert not any("reset" in cmd for cmd, _ in commands)


def test_fetch_one_requires_auth_and_existing_instance(client, auth_headers):
    assert client.post("/api/instances/missing/fetch").status_code == 401
    assert client.post("/api/instances/missing/fetch", headers=auth_headers).status_code == 404


@pytest.mark.parametrize("timeout", [False, True])
def test_fetch_one_reports_failure(client, auth_headers, make_instance, timeout):
    make_instance("demo01")

    async def runner(cmd, cwd):
        if timeout:
            raise CommandTimeoutError("Git 操作超时")
        return FakeProcess(stderr=b"network unavailable", returncode=128)

    client.app.state.git = GitService(runner=runner)
    response = client.post("/api/instances/demo01/fetch", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["exit_code"] == (124 if timeout else 128)
    assert response.json()["stderr"]


async def test_git_operations_run_concurrently(tmp_path):
    (tmp_path / ".git").mkdir()

    async def runner(cmd, cwd):
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            return FakeProcess(stdout=f"{HEAD}\n".encode())
        if cmd[:2] == ["git", "log"]:
            return FakeProcess(stdout=LOG.encode())
        if any(arg.startswith("--contains=") for arg in cmd):
            return FakeProcess(stdout=b"refs/remotes/origin/main\t\n")
        if cmd[:2] == ["git", "for-each-ref"]:
            return FakeProcess(stdout=REFS.encode())
        return FakeProcess()

    service = GitService(runner=runner)
    results = await asyncio.gather(
        service.clone(tmp_path / "clone"),
        service.fetch_all([("demo01", tmp_path)]),
        service.versions("demo01", tmp_path),
        service.switch("demo01", tmp_path, "refs/remotes/origin/main"),
    )
    assert results[0]["success"]
    assert results[1][0]["success"]
    assert results[2]["current_label"] == "origin/main"
    assert results[3]["success"]


async def test_real_repository_commit_branch_membership(tmp_path):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args):
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
            cwd=tmp_path, env=env, capture_output=True, text=True, check=True,
        ).stdout.strip()

    git("init", "-b", "main")
    git("commit", "--allow-empty", "-m", "shared commit")
    shared = git("rev-parse", "HEAD")
    git("tag", "-a", "v1", "-m", "release")
    git("checkout", "-b", "feature")
    git("commit", "--allow-empty", "-m", "feature commit")
    feature = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/feature", feature)
    git("checkout", "main")
    git("commit", "--allow-empty", "-m", "main commit")
    main = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", main)
    git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    data = await GitService().versions("demo01", tmp_path)
    commits = {item["ref"]: item for item in data["versions"] if item["kind"] == "commit"}
    assert commits[shared]["branches"] == ["origin/feature", "origin/main"]
    assert commits[feature]["branches"] == ["origin/feature"]
    assert commits[main]["branches"] == ["origin/main"]
    tag = next(item for item in data["versions"] if item["kind"] == "tag")
    assert tag["branches"] == ["origin/feature", "origin/main"]
    assert not any(item["label"] == "origin/HEAD" for item in data["versions"])
