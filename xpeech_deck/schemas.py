"""API 请求与响应模型。"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class InstanceOut(BaseModel):
    name: str
    backend_port: int
    web_client_port: int
    path: str


class InstanceListOut(BaseModel):
    instances: list[InstanceOut]


class CreateInstanceIn(BaseModel):
    name: str


class InstanceConfigOut(BaseModel):
    name: str
    backend_port: int
    web_client_port: int
    conf_toml: str


class SaveConfigIn(BaseModel):
    # 端口允许整数或数字字符串，具体校验在服务层完成（保证返回 400 而非 422）
    backend_port: int | str
    web_client_port: int | str
    conf_toml: str


class GitVersionOut(BaseModel):
    ref: str
    label: str
    kind: Literal["branch", "tag", "commit"]
    commit: str
    committed_at: str | None = None


class InstanceVersionsOut(BaseModel):
    current_ref: str
    current_label: str
    current_commit: str
    versions: list[GitVersionOut]


class SwitchVersionIn(BaseModel):
    ref: str


class GitResultOut(BaseModel):
    success: bool
    exit_code: int
    stdout: str
    stderr: str


class GitFetchResultOut(GitResultOut):
    name: str


class GitFetchAllOut(BaseModel):
    results: list[GitFetchResultOut]


class SwitchVersionOut(GitResultOut):
    current_ref: str
    current_label: str
    current_commit: str


class ComposeResultOut(BaseModel):
    success: bool
    exit_code: int
    stdout: str
    stderr: str


class AuthCheckOut(BaseModel):
    authenticated: bool


class SuccessOut(BaseModel):
    success: bool


class ImageStatusOut(BaseModel):
    key: str
    label: str
    name: str
    status: Literal["available", "missing", "error"]
    image_id: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None
    message: str = ""


class ImageListOut(BaseModel):
    images: list[ImageStatusOut]


class ImagePullOut(ComposeResultOut):
    image: ImageStatusOut
