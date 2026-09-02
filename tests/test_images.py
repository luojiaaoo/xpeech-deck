"""Docker 镜像状态与拉取接口测试。"""

from __future__ import annotations

import json

import pytest

from xpeech_deck.errors import NotFoundError
from xpeech_deck.image_service import IMAGE_SPECS, ImageService


class FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.returncode = -9


def inspect_output(image_id: str = "abc123def456789", size: int = 123456) -> bytes:
    return json.dumps(
        [{"Id": f"sha256:{image_id}", "Size": size, "Created": "2026-08-22T01:02:03Z"}]
    ).encode()


async def test_list_image_statuses_available_and_missing():
    commands: list[list[str]] = []

    async def runner(cmd):
        commands.append(cmd)
        if "ubuntu:22.04" in cmd[-1]:
            return FakeProcess(stdout=inspect_output())
        return FakeProcess(stderr=b"Error: No such image", returncode=1)

    images = await ImageService(runner=runner).list_statuses()

    assert images[0]["status"] == "available"
    assert images[0]["image_id"] == "abc123def456"
    assert images[0]["size_bytes"] == 123456
    assert images[1]["status"] == "missing"
    assert images[2]["status"] == "missing"
    assert images[2]["name"] == "docker.1ms.run/library/golang:1.23-bookworm"
    assert commands == [
        ["docker", "image", "inspect", IMAGE_SPECS[0].name],
        ["docker", "image", "inspect", IMAGE_SPECS[1].name],
        ["docker", "image", "inspect", IMAGE_SPECS[2].name],
    ]


async def test_inspect_failure_reports_error():
    async def runner(cmd):
        return FakeProcess(stderr=b"Cannot connect to the Docker daemon", returncode=1)

    image = await ImageService(runner=runner).inspect("browserless")
    assert image["status"] == "error"
    assert "Docker daemon" in image["message"]


async def test_missing_docker_command_reports_error_instead_of_raising():
    async def runner(cmd):
        raise FileNotFoundError(2, "No such file or directory", "docker")

    images = await ImageService(runner=runner).list_statuses()

    assert all(image["status"] == "error" for image in images)
    assert all("无法启动 Docker 命令" in image["message"] for image in images)


async def test_pull_uses_fixed_image_and_refreshes_status():
    commands: list[list[str]] = []

    async def runner(cmd):
        commands.append(cmd)
        if cmd[:2] == ["docker", "pull"]:
            return FakeProcess(stdout=b"Pulled newer image\n")
        return FakeProcess(stdout=inspect_output())

    result = await ImageService(runner=runner).pull("browserless")

    assert result["success"] is True
    assert result["stdout"] == "Pulled newer image\n"
    assert result["image"]["status"] == "available"
    assert commands == [
        ["docker", "pull", IMAGE_SPECS[1].name],
        ["docker", "image", "inspect", IMAGE_SPECS[1].name],
    ]


async def test_unknown_image_rejected():
    with pytest.raises(NotFoundError):
        await ImageService().pull("unknown")


def test_images_api_requires_token(client):
    assert client.get("/api/images").status_code == 401
    assert client.post("/api/images/browserless/pull").status_code == 401


def test_images_api(client, auth_headers):
    async def runner(cmd):
        return FakeProcess(stdout=inspect_output())

    client.app.state.images = ImageService(runner=runner)
    response = client.get("/api/images", headers=auth_headers)

    assert response.status_code == 200
    images = response.json()["images"]
    assert [image["key"] for image in images] == ["xpeech-base", "browserless", "golang"]
    assert all(image["status"] == "available" for image in images)


def test_pull_image_api(client, auth_headers):
    async def runner(cmd):
        if cmd[:2] == ["docker", "pull"]:
            return FakeProcess(stdout=b"done\n")
        return FakeProcess(stdout=inspect_output())

    client.app.state.images = ImageService(runner=runner)
    response = client.post("/api/images/xpeech-base/pull", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["image"]["status"] == "available"


def test_unknown_image_api_returns_404(client, auth_headers):
    response = client.post("/api/images/unknown/pull", headers=auth_headers)
    assert response.status_code == 404
