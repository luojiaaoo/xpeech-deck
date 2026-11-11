"""自定义内置技能管理测试。"""

from __future__ import annotations

import io
import stat
import zipfile

import pytest


def _skill_md(name: str = "weather-plus", description: str = "补充天气能力") -> bytes:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Test\n"
    ).encode("utf-8")


def _skill_archive(
    name: str = "weather-plus",
    *,
    description: str = "补充天气能力",
    root_directory: bool = True,
    extra_files: dict[str, str] | None = None,
) -> bytes:
    prefix = f"{name}/" if root_directory else ""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            f"{prefix}SKILL.md",
            _skill_md(name, description),
        )
        for path, content in (extra_files or {}).items():
            archive.writestr(f"{prefix}{path}", content)
    return buffer.getvalue()


def _upload(client, auth_headers, content: bytes, filename: str, overwrite: bool = False):
    return client.post(
        "/api/instances/demo01/skills",
        params={"filename": filename, "overwrite": str(overwrite).lower()},
        headers=auth_headers,
        content=content,
    )


def test_upload_adds_x_prefix_and_lists_skill(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    content = _skill_archive(extra_files={"scripts/run.py": "print('ok')\n"})

    response = _upload(client, auth_headers, content, "weather-plus.zip")

    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "x-weather-plus"
    assert data["is_custom"] is True
    assert data["description"] == "补充天气能力"
    assert data["filter"] is None
    assert data["file_count"] == 2
    target = (
        root_path
        / "demo01"
        / "xpeech"
        / "agent"
        / "skills"
        / "buildin"
        / "x-weather-plus"
    )
    assert (target / "SKILL.md").is_file()
    assert (target / "scripts" / "run.py").read_text(encoding="utf-8") == "print('ok')\n"

    listed = client.get("/api/instances/demo01/skills", headers=auth_headers)
    assert listed.status_code == 200
    assert [skill["name"] for skill in listed.json()["skills"]] == ["x-weather-plus"]


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ('filter: channel == "feishu"\n', 'channel == "feishu"'),
        ("filter: 'channel == \"feishu\"'\n", 'channel == "feishu"'),
        ('filter: >-\n  channel == "feishu"\n  and org == "demo"\n',
         'channel == "feishu" and org == "demo"'),
        ("filter:\n", ""),
        ("", None),
        ("# filter: ignored\n", None),
    ],
)
def test_skill_filter_is_exposed_from_frontmatter(
    client, auth_headers, make_instance, field, expected
):
    make_instance("demo01")
    content = (
        "---\nname: helper\ndescription: 技能描述\n"
        f"{field}---\n\n# Body\nfilter: not-frontmatter\n"
    )

    uploaded = _upload(client, auth_headers, content.encode("utf-8"), "SKILL.md")
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["filter"] == expected
    assert uploaded.json()["description"] == "技能描述"

    listed = client.get("/api/instances/demo01/skills", headers=auth_headers)
    assert listed.json()["skills"][0]["filter"] == expected

    edited = (
        "---\nname: helper\ndescription: 技能描述\n"
        'filter: org == "updated"\n---\n\n# Body\n'
    )
    saved = client.put(
        "/api/instances/demo01/skills/x-helper/content",
        headers=auth_headers,
        json={"content": edited},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["filter"] == 'org == "updated"'

    removed = client.put(
        "/api/instances/demo01/skills/x-helper/content",
        headers=auth_headers,
        json={"content": _skill_md("helper").decode("utf-8")},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["filter"] is None


def test_upload_does_not_duplicate_existing_x_prefix(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    response = _upload(client, auth_headers, _skill_archive("x-helper"), "x-helper.zip")
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "x-helper"
    assert (
        root_path
        / "demo01"
        / "xpeech"
        / "agent"
        / "skills"
        / "buildin"
        / "x-helper"
    ).is_dir()


def test_upload_skill_md_uses_frontmatter_name(client, auth_headers, make_instance, root_path):
    make_instance("demo01")

    response = _upload(client, auth_headers, _skill_md("calendar-helper"), "SKILL.md")

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "x-calendar-helper"
    installed = (
        root_path
        / "demo01"
        / "xpeech"
        / "agent"
        / "skills"
        / "buildin"
        / "x-calendar-helper"
        / "SKILL.md"
    )
    assert installed.read_bytes() == _skill_md("calendar-helper")


def test_upload_supports_archive_without_wrapper_directory(client, auth_headers, make_instance):
    make_instance("demo01")
    response = _upload(
        client,
        auth_headers,
        _skill_archive("plain", root_directory=False),
        "plain.zip",
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "x-plain"


def test_duplicate_requires_explicit_overwrite(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    first = _skill_archive(description="第一版")
    second = _skill_archive(description="第二版")
    assert _upload(client, auth_headers, first, "weather-plus.zip").status_code == 201

    conflict = _upload(client, auth_headers, second, "weather-plus.zip")
    assert conflict.status_code == 409
    assert "已存在" in conflict.json()["detail"]

    replaced = _upload(client, auth_headers, second, "weather-plus.zip", overwrite=True)
    assert replaced.status_code == 201
    assert replaced.json()["description"] == "第二版"
    skill_md = (
        root_path
        / "demo01"
        / "xpeech"
        / "agent"
        / "skills"
        / "buildin"
        / "x-weather-plus"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "第二版" in skill_md


def test_online_edit_and_download_complete_skill(
    client, auth_headers, make_instance, root_path
):
    make_instance("demo01")
    content = _skill_archive(extra_files={"scripts/run.py": "print('ok')\n"})
    assert _upload(client, auth_headers, content, "weather-plus.zip").status_code == 201

    read = client.get(
        "/api/instances/demo01/skills/x-weather-plus/content", headers=auth_headers
    )
    assert read.status_code == 200
    assert read.json()["content"] == _skill_md().decode("utf-8")

    updated_content = _skill_md(description="在线编辑后的描述").decode("utf-8")
    saved = client.put(
        "/api/instances/demo01/skills/x-weather-plus/content",
        headers=auth_headers,
        json={"content": updated_content},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["description"] == "在线编辑后的描述"

    invalid = client.put(
        "/api/instances/demo01/skills/x-weather-plus/content",
        headers=auth_headers,
        json={"content": "# missing frontmatter\n"},
    )
    assert invalid.status_code == 400
    skill_md = (
        root_path
        / "demo01"
        / "xpeech"
        / "agent"
        / "skills"
        / "buildin"
        / "x-weather-plus"
        / "SKILL.md"
    )
    assert skill_md.read_text(encoding="utf-8") == updated_content

    downloaded = client.get(
        "/api/instances/demo01/skills/x-weather-plus/download", headers=auth_headers
    )
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    assert "x-weather-plus.zip" in downloaded.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert set(archive.namelist()) == {
            "x-weather-plus/SKILL.md",
            "x-weather-plus/scripts/run.py",
        }
        assert archive.read("x-weather-plus/SKILL.md").decode("utf-8") == updated_content
        assert archive.read("x-weather-plus/scripts/run.py") == b"print('ok')\n"


def test_delete_only_allows_custom_skills(client, auth_headers, make_instance, root_path):
    make_instance("demo01")
    skills_root = root_path / "demo01" / "xpeech" / "agent" / "skills" / "buildin"
    builtin = skills_root / "weather"
    builtin.mkdir(parents=True)
    (builtin / "SKILL.md").write_text("# Built in\n", encoding="utf-8")
    assert _upload(client, auth_headers, _skill_archive(), "weather-plus.zip").status_code == 201

    listed = client.get("/api/instances/demo01/skills", headers=auth_headers)
    assert [skill["name"] for skill in listed.json()["skills"]] == ["weather", "x-weather-plus"]
    assert [skill["is_custom"] for skill in listed.json()["skills"]] == [False, True]

    protected = client.delete("/api/instances/demo01/skills/weather", headers=auth_headers)
    assert protected.status_code == 400
    assert builtin.is_dir()

    deleted = client.delete(
        "/api/instances/demo01/skills/x-weather-plus", headers=auth_headers
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"success": True}
    assert not (skills_root / "x-weather-plus").exists()


def test_builtin_skills_can_be_viewed_and_downloaded_but_not_edited(
    client, auth_headers, make_instance, root_path
):
    make_instance("demo01")
    skills_root = root_path / "demo01" / "xpeech" / "agent" / "skills" / "buildin"
    builtin = skills_root / "weather"
    builtin.mkdir(parents=True)
    content = (
        '---\nname: weather\ndescription: 内置天气技能\nfilter: org == "demo"\n---\n# Weather\n'
    )
    (builtin / "SKILL.md").write_text(content, encoding="utf-8")
    (builtin / "helper.py").write_bytes(b"print('weather')\n")
    (skills_root / "not-a-skill").mkdir()

    listed = client.get("/api/instances/demo01/skills", headers=auth_headers).json()["skills"]
    assert len(listed) == 1
    assert listed[0]["name"] == "weather"
    assert listed[0]["is_custom"] is False
    assert listed[0]["description"] == "内置天气技能"
    assert listed[0]["filter"] == 'org == "demo"'

    viewed = client.get("/api/instances/demo01/skills/weather/content", headers=auth_headers)
    assert viewed.status_code == 200
    assert viewed.json()["content"] == content

    downloaded = client.get("/api/instances/demo01/skills/weather/download", headers=auth_headers)
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert set(archive.namelist()) == {"weather/SKILL.md", "weather/helper.py"}
        assert archive.read("weather/helper.py") == b"print('weather')\n"

    edited = client.put(
        "/api/instances/demo01/skills/weather/content",
        headers=auth_headers,
        json={"content": _skill_md("weather").decode("utf-8")},
    )
    assert edited.status_code == 400
    assert (builtin / "SKILL.md").read_text(encoding="utf-8") == content


@pytest.mark.parametrize("skill_name", ["..", ".", "../outside", "nested/skill", "C:outside", "\\outside"])
def test_skill_reads_reject_paths_outside_single_directory(make_instance, root_path, skill_name):
    from xpeech_deck.errors import ValidationError
    from xpeech_deck.skill_service import read_skill_md, export_skill

    make_instance("demo01")
    for read in (read_skill_md, export_skill):
        with pytest.raises(ValidationError):
            read(root_path, "demo01", skill_name)


def test_rejects_unsafe_or_invalid_archives(client, auth_headers, make_instance):
    make_instance("demo01")

    traversal = io.BytesIO()
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("safe/SKILL.md", "# Safe\n")
        archive.writestr("../escaped.txt", "bad")
    assert _upload(client, auth_headers, traversal.getvalue(), "safe.zip").status_code == 400

    missing = io.BytesIO()
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("no-skill/readme.md", "missing")
    assert _upload(client, auth_headers, missing.getvalue(), "no-skill.zip").status_code == 400

    symlink = io.BytesIO()
    with zipfile.ZipFile(symlink, "w") as archive:
        archive.writestr("linked/SKILL.md", "# Linked\n")
        info = zipfile.ZipInfo("linked/scripts/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../outside")
    assert _upload(client, auth_headers, symlink.getvalue(), "linked.zip").status_code == 400

    assert _upload(client, auth_headers, b"not a zip", "broken.zip").status_code == 400
    assert _upload(client, auth_headers, _skill_archive(), "legacy.skill").status_code == 400
    assert _upload(client, auth_headers, b"# Missing frontmatter\n", "SKILL.md").status_code == 400
    assert _upload(client, auth_headers, _skill_md(), "other.md").status_code == 400
    assert _upload(client, auth_headers, _skill_archive(), "weather-plus.tar").status_code == 400


def test_skill_routes_require_authentication(client, make_instance):
    make_instance("demo01")
    assert client.get("/api/instances/demo01/skills").status_code == 401
    assert (
        client.post(
            "/api/instances/demo01/skills",
            params={"filename": "sample.zip"},
            content=_skill_archive("sample"),
        ).status_code
        == 401
    )
    assert client.delete("/api/instances/demo01/skills/x-sample").status_code == 401
    assert client.get("/api/instances/demo01/skills/x-sample/content").status_code == 401
    assert client.put(
        "/api/instances/demo01/skills/x-sample/content", json={"content": "test"}
    ).status_code == 401
    assert client.get("/api/instances/demo01/skills/x-sample/download").status_code == 401


def test_skill_routes_for_missing_instance_return_404(client, auth_headers):
    assert client.get("/api/instances/ghost/skills", headers=auth_headers).status_code == 404
    assert (
        client.delete("/api/instances/ghost/skills/x-sample", headers=auth_headers).status_code
        == 404
    )
