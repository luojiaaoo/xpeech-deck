"""平台配置：读取项目根目录 conf.toml，检查运行依赖。"""

from __future__ import annotations

import re
import shutil
import tomllib
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

# 项目根目录：xpeech_deck 包所在目录的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DISPLAY_NAME = "Xpeech Deck"
DEFAULT_GLOBAL_CONFIG_PATH = PROJECT_ROOT / "global_config.json"
DEFAULT_CONSOLE_LOG_PATH = PROJECT_ROOT / "console.jsonl"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
GLOBAL_HOST_ERROR = (
    "conf.toml 中的 global_host 必须是以 http:// 或 https:// 开头的有效地址，"
    "且不能包含端口、路径、查询参数或认证信息"
)


@dataclass(frozen=True)
class Settings:
    token: str
    root_path: Path
    console_log_path: Path | None = None
    listen_port: int = 7801
    display_name: str = DEFAULT_DISPLAY_NAME
    global_host: str | None = None
    global_config_path: Path = DEFAULT_GLOBAL_CONFIG_PATH
    redis_url: str = DEFAULT_REDIS_URL
    redis_password: str = field(default="", repr=False)


def _project_relative_path(value: object, default: Path) -> Path:
    """将可选配置路径解析为绝对路径，空值使用项目根目录下的默认文件。"""
    raw = str(value).strip() if value is not None else ""
    path = Path(raw).expanduser() if raw else default
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _normalize_hostname(host: str) -> str:
    """校验并规范化域名/IP；IPv6 返回适合放入 URL authority 的方括号形式。"""
    try:
        parsed_ip = ip_address(host)
        return f"[{parsed_ip}]" if parsed_ip.version == 6 else str(parsed_ip)
    except ValueError:
        pass

    # 防止形似 IPv4 的非法值（例如 999.1.1.1）被当成普通域名。
    if re.fullmatch(r"[0-9.]+", host):
        raise ValueError(GLOBAL_HOST_ERROR)
    domain = host[:-1] if host.endswith(".") else host
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(GLOBAL_HOST_ERROR) from exc
    if (
        not ascii_domain
        or len(ascii_domain) > 253
        or any(not HOST_LABEL_RE.fullmatch(label) for label in ascii_domain.split("."))
    ):
        raise ValueError(GLOBAL_HOST_ERROR)
    return f"{ascii_domain}." if host.endswith(".") else ascii_domain


def _validate_global_host(value: object) -> str | None:
    """校验带 HTTP(S) 协议的全局主机地址，并返回无末尾斜杠的规范形式。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError(GLOBAL_HOST_ERROR)

    raw = value.strip()
    if any(character.isspace() for character in raw):
        raise ValueError(GLOBAL_HOST_ERROR)
    try:
        parsed = urlsplit(raw)
        configured_port = parsed.port
    except ValueError as exc:
        raise ValueError(GLOBAL_HOST_ERROR) from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or configured_port is not None
        or parsed.netloc.endswith(":")
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.hostname is None
    ):
        raise ValueError(GLOBAL_HOST_ERROR)

    hostname = _normalize_hostname(parsed.hostname)
    return f"{parsed.scheme.lower()}://{hostname}"


def load_settings(path: Path | None = None) -> Settings:
    """读取 conf.toml 并校验，返回平台配置。"""
    conf_path = path or (PROJECT_ROOT / "conf.toml")
    if not conf_path.is_file():
        raise FileNotFoundError(
            f"缺少配置文件：{conf_path}（请参考 conf.toml.example 创建 conf.toml）"
        )
    data = tomllib.loads(conf_path.read_text(encoding="utf-8"))

    token = str(data.get("token", "")).strip()
    if not token:
        raise ValueError("conf.toml 中的 token 不能为空")

    raw_root = str(data.get("root_path", "")).strip()
    if not raw_root:
        raise ValueError("conf.toml 中的 root_path 不能为空")
    root_path = Path(raw_root).expanduser()
    if not root_path.is_absolute():
        root_path = (PROJECT_ROOT / root_path).resolve()
    root_path = root_path.resolve()

    console_log_path = _project_relative_path(
        data.get("console_log_path"), DEFAULT_CONSOLE_LOG_PATH
    )

    display_name = str(data.get("display_name", DEFAULT_DISPLAY_NAME)).strip()
    if not display_name:
        display_name = DEFAULT_DISPLAY_NAME

    global_host = _validate_global_host(data.get("global_host"))

    global_config_path = _project_relative_path(
        data.get("global_config_path"), DEFAULT_GLOBAL_CONFIG_PATH
    )

    redis_url = str(data.get("redis_url", DEFAULT_REDIS_URL)).strip()
    if not redis_url:
        raise ValueError("conf.toml 中的 redis_url 不能为空")

    redis_password = str(data.get("redis_password", ""))

    listen_port = data.get("listen_port", 7801)
    if isinstance(listen_port, bool) or not isinstance(listen_port, int):
        raise ValueError("conf.toml 中的 listen_port 必须是 1–65535 之间的整数")
    if not 1 <= listen_port <= 65535:
        raise ValueError("conf.toml 中的 listen_port 必须是 1–65535 之间的整数")

    return Settings(
        token=token,
        root_path=root_path,
        console_log_path=console_log_path,
        listen_port=listen_port,
        display_name=display_name,
        global_host=global_host,
        global_config_path=global_config_path,
        redis_url=redis_url,
        redis_password=redis_password,
    )


def ensure_root_path(root_path: Path) -> None:
    """root_path 不存在时自动创建。"""
    root_path.mkdir(parents=True, exist_ok=True)


def docker_available() -> bool:
    """检查 docker 命令是否可执行。"""
    return shutil.which("docker") is not None


def git_available() -> bool:
    """检查 git 命令是否可执行。"""
    return shutil.which("git") is not None
