"""基于文件的 Skills API，skill 是 assistant/skills/ 下的文件夹。"""

import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.utils.frontmatter import parse_frontmatter as _parse_fm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


class SkillInfo(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    tags: list[str] = []


def _parse_frontmatter(text: str) -> dict | None:
    """解析 skill frontmatter，并将 ``origin`` 值映射为标签。"""
    fields, _ = _parse_fm(text)
    if not fields:
        return None
    result: dict[str, str | list[str]] = {}
    tags: list[str] = []
    for k, v in fields.items():
        if k == "origin":
            tags.append(v)
        else:
            result[k] = v
    if tags:
        result["tags"] = tags
    return result


def _read_skill(folder: Path) -> SkillInfo | None:
    """读取 skill 文件夹并返回信息；无效时返回 None。

    校验要求：
    - 必须存在大写的 ``SKILL.md``
    - frontmatter 必须包含 ``name`` 和 ``description``
    """
    skill_file = folder / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        text = skill_file.read_text(encoding="utf-8")
    except Exception:
        return None

    fm = _parse_frontmatter(text)
    if fm is None:
        return None
    name = fm.get("name", "").strip()
    description = fm.get("description", "").strip()
    if not name or not description:
        return None

    tags: list[str] = fm.get("tags", []) if isinstance(fm.get("tags"), list) else []
    return SkillInfo(
        id=folder.name,
        name=name,
        description=description,
        enabled=not (folder / ".disabled").exists(),
        tags=tags,
    )


@router.get("", response_model=List[SkillInfo])
def list_skills():
    """扫描 assistant/skills/ 并返回所有有效 skill。"""
    results: list[SkillInfo] = []
    if not SKILLS_DIR.exists():
        return results
    for child in sorted(SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        info = _read_skill(child)
        if info:
            results.append(info)
    return results


@router.post("/{skill_id}/toggle")
def toggle_skill(skill_id: str):
    """通过 .disabled 标记切换启用或禁用状态。"""
    folder = SKILLS_DIR / skill_id
    if not folder.exists() or not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"技能 '{skill_id}' 不存在")
    disabled_file = folder / ".disabled"
    if disabled_file.exists():
        disabled_file.unlink()
        return {"id": skill_id, "enabled": True}
    else:
        disabled_file.write_text("")
        return {"id": skill_id, "enabled": False}
