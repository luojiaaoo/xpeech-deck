"""实例发现、创建与配置管理。"""

from __future__ import annotations

import re
import shutil
import tomllib
from collections.abc import Awaitable, Callable
from pathlib import Path

from .errors import ConflictError, FileOperationError, NotFoundError, ValidationError

# 实例名：字母/数字开头，后续允许字母、数字、下划线、连字符，最长 63 字符
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}$")


def validate_name(name: str) -> str:
    name = name.strip()
    if not NAME_RE.match(name):
        raise ValidationError(
            "实例名只能由字母、数字、下划线和连字符组成，且以字母或数字开头，长度不超过 63"
        )
    return name


def parse_dotenv(text: str) -> dict[str, str]:
    """解析 .env 值，支持 export、引号和行尾注释，不展开变量。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = re.sub(r"^export\s+", "", key.strip())
        value = value.strip()
        quoted = re.fullmatch(r"(['\"])(.*?)\1(?:\s+#.*)?", value)
        if quoted:
            value = quoted.group(2)
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
        result[key] = value
    return result


def build_dotenv(name: str, template: str) -> str:
    """保留示例配置原文，仅设置实例的 Compose 项目名。"""
    content, count = re.subn(
        r"(?m)^([ \t]*(?:export[ \t]+)?COMPOSE_PROJECT_NAME[ \t]*=[ \t]*)"
        r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n]*?)"
        r"([ \t]+#[^\r\n]*|[ \t]*)(\r?)$",
        lambda match: f"{match[1]}{name}{match[2]}{match[3]}",
        template,
    )
    if not count:
        newline = "\r\n" if "\r\n" in template else "\n"
        if content and not content.endswith(("\r", "\n")):
            content += newline
        content += f"COMPOSE_PROJECT_NAME={name}{newline}"
    return content


def _port(env: dict[str, str], key: str) -> int | None:
    try:
        port = int(env[key])
    except (KeyError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def _recognize_instance(root_path: Path, name: str) -> Path:
    """确认 name 是已识别的实例，返回其实例目录；否则抛出 404。"""
    name = validate_name(name)
    path = root_path / name
    env_file = path / ".env"
    compose_file = path / "compose.yaml"
    if (
        path.is_symlink()
        or not path.is_dir()
        or not env_file.is_file()
        or not compose_file.is_file()
    ):
        raise NotFoundError(f"实例 {name} 不存在")
    try:
        env = parse_dotenv(env_file.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileOperationError(f"读取实例 {name} 配置失败：{exc}") from exc
    if not env.get("COMPOSE_PROJECT_NAME"):
        raise NotFoundError(f"实例 {name} 不存在")
    return path


def list_instances(root_path: Path) -> list[dict]:
    """扫描 root_path 直接子目录，返回被识别的实例列表。"""
    instances: list[dict] = []
    if not root_path.is_dir():
        return instances
    for child in sorted(root_path.iterdir()):
        if not child.is_dir():
            continue
        env_file = child / ".env"
        if not env_file.is_file() or not (child / "compose.yaml").is_file():
            continue
        try:
            env = parse_dotenv(env_file.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not env.get("COMPOSE_PROJECT_NAME"):
            continue
        instances.append(
            {
                "name": child.name,
                "backend_port": _port(env, "BACKEND_PORT"),
                "web_client_port": _port(env, "WEB_CLIENT_PORT"),
                "ports": [value for key, value in env.items() if key.endswith("_PORT") and value],
                "path": str(child),
            }
        )
    return instances


async def create_instance(
    root_path: Path,
    name: str,
    clone: Callable[[Path], Awaitable[dict]],
) -> dict:
    """从远程仓库克隆 Xpeech，由示例文件初始化 .env 与 conf.toml。"""
    name = validate_name(name)
    target = root_path / name
    try:
        # 先原子占位，防止两个同名克隆同时通过 exists 检查。
        target.mkdir()
    except FileExistsError:
        raise ConflictError(f"实例 {name} 已存在")
    except OSError as exc:
        raise FileOperationError(f"创建实例目录失败：{exc}") from exc

    try:
        result = await clone(target)
        if not result["success"]:
            detail = result["stderr"].strip() or result["stdout"].strip() or "未知错误"
            raise FileOperationError(f"克隆 Xpeech 失败：{detail}")

        template = (target / ".env.example").read_bytes().decode("utf-8")
        env_content = build_dotenv(name, template)
        (target / ".env").write_bytes(env_content.encode("utf-8"))
        env = parse_dotenv(env_content)
        backend_port = _port(env, "BACKEND_PORT")
        web_client_port = _port(env, "WEB_CLIENT_PORT")
        example = target / "conf.toml.example"
        if example.is_file():
            shutil.copy2(example, target / "conf.toml")
    except Exception as exc:
        # 创建是一个事务：克隆或初始化失败时不留半成品目录。
        try:
            if target.is_symlink():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
        except OSError:
            pass
        if isinstance(exc, FileOperationError):
            raise
        if isinstance(exc, OSError):
            raise FileOperationError(f"生成实例配置失败：{exc}") from exc
        raise

    return {
        "name": name,
        "backend_port": backend_port,
        "web_client_port": web_client_port,
        "ports": [value for key, value in env.items() if key.endswith("_PORT") and value],
        "path": str(target),
    }


def read_instance_config(root_path: Path, name: str) -> dict:
    """读取 .env 与 conf.toml 原文，保留注释、空行和换行格式。"""
    path = _recognize_instance(root_path, name)
    try:
        env_content = (path / ".env").read_bytes().decode("utf-8")
        conf_file = path / "conf.toml"
        conf_toml = conf_file.read_bytes().decode("utf-8") if conf_file.is_file() else ""
    except OSError as exc:
        raise FileOperationError(f"读取实例 {name} 配置失败：{exc}") from exc
    return {
        "name": name,
        "env_content": env_content,
        "conf_toml": conf_toml,
    }


def save_instance_config(
    root_path: Path,
    name: str,
    env_content: str,
    conf_toml: str,
) -> None:
    """保存实例配置：先完整校验，全部通过后才写文件，失败不覆盖原配置。"""
    path = _recognize_instance(root_path, name)

    if not parse_dotenv(env_content).get("COMPOSE_PROJECT_NAME"):
        raise ValidationError(".env 必须保留非空的 COMPOSE_PROJECT_NAME，以便识别实例")

    try:
        tomllib.loads(conf_toml)
    except tomllib.TOMLDecodeError as exc:
        # str(exc) 自带位置信息，如 "(at line 3, column 5)"
        raise ValidationError(f"conf.toml 语法错误：{exc}") from exc

    try:
        for filename, content in ((".env", env_content), ("conf.toml", conf_toml)):
            config_file = path / filename
            encoded = content.encode("utf-8")
            if not config_file.is_file() or config_file.read_bytes() != encoded:
                config_file.write_bytes(encoded)
    except OSError as exc:
        raise FileOperationError(f"保存实例 {name} 配置失败：{exc}") from exc
