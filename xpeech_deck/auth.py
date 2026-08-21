"""URL Token 认证：Bearer Token 与 conf.toml 中的 token 比对。"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request


def require_token(request: Request) -> None:
    """FastAPI 依赖：校验 Authorization: Bearer <token>。"""
    token = request.app.state.settings.token
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少访问 Token")
    supplied = header[len("Bearer "):].strip()
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(status_code=401, detail="Token 错误")
