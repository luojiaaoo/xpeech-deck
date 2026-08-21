"""API 请求与响应模型。"""

from __future__ import annotations

from pydantic import BaseModel


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


class ComposeResultOut(BaseModel):
    success: bool
    exit_code: int
    stdout: str
    stderr: str


class AuthCheckOut(BaseModel):
    authenticated: bool


class SuccessOut(BaseModel):
    success: bool
