"""FastAPI 应用：API 路由与前端静态资源托管。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .compose_service import ComposeService
from .console_service import ConsoleBroker
from .command_gate import CommandGate
from .config import Settings
from .errors import DeckError
from .git_service import GitService
from .image_service import ImageService
from .instance_service import (
    _recognize_instance,
    create_instance,
    list_instances,
    read_instance_config,
    save_instance_config,
)
from .schemas import (
    AuthCheckOut,
    ComposeResultOut,
    CreateInstanceIn,
    InstanceConfigOut,
    InstanceListOut,
    InstanceOut,
    ImageListOut,
    ImagePullOut,
    ImageStatusOut,
    GitFetchAllOut,
    GitFetchResultOut,
    InstanceVersionsOut,
    SaveConfigIn,
    SuccessOut,
    SwitchVersionIn,
    SwitchVersionOut,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Xpeech Deck", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    console_log_path = (
        settings.console_log_path
        or settings.root_path / ".xpeech-deck" / "console.jsonl"
    )
    app.state.console = ConsoleBroker(log_path=console_log_path)
    app.state.command_gate = CommandGate()
    app.state.compose = ComposeService(console=app.state.console, gate=app.state.command_gate)
    app.state.images = ImageService(console=app.state.console, gate=app.state.command_gate)
    app.state.git = GitService(console=app.state.console, gate=app.state.command_gate)

    @app.exception_handler(DeckError)
    async def deck_error_handler(request: Request, exc: DeckError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    # ---------- 公开接口 ----------

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # ---------- 认证 ----------

    @app.get(
        "/api/auth/check",
        dependencies=[Depends(require_token)],
        response_model=AuthCheckOut,
    )
    async def auth_check():
        return AuthCheckOut(authenticated=True)

    # ---------- 系统 Console ----------

    @app.get(
        "/api/console/stream",
        dependencies=[Depends(require_token)],
    )
    async def console_stream(request: Request):
        async def events():
            async for event in app.state.console.subscribe():
                if await request.is_disconnected():
                    break
                if event is None:
                    yield ": keep-alive\n\n"
                else:
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"data: {payload}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---------- Docker 镜像 ----------

    @app.get(
        "/api/images",
        dependencies=[Depends(require_token)],
        response_model=ImageListOut,
    )
    async def get_images():
        images = await app.state.images.list_statuses()
        return ImageListOut(images=[ImageStatusOut(**image) for image in images])

    @app.post(
        "/api/images/{key}/pull",
        dependencies=[Depends(require_token)],
        response_model=ImagePullOut,
    )
    async def pull_image(key: str):
        result = await app.state.images.pull(key)
        return ImagePullOut(**result)

    # ---------- 实例管理 ----------

    @app.get(
        "/api/instances",
        dependencies=[Depends(require_token)],
        response_model=InstanceListOut,
    )
    async def get_instances():
        instances = list_instances(settings.root_path)
        return InstanceListOut(instances=[InstanceOut(**i) for i in instances])

    @app.post(
        "/api/instances",
        dependencies=[Depends(require_token)],
        response_model=InstanceOut,
        status_code=201,
    )
    async def post_instance(body: CreateInstanceIn):
        data = await create_instance(settings.root_path, body.name, app.state.git.clone)
        return InstanceOut(**data)

    @app.post(
        "/api/instances/fetch",
        dependencies=[Depends(require_token)],
        response_model=GitFetchAllOut,
    )
    async def fetch_instances():
        instances = list_instances(settings.root_path)
        paths = [(item["name"], Path(item["path"])) for item in instances]
        results = await app.state.git.fetch_all(paths)
        return GitFetchAllOut(results=[GitFetchResultOut(**item) for item in results])

    @app.get(
        "/api/instances/{name}/versions",
        dependencies=[Depends(require_token)],
        response_model=InstanceVersionsOut,
    )
    async def get_versions(name: str):
        path = _recognize_instance(settings.root_path, name)
        data = await app.state.git.versions(name, path)
        return InstanceVersionsOut(**data)

    @app.post(
        "/api/instances/{name}/version",
        dependencies=[Depends(require_token)],
        response_model=SwitchVersionOut,
    )
    async def switch_version(name: str, body: SwitchVersionIn):
        path = _recognize_instance(settings.root_path, name)
        data = await app.state.git.switch(name, path, body.ref)
        return SwitchVersionOut(**data)

    @app.get(
        "/api/instances/{name}/config",
        dependencies=[Depends(require_token)],
        response_model=InstanceConfigOut,
    )
    async def get_config(name: str):
        data = read_instance_config(settings.root_path, name)
        return InstanceConfigOut(**data)

    @app.put(
        "/api/instances/{name}/config",
        dependencies=[Depends(require_token)],
        response_model=SuccessOut,
    )
    async def put_config(name: str, body: SaveConfigIn):
        save_instance_config(
            settings.root_path,
            name,
            body.backend_port,
            body.web_client_port,
            body.conf_toml,
        )
        return SuccessOut(success=True)

    # ---------- Compose 操作 ----------

    @app.post(
        "/api/instances/{name}/compose/{action}",
        dependencies=[Depends(require_token)],
        response_model=ComposeResultOut,
    )
    async def compose_action(name: str, action: str):
        path = _recognize_instance(settings.root_path, name)
        result = await app.state.compose.run(name, str(path), action)
        return ComposeResultOut(**result)

    @app.get(
        "/api/instances/{name}/compose/ps",
        dependencies=[Depends(require_token)],
        response_model=ComposeResultOut,
    )
    async def compose_ps(name: str):
        path = _recognize_instance(settings.root_path, name)
        result = await app.state.compose.run(name, str(path), "ps")
        return ComposeResultOut(**result)

    # ---------- 前端静态资源（最后挂载，避免覆盖 /api 与 /health） ----------

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    else:
        @app.get("/", include_in_schema=False)
        async def index_placeholder():
            return JSONResponse(
                {"detail": "前端尚未构建，请在 frontend/ 目录运行 npm install && npm run build"}
            )

    return app
