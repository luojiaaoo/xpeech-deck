"""实例自定义内置技能的安全安装、编辑、导出、迁移与删除。"""

from __future__ import annotations

import io
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .errors import ConflictError, FileOperationError, NotFoundError, ValidationError
from .instance_service import _recognize_instance, validate_name

BUILTIN_SKILLS_RELATIVE = Path("xpeech/agent/skills/buildin")
CUSTOM_SKILL_PREFIX = "x-"
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_FILES = 2_000
MAX_SKILL_MD_BYTES = 1024 * 1024


def _skills_root(root_path: Path, instance_name: str) -> Path:
    return _recognize_instance(root_path, instance_name) / BUILTIN_SKILLS_RELATIVE


def _validate_custom_name(name: str) -> str:
    """校验一个已存在的 x-* 目录名，允许清理早期创建的非标准名称。"""
    if (
        not name.startswith(CUSTOM_SKILL_PREFIX)
        or len(name) <= len(CUSTOM_SKILL_PREFIX)
        or len(name) > 255
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise ValidationError("只能管理名称以 x- 开头的自定义技能")
    return name


def _validate_uploaded_name(name: str) -> str:
    _validate_custom_name(name)
    if not SKILL_NAME_RE.fullmatch(name):
        raise ValidationError("技能名只能由小写字母、数字和单连字符组成")
    if len(name) > 64:
        raise ValidationError("技能名长度不能超过 64 个字符")
    return name


def _description_from_skill_md(text: str) -> str:
    """轻量读取 frontmatter 的 description，解析失败时不影响技能管理。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return ""
    for index, line in enumerate(lines[1:end], 1):
        match = re.match(r"^description\s*:\s*(.*)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if value in {"|", ">"}:
            parts: list[str] = []
            for continuation in lines[index + 1 : end]:
                if continuation[:1].isspace():
                    parts.append(continuation.strip())
                else:
                    break
            return " ".join(part for part in parts if part)[:1024]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value[:1024]
    return ""


def _name_from_skill_md(text: str) -> str:
    """从 SKILL.md frontmatter 读取用来创建目录的技能名。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValidationError("SKILL.md 缺少 YAML frontmatter")
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValidationError("SKILL.md 的 YAML frontmatter 未闭合")
    for line in lines[1:end]:
        match = re.match(r"^name\s*:\s*(.*)$", line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1].strip()
        if value:
            return value
    raise ValidationError("SKILL.md frontmatter 中缺少 name")


def _skill_info(path: Path) -> dict:
    file_count = 0
    size_bytes = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            file_count += 1
            try:
                size_bytes += child.stat().st_size
            except OSError:
                pass
    try:
        description = _description_from_skill_md(
            (path / "SKILL.md").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError):
        description = ""
    return {
        "name": path.name,
        "description": description,
        "file_count": file_count,
        "size_bytes": size_bytes,
    }


def _custom_skill_path(root_path: Path, instance_name: str, skill_name: str) -> Path:
    """返回一个可管理技能目录，并拒绝目录或入口文件符号链接。"""
    skill_name = _validate_custom_name(skill_name)
    target = _skills_root(root_path, instance_name) / skill_name
    skill_md = target / "SKILL.md"
    if (
        target.is_symlink()
        or not target.is_dir()
        or skill_md.is_symlink()
        or not skill_md.is_file()
    ):
        raise NotFoundError(f"技能 {skill_name} 不存在")
    return target


def _validate_skill_tree(path: Path) -> list[Path]:
    """列出技能内普通文件，避免下载或迁移时跟随符号链接。"""
    files: list[Path] = []
    size_bytes = 0
    try:
        for child in path.rglob("*"):
            if child.is_symlink():
                raise FileOperationError(f"技能 {path.name} 包含符号链接，无法导出或迁移")
            if child.is_dir():
                continue
            if not child.is_file():
                raise FileOperationError(f"技能 {path.name} 包含非常规文件，无法导出或迁移")
            files.append(child)
            if len(files) > MAX_ARCHIVE_FILES:
                raise FileOperationError("技能文件数超过 2000，无法导出或迁移")
            size_bytes += child.stat().st_size
            if size_bytes > MAX_EXTRACTED_BYTES:
                raise FileOperationError("技能大小超过 100 MB，无法导出或迁移")
    except FileOperationError:
        raise
    except OSError as exc:
        raise FileOperationError(f"读取技能 {path.name} 失败：{exc}") from exc
    return files


def list_custom_skills(root_path: Path, instance_name: str) -> list[dict]:
    """仅列出 x-* 自定义内置技能，不暴露仓库自带技能为可管理项。"""
    root = _skills_root(root_path, instance_name)
    if not root.is_dir():
        return []
    result: list[dict] = []
    try:
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if (
                child.name.startswith(CUSTOM_SKILL_PREFIX)
                and child.is_dir()
                and not child.is_symlink()
                and (child / "SKILL.md").is_file()
            ):
                result.append(_skill_info(child))
    except OSError as exc:
        raise FileOperationError(f"读取实例 {instance_name} 的技能失败：{exc}") from exc
    return result


def _archive_files(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
    seen: set[str] = set()
    extracted_bytes = 0

    for info in archive.infolist():
        normalized = info.filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if not normalized or normalized.startswith("/") or ".." in path.parts:
            raise ValidationError("技能压缩包包含不安全路径")
        if path.parts and path.parts[0] == "__MACOSX":
            continue
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise ValidationError("技能压缩包不能包含符号链接")
        if info.is_dir():
            continue
        file_type = stat.S_IFMT(mode)
        if file_type and file_type != stat.S_IFREG:
            raise ValidationError("技能压缩包只能包含普通文件")
        if info.flag_bits & 0x1:
            raise ValidationError("不支持加密的技能压缩包")
        key = path.as_posix().casefold()
        if key in seen:
            raise ValidationError("技能压缩包包含重复路径")
        seen.add(key)
        extracted_bytes += info.file_size
        if extracted_bytes > MAX_EXTRACTED_BYTES:
            raise ValidationError("技能解压后不能超过 100 MB")
        files.append((info, path))
        if len(files) > MAX_ARCHIVE_FILES:
            raise ValidationError("技能压缩包文件数不能超过 2000")

    if not files:
        raise ValidationError("技能压缩包为空")
    return files


def _archive_layout(
    files: list[tuple[zipfile.ZipInfo, PurePosixPath]], filename: str
) -> tuple[str, int]:
    paths = [path for _, path in files]
    if PurePosixPath("SKILL.md") in paths:
        roots_to_strip = 0
        source_name = Path(filename).stem
    else:
        top_levels = {path.parts[0] for path in paths if path.parts}
        if len(top_levels) != 1:
            raise ValidationError("技能压缩包必须只包含一个技能目录")
        source_name = next(iter(top_levels))
        roots_to_strip = 1
        if PurePosixPath(source_name, "SKILL.md") not in paths:
            raise ValidationError("技能压缩包中缺少 SKILL.md")

    if source_name.startswith(CUSTOM_SKILL_PREFIX):
        custom_name = source_name
    else:
        custom_name = f"{CUSTOM_SKILL_PREFIX}{source_name}"
    return _validate_uploaded_name(custom_name), roots_to_strip


def install_custom_skill(
    root_path: Path,
    instance_name: str,
    filename: str,
    content: bytes,
    *,
    overwrite: bool = False,
) -> dict:
    """从 SKILL.md 或 .zip 安装技能，目录名自动补 x-。"""
    if not content:
        raise ValidationError("上传文件不能为空")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise ValidationError("上传文件不能超过 20 MB")

    if filename.casefold() == "skill.md":
        if len(content) > MAX_SKILL_MD_BYTES:
            raise ValidationError("SKILL.md 不能超过 1 MB")
        try:
            skill_text = content.decode("utf-8")
        except UnicodeError as exc:
            raise ValidationError("SKILL.md 必须使用 UTF-8 编码") from exc
        source_name = _name_from_skill_md(skill_text)
        packaged = io.BytesIO()
        with zipfile.ZipFile(packaged, "w", zipfile.ZIP_DEFLATED) as generated:
            generated.writestr(f"{source_name}/SKILL.md", content)
        content = packaged.getvalue()
        filename = f"{source_name}.zip"
    elif not filename.lower().endswith(".zip"):
        raise ValidationError("请选择 SKILL.md 或 .zip 技能包")

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValidationError("技能包不是有效的 ZIP 文件") from exc

    with archive:
        files = _archive_files(archive)
        custom_name, roots_to_strip = _archive_layout(files, filename)
        skills_root = _skills_root(root_path, instance_name)
        target = skills_root / custom_name
        if target.exists() and not overwrite:
            raise ConflictError(f"技能 {custom_name} 已存在")

        try:
            skills_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".xpeech-deck-upload-", dir=skills_root) as tmp:
                staged = Path(tmp) / custom_name
                staged.mkdir()
                for info, archive_path in files:
                    relative_parts = archive_path.parts[roots_to_strip:]
                    if not relative_parts:
                        continue
                    destination = staged.joinpath(*relative_parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    if mode := (info.external_attr >> 16) & 0o111:
                        destination.chmod(destination.stat().st_mode | mode)
                skill_md = staged / "SKILL.md"
                if not skill_md.is_file():
                    raise ValidationError("技能压缩包中缺少 SKILL.md")
                if skill_md.stat().st_size > MAX_SKILL_MD_BYTES:
                    raise ValidationError("SKILL.md 不能超过 1 MB")
                try:
                    skill_md.read_text(encoding="utf-8")
                except UnicodeError as exc:
                    raise ValidationError("SKILL.md 必须使用 UTF-8 编码") from exc

                backup: Path | None = None
                if target.exists():
                    if target.is_symlink() or not target.is_dir():
                        raise FileOperationError(f"技能目录 {custom_name} 状态异常，无法覆盖")
                    backup = skills_root / f".xpeech-deck-backup-{uuid.uuid4().hex}"
                    target.rename(backup)
                try:
                    staged.rename(target)
                except Exception:
                    if backup is not None and backup.exists() and not target.exists():
                        backup.rename(target)
                    raise
                if backup is not None:
                    shutil.rmtree(backup, ignore_errors=True)
        except ValidationError:
            raise
        except (zipfile.BadZipFile, RuntimeError) as exc:
            raise ValidationError("技能包内容损坏，无法解压") from exc
        except OSError as exc:
            raise FileOperationError(f"安装技能 {custom_name} 失败：{exc}") from exc

    return _skill_info(target)


def read_custom_skill_md(root_path: Path, instance_name: str, skill_name: str) -> str:
    """读取自定义技能的 SKILL.md，供在线编辑。"""
    target = _custom_skill_path(root_path, instance_name, skill_name)
    skill_md = target / "SKILL.md"
    try:
        if skill_md.stat().st_size > MAX_SKILL_MD_BYTES:
            raise ValidationError("SKILL.md 不能超过 1 MB")
        return skill_md.read_text(encoding="utf-8")
    except ValidationError:
        raise
    except UnicodeError as exc:
        raise ValidationError("SKILL.md 必须使用 UTF-8 编码") from exc
    except OSError as exc:
        raise FileOperationError(f"读取技能 {skill_name} 失败：{exc}") from exc


def save_custom_skill_md(
    root_path: Path,
    instance_name: str,
    skill_name: str,
    content: str,
) -> dict:
    """原子保存自定义技能的 SKILL.md。"""
    target = _custom_skill_path(root_path, instance_name, skill_name)
    encoded = content.encode("utf-8")
    if not encoded:
        raise ValidationError("SKILL.md 不能为空")
    if len(encoded) > MAX_SKILL_MD_BYTES:
        raise ValidationError("SKILL.md 不能超过 1 MB")
    _name_from_skill_md(content)

    skill_md = target / "SKILL.md"
    staged = target / f".SKILL.md.{uuid.uuid4().hex}.tmp"
    try:
        staged.write_bytes(encoded)
        staged.chmod(skill_md.stat().st_mode)
        os.replace(staged, skill_md)
    except OSError as exc:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
        raise FileOperationError(f"保存技能 {skill_name} 失败：{exc}") from exc
    return _skill_info(target)


def export_custom_skill(
    root_path: Path,
    instance_name: str,
    skill_name: str,
) -> bytes:
    """将完整技能目录导出为带顶层目录的 ZIP。"""
    target = _custom_skill_path(root_path, instance_name, skill_name)
    files = _validate_skill_tree(target)
    output = io.BytesIO()
    try:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for child in files:
                relative = child.relative_to(target)
                archive.write(child, PurePosixPath(skill_name, *relative.parts).as_posix())
    except OSError as exc:
        raise FileOperationError(f"导出技能 {skill_name} 失败：{exc}") from exc
    return output.getvalue()


def migrate_custom_skill(
    root_path: Path,
    source_instance: str,
    skill_name: str,
    target_instances: list[str],
    *,
    overwrite: bool = False,
) -> list[str]:
    """将一个完整技能事务式复制到多个实例。"""
    source_instance = validate_name(source_instance)
    source = _custom_skill_path(root_path, source_instance, skill_name)
    _validate_skill_tree(source)

    unique_targets: list[str] = []
    seen: set[str] = set()
    for raw_target_instance in target_instances:
        target_instance = validate_name(raw_target_instance)
        if target_instance == source_instance:
            raise ValidationError("迁移目标不能包含源实例")
        if target_instance not in seen:
            seen.add(target_instance)
            unique_targets.append(target_instance)
    if not unique_targets:
        raise ValidationError("请至少选择一个目标实例")
    if len(unique_targets) > 100:
        raise ValidationError("单次最多迁移到 100 个实例")

    destinations: list[tuple[str, Path, Path]] = []
    conflicts: list[str] = []
    for target_instance in unique_targets:
        skills_root = _skills_root(root_path, target_instance)
        destination = skills_root / skill_name
        if destination.exists():
            if not overwrite:
                conflicts.append(target_instance)
            elif destination.is_symlink() or not destination.is_dir():
                raise FileOperationError(
                    f"实例 {target_instance} 的技能目录 {skill_name} 状态异常，无法覆盖"
                )
        destinations.append((target_instance, skills_root, destination))
    if conflicts:
        raise ConflictError(f"以下实例已存在技能 {skill_name}：{', '.join(conflicts)}")

    staged_paths: list[tuple[str, Path, Path, Path]] = []
    committed: list[tuple[Path, Path | None]] = []
    try:
        for target_instance, skills_root, destination in destinations:
            skills_root.mkdir(parents=True, exist_ok=True)
            staged = skills_root / f".xpeech-deck-migrate-{uuid.uuid4().hex}"
            staged_paths.append((target_instance, staged, skills_root, destination))
            shutil.copytree(source, staged)

        for _, staged, skills_root, destination in staged_paths:
            backup: Path | None = None
            if destination.exists():
                backup = skills_root / f".xpeech-deck-backup-{uuid.uuid4().hex}"
                destination.rename(backup)
            try:
                staged.rename(destination)
            except Exception:
                if backup is not None and backup.exists() and not destination.exists():
                    backup.rename(destination)
                raise
            committed.append((destination, backup))
    except Exception as exc:
        for destination, backup in reversed(committed):
            try:
                if destination.exists():
                    shutil.rmtree(destination)
                if backup is not None and backup.exists():
                    backup.rename(destination)
            except OSError:
                pass
        raise FileOperationError(f"迁移技能 {skill_name} 失败：{exc}") from exc
    finally:
        for _, staged, _, _ in staged_paths:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)

    for _, backup in committed:
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    return unique_targets


def delete_custom_skill(root_path: Path, instance_name: str, skill_name: str) -> None:
    """删除一个 x-* 自定义技能；仓库内置技能永远不会进入此路径。"""
    target = _custom_skill_path(root_path, instance_name, skill_name)
    try:
        shutil.rmtree(target)
    except OSError as exc:
        raise FileOperationError(f"删除技能 {skill_name} 失败：{exc}") from exc
