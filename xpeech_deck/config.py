"""平台配置：读取项目根目录 conf.toml，检查运行依赖。"""

from __future__ import annotations

import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

# 项目根目录：xpeech_deck 包所在目录的上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 实例来源：当前项目中的 xpeech 子模块目录
SOURCE_DIR = PROJECT_ROOT / "xpeech"


@dataclass(frozen=True)
class Settings:
    token: str
    root_path: Path
    source_dir: Path


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

    return Settings(token=token, root_path=root_path.resolve(), source_dir=SOURCE_DIR)


def ensure_root_path(root_path: Path) -> None:
    """root_path 不存在时自动创建。"""
    root_path.mkdir(parents=True, exist_ok=True)


def docker_available() -> bool:
    """检查 docker 命令是否可执行。"""
    return shutil.which("docker") is not None
