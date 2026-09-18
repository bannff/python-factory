"""Typed Agent skill discovery, reading, and gated authoring tools."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml
from factory.mcp_utils.interface import (
    ToolResult, authoring, deterministic, fail, ok,
)

from ..authoring import authoring_enabled
from .contracts.discovery import (
    EmptyInput, SkillAddInput, SkillAddOutput, SkillDeleteOutput,
    SkillDetailOutput, SkillIdInput, SkillSummary, SkillsOutput,
)

if TYPE_CHECKING:
    from ..agent import SuperAgent

logger = logging.getLogger(__name__)
_SKILLS_ROOT = Path(__file__).parent.parent / "skills"
_MAX_SKILL_BYTES = 400_000


def _skills_root() -> Path:
    configured = os.environ.get("FACTORY_AGENT_SKILLS_DIR", "").strip()
    return Path(configured).expanduser() if configured else _SKILLS_ROOT


def _frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        parts = text.split("---", 2)
        value = yaml.safe_load(parts[1]) if text.startswith("---") and len(parts) == 3 else {}
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        logger.debug("Cannot read skill %s: %s", path, error)
        return {}


def _summary(skill_id: str, path: Path) -> SkillSummary:
    meta = _frontmatter(path)
    return SkillSummary(
        id=skill_id, name=str(meta.get("name") or skill_id),
        description=str(meta.get("description") or "").strip(),
    )


def list_skills() -> list[SkillSummary]:
    """Enumerate skills from runtime-owned on-disk SKILL.md files."""
    root = _skills_root()
    if not root.exists() or root.is_symlink():
        return []
    skills: list[SkillSummary] = []
    for directory in sorted(root.iterdir()):
        path = directory / "SKILL.md"
        if directory.is_dir() and not directory.is_symlink() and path.is_file() and not path.is_symlink():
            skills.append(_summary(directory.name, path))
    return skills


def _read_skill(skill_id: str) -> SkillDetailOutput | None:
    root = _skills_root().resolve()
    path = root / skill_id / "SKILL.md"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_SKILL_BYTES:
        return None
    try:
        path.resolve(strict=True).relative_to(root)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return None
    parts = text.split("---", 2)
    body = parts[2].strip() if text.startswith("---") and len(parts) == 3 else text.strip()
    summary = _summary(skill_id, path)
    return SkillDetailOutput(**summary.model_dump(), body=body)


def _add_skill(skill_id: str, name: str, description: str, body: str) -> SkillSummary:
    configured_root = _skills_root()
    root = configured_root.resolve(strict=True)
    if configured_root.is_symlink():
        raise ValueError("skills_root_unavailable")
    directory = root / skill_id
    directory.mkdir(mode=0o700, exist_ok=False)
    temporary = directory / ".SKILL.md.tmp"
    target = directory / "SKILL.md"
    header = yaml.safe_dump(
        {"name": name.strip(), "description": description.strip()},
        sort_keys=False, allow_unicode=True,
    )
    content = f"---\n{header}---\n\n{body.strip()}\n"
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_SKILL_BYTES:
        directory.rmdir()
        raise ValueError("skill_too_large")
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return SkillSummary(id=skill_id, name=name.strip(), description=description.strip())


def _delete_skill(skill_id: str) -> bool:
    """Remove a runtime-owned skill directory. Symlink/traversal-safe like read/add."""
    root = _skills_root().resolve()
    directory = root / skill_id
    target = directory / "SKILL.md"
    if directory.is_symlink() or not directory.is_dir() or target.is_symlink() or not target.is_file():
        return False
    try:
        directory.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        return False
    for child in directory.iterdir():
        if child.is_symlink() or child.is_dir():
            return False
        child.unlink()
    directory.rmdir()
    return True


def register(mcp: Any, agent: "SuperAgent") -> None:
    """Register always-readable skills and explicitly gated creation."""
    @mcp.tool()
    @deterministic(input_model=EmptyInput, output_model=SkillsOutput)
    def agent_list_skills() -> ToolResult[SkillsOutput]:
        skills = list_skills()
        return ok(SkillsOutput(count=len(skills), skills=skills))

    @mcp.tool()
    @deterministic(input_model=SkillIdInput, output_model=SkillDetailOutput)
    def agent_read_skill(skill_id: str) -> ToolResult[SkillDetailOutput]:
        skill = _read_skill(skill_id)
        return fail("skill_not_found") if skill is None else ok(skill)

    if authoring_enabled(getattr(agent, "settings", None)):
        @mcp.tool()
        @authoring(input_model=SkillAddInput, output_model=SkillAddOutput)
        def agent_add_skill(
            skill_id: str, name: str, description: str, body: str,
        ) -> ToolResult[SkillAddOutput]:
            try:
                skill = _add_skill(skill_id, name, description, body)
            except FileExistsError:
                return fail("skill_exists")
            except (OSError, ValueError):
                return fail("skill_write_failed")
            return ok(SkillAddOutput(created=True, skill=skill))

        @mcp.tool()
        @authoring(input_model=SkillIdInput, output_model=SkillDeleteOutput)
        def agent_delete_skill(skill_id: str) -> ToolResult[SkillDeleteOutput]:
            deleted = _delete_skill(skill_id)
            if not deleted:
                return fail("skill_not_found")
            return ok(SkillDeleteOutput(deleted=True, skill_id=skill_id))


__all__ = ["register", "list_skills"]
