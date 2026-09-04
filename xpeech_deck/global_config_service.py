"""可实时读取和更新的 redirect_to 全局映射配置。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import FileOperationError, ValidationError


def read_redirect_mappings(path: Path) -> dict[str, str]:
    """读取 global_config.json；文件不存在等价于空映射。"""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise FileOperationError(f"读取全局配置失败：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise FileOperationError(f"global_config.json 格式错误：{exc}") from exc

    if not isinstance(data, dict) or set(data) - {"redirect_to"}:
        raise FileOperationError(
            'global_config.json 格式错误：根对象只能包含 "redirect_to" 映射'
        )
    mappings = data.get("redirect_to", {})
    if not isinstance(mappings, dict):
        raise FileOperationError(
            'global_config.json 格式错误："redirect_to" 必须是对象'
        )

    result: dict[str, str] = {}
    for redirect_to, instance_name in mappings.items():
        if (
            not isinstance(redirect_to, str)
            or not redirect_to
            or not isinstance(instance_name, str)
            or not instance_name
        ):
            raise FileOperationError(
                "global_config.json 格式错误：redirect_to 和实例名必须是非空字符串"
            )
        result[redirect_to] = instance_name
    return result


def save_redirect_mappings(path: Path, mappings: dict[str, str]) -> None:
    """原子保存映射，避免请求读取到只写了一半的 JSON 文件。"""
    normalized: dict[str, str] = {}
    for redirect_to, instance_name in mappings.items():
        redirect_to = redirect_to.strip()
        instance_name = instance_name.strip()
        if not redirect_to or not instance_name:
            raise ValidationError("redirect_to 和实例名不能为空")
        normalized[redirect_to] = instance_name

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(
                    {"redirect_to": normalized},
                    file,
                    ensure_ascii=False,
                    indent=2,
                )
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise FileOperationError(f"保存全局配置失败：{exc}") from exc
