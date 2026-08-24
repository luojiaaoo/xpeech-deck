"""系统 Console 事件缓存、广播和命令接入测试。"""

from __future__ import annotations

import asyncio
import json

from xpeech_deck.compose_service import ComposeService
from xpeech_deck.console_service import ConsoleBroker, communicate_with_console


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.returncode = -9


class StreamingProcess:
    def __init__(self) -> None:
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.returncode: int | None = None

    async def wait(self) -> int:
        self.stdout.feed_data(b"step 1\n")
        await asyncio.sleep(0)
        self.stderr.feed_data(b"warning\n")
        self.stdout.feed_data(b"step 2\n")
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.returncode = -9


async def test_console_replays_history_then_streams_new_events():
    console = ConsoleBroker()
    await console.publish("stdout", "before\n", source="compose")
    subscription = console.subscribe()

    first = await anext(subscription)
    assert first is not None
    assert first["text"] == "before\n"

    await console.publish("stderr", "after\n", source="image")
    second = await anext(subscription)
    assert second is not None
    assert second["text"] == "after\n"
    await subscription.aclose()


async def test_file_backed_console_persists_across_process_restart(tmp_path):
    log_path = tmp_path / "logs" / "console.jsonl"
    first_process = ConsoleBroker(log_path=log_path)
    await first_process.publish("stdout", "before restart\n", source="compose")

    assert first_process._events == []
    assert log_path.is_file()
    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert records[0]["sequence"] == 1

    second_process = ConsoleBroker(log_path=log_path)
    assert second_process.snapshot()[0]["text"] == "before restart\n"
    await second_process.publish("stderr", "after restart\n", source="git")

    history = second_process.snapshot()
    assert [event["sequence"] for event in history] == [1, 2]
    assert [event["text"] for event in history] == [
        "before restart\n",
        "after restart\n",
    ]


async def test_file_backed_console_ignores_malformed_lines(tmp_path):
    log_path = tmp_path / "console.jsonl"
    log_path.write_text(
        '{"sequence":7,"text":"valid","kind":"stdout","source":"git"}\n'
        "not-json\n",
        encoding="utf-8",
    )

    console = ConsoleBroker(log_path=log_path)
    await console.publish("stdout", "next", source="git")

    assert [event["sequence"] for event in console.snapshot()] == [7, 8]


async def test_real_stream_reader_publishes_chunks_before_completion():
    console = ConsoleBroker()
    proc = StreamingProcess()
    stdout, stderr = await communicate_with_console(
        proc,
        timeout=1,
        console=console,
        source="compose",
        target="demo01",
    )

    assert stdout == b"step 1\nstep 2\n"
    assert stderr == b"warning\n"
    events = console.snapshot()
    assert [event["kind"] for event in events].count("stdout") == 2
    assert [event["kind"] for event in events].count("stderr") == 1
    assert "step 1" in "".join(event["text"] for event in events if event["kind"] == "stdout")


async def test_compose_command_and_response_are_written_to_console():
    console = ConsoleBroker()

    async def runner(cmd, cwd):
        return FakeProcess(stdout=b"NAME STATE\n", stderr=b"warning\n", returncode=0)

    service = ComposeService(runner=runner, console=console)
    result = await service.run("demo01", "/instances/demo01", "ps")

    assert result["success"] is True
    events = console.snapshot()
    assert [event["kind"] for event in events] == ["command", "stdout", "stderr", "exit"]
    assert events[0]["text"] == "$ docker compose ps"
    assert events[0]["cwd"] == "/instances/demo01"
    assert events[-1]["exit_code"] == 0


def test_console_stream_requires_token(client):
    response = client.get("/api/console/stream")
    assert response.status_code == 401


def test_console_stream_route_is_registered(app):
    routes = {
        (route.path, frozenset(getattr(route, "methods", None) or []))
        for route in app.routes
    }
    assert ("/api/console/stream", frozenset({"GET"})) in routes


def test_application_console_uses_persistent_default_path(app, root_path):
    assert app.state.console.log_path == (
        root_path / ".xpeech-deck" / "console.jsonl"
    )
