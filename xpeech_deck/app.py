"""FastAPI 应用：API 路由与前端静态资源托管。"""

from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import require_token
from .compose_service import ComposeService
from .console_service import ConsoleBroker
from .command_gate import CommandGate
from .config import DEFAULT_CONSOLE_LOG_PATH, Settings
from .errors import DeckError, ValidationError
from .global_config_service import read_redirect_mappings, save_redirect_mappings
from .git_service import GitService
from .image_service import ImageService
from .instance_service import (
    _recognize_instance,
    create_instance,
    list_instances,
    read_instance_config,
    save_instance_config,
)
from .skill_service import (
    MAX_ARCHIVE_BYTES,
    delete_custom_skill,
    export_custom_skill,
    install_custom_skill,
    list_custom_skills,
    migrate_custom_skill,
    read_custom_skill_md,
    save_custom_skill_md,
)
from .schemas import (
    AuthCheckOut,
    ComposeResultOut,
    ComposeServicesOut,
    CreateInstanceIn,
    InstanceConfigOut,
    InstanceListOut,
    InstanceOut,
    GlobalConfigOut,
    PublicInstanceListOut,
    PublicInstanceOut,
    RedirectMappingOut,
    SaveGlobalConfigIn,
    MigrateSkillIn,
    ImageListOut,
    ImagePullOut,
    ImageStatusOut,
    GitFetchAllOut,
    GitFetchResultOut,
    InstanceVersionsOut,
    SaveConfigIn,
    SaveSkillContentIn,
    SkillContentOut,
    SkillListOut,
    SkillMigrationOut,
    SkillOut,
    SuccessOut,
    SwitchVersionIn,
    SwitchVersionOut,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title=settings.display_name, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    console_log_path = (
        settings.console_log_path
        or DEFAULT_CONSOLE_LOG_PATH
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

    @app.get(
        "/api/public/instances",
        response_model=PublicInstanceListOut,
    )
    async def get_public_instances():
        instances = list_instances(settings.root_path)
        return PublicInstanceListOut(
            display_name=settings.display_name,
            instances=[
                PublicInstanceOut(
                    name=instance["name"],
                    web_client_port=instance["web_client_port"],
                )
                for instance in instances
            ],
        )

    # ---------- 认证 ----------

    @app.get(
        "/api/auth/check",
        dependencies=[Depends(require_token)],
        response_model=AuthCheckOut,
    )
    async def auth_check():
        return AuthCheckOut(authenticated=True)

    # ---------- 全局配置 ----------

    @app.get(
        "/api/global-config",
        dependencies=[Depends(require_token)],
        response_model=GlobalConfigOut,
    )
    async def get_global_config():
        mappings = read_redirect_mappings(settings.global_config_path)
        return GlobalConfigOut(
            mappings=[
                RedirectMappingOut(redirect_to=key, instance_name=value)
                for key, value in mappings.items()
            ]
        )

    @app.put(
        "/api/global-config",
        dependencies=[Depends(require_token)],
        response_model=SuccessOut,
    )
    async def put_global_config(body: SaveGlobalConfigIn):
        mappings: dict[str, str] = {}
        for item in body.mappings:
            key = item.redirect_to.strip()
            if key in mappings:
                raise ValidationError(f"redirect_to 重复：{key}")
            mappings[key] = item.instance_name
        save_redirect_mappings(settings.global_config_path, mappings)
        return SuccessOut(success=True)

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

    # ---------- 自定义内置技能 ----------

    @app.get(
        "/api/instances/{name}/skills",
        dependencies=[Depends(require_token)],
        response_model=SkillListOut,
    )
    async def get_skills(name: str):
        skills = list_custom_skills(settings.root_path, name)
        return SkillListOut(skills=[SkillOut(**skill) for skill in skills])

    @app.post(
        "/api/instances/{name}/skills",
        dependencies=[Depends(require_token)],
        response_model=SkillOut,
        status_code=201,
    )
    async def post_skill(
        name: str,
        request: Request,
        filename: str,
        overwrite: bool = False,
    ):
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > MAX_ARCHIVE_BYTES
        ):
            raise ValidationError("上传文件不能超过 20 MB")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_ARCHIVE_BYTES:
                raise ValidationError("上传文件不能超过 20 MB")
        skill = install_custom_skill(
            settings.root_path,
            name,
            filename,
            bytes(content),
            overwrite=overwrite,
        )
        return SkillOut(**skill)

    @app.get(
        "/api/instances/{name}/skills/{skill_name}/content",
        dependencies=[Depends(require_token)],
        response_model=SkillContentOut,
    )
    async def get_skill_content(name: str, skill_name: str):
        content = read_custom_skill_md(settings.root_path, name, skill_name)
        return SkillContentOut(content=content)

    @app.put(
        "/api/instances/{name}/skills/{skill_name}/content",
        dependencies=[Depends(require_token)],
        response_model=SkillOut,
    )
    async def put_skill_content(name: str, skill_name: str, body: SaveSkillContentIn):
        skill = save_custom_skill_md(settings.root_path, name, skill_name, body.content)
        return SkillOut(**skill)

    @app.get(
        "/api/instances/{name}/skills/{skill_name}/download",
        dependencies=[Depends(require_token)],
    )
    async def download_skill(name: str, skill_name: str):
        content = export_custom_skill(settings.root_path, name, skill_name)
        encoded_name = quote(f"{skill_name}.zip")
        return StreamingResponse(
            io.BytesIO(content),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
                "Content-Length": str(len(content)),
            },
        )

    @app.post(
        "/api/instances/{name}/skills/{skill_name}/migrate",
        dependencies=[Depends(require_token)],
        response_model=SkillMigrationOut,
    )
    async def migrate_skill(name: str, skill_name: str, body: MigrateSkillIn):
        migrated = migrate_custom_skill(
            settings.root_path,
            name,
            skill_name,
            body.target_instances,
            overwrite=body.overwrite,
        )
        return SkillMigrationOut(migrated=migrated)

    @app.delete(
        "/api/instances/{name}/skills/{skill_name}",
        dependencies=[Depends(require_token)],
        response_model=SuccessOut,
    )
    async def delete_skill(name: str, skill_name: str):
        delete_custom_skill(settings.root_path, name, skill_name)
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

    @app.get(
        "/api/instances/{name}/compose/services",
        dependencies=[Depends(require_token)],
        response_model=ComposeServicesOut,
    )
    async def compose_services(name: str):
        path = _recognize_instance(settings.root_path, name)
        result = await app.state.compose.list_services(name, str(path))
        return ComposeServicesOut(**result)

    @app.get(
        "/api/instances/{name}/compose/logs/{service}",
        dependencies=[Depends(require_token)],
        response_model=ComposeResultOut,
    )
    async def compose_logs(name: str, service: str):
        path = _recognize_instance(settings.root_path, name)
        result = await app.state.compose.logs(name, str(path), service)
        return ComposeResultOut(**result)

    # ---------- 根路径重定向与前端静态资源 ----------

    @app.get("/", include_in_schema=False)
    async def root(request: Request):
        # token 参数存在（即使值为空）或没有 redirect_to 时，均正常打开前端。
        if "token" in request.query_params or "redirect_to" not in request.query_params:
            if (STATIC_DIR / "index.html").is_file():
                return FileResponse(STATIC_DIR / "index.html")
            return JSONResponse(
                {"detail": "前端尚未构建，请在 frontend/ 目录运行 npm install && npm run build"}
            )

        if not settings.global_host:
            return JSONResponse(status_code=400, content={"detail": "global_host 未配置"})

        redirect_to = request.query_params["redirect_to"]
        mappings = read_redirect_mappings(settings.global_config_path)
        instance_name = mappings.get(redirect_to)
        if instance_name is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "redirect_to 未命中实例映射"},
            )

        instance = next(
            (
                item
                for item in list_instances(settings.root_path)
                if item["name"] == instance_name
            ),
            None,
        )
        if instance is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"映射指向的实例 {instance_name} 不存在"},
            )

        target = f"{settings.global_host}:{instance['web_client_port']}"
        passthrough = [
            (key, value)
            for key, value in request.query_params.multi_items()
            if key in {"state", "oauth2provider"}
        ]
        if passthrough:
            target = f"{target}?{urlencode(passthrough)}"
        return RedirectResponse(target)

    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    return app
