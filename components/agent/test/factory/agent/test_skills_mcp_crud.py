"""Typed MCP contracts for Agent-owned skill list/read/add."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from factory.agent.mcp.contracts.discovery import SkillAddInput, SkillIdInput


def _seed(root: Path, skill_id: str = "existing") -> None:
    directory = root / skill_id
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        "---\nname: Existing Skill\ndescription: Seeded\n---\n\nFollow evidence.\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_skill_list_read_add_and_conflict(tmp_path, monkeypatch) -> None:
    from factory.agent.mcp import skills_tools
    from factory.agent.server import create_tool_catalog

    _seed(tmp_path)
    monkeypatch.setattr(skills_tools, "_SKILLS_ROOT", tmp_path)
    monkeypatch.setenv("SUPER_AGENT_ENABLE_AUTHORING_TOOLS", "1")
    catalog = create_tool_catalog()
    names = set(catalog.tool_map())
    assert {"agent_list_skills", "agent_read_skill", "agent_add_skill"} <= names

    listed = await catalog.call_tool("agent_list_skills", {})
    assert listed.structured_content["data"]["skills"] == [{
        "id": "existing", "name": "Existing Skill", "description": "Seeded",
    }]
    detail = await catalog.call_tool("agent_read_skill", {"skill_id": "existing"})
    assert detail.structured_content["data"]["body"] == "Follow evidence."

    added = await catalog.call_tool("agent_add_skill", {
        "skill_id": "new-skill", "name": "New Skill",
        "description": "Created", "body": "Use typed tools.",
    })
    assert added.structured_content["data"]["created"] is True
    assert (tmp_path / "new-skill" / "SKILL.md").is_file()
    reread = await catalog.call_tool("agent_read_skill", {"skill_id": "new-skill"})
    assert reread.structured_content["data"]["body"] == "Use typed tools."

    conflict = await catalog.call_tool("agent_add_skill", {
        "skill_id": "new-skill", "name": "Other", "description": "", "body": "No.",
    })
    assert conflict.structured_content["ok"] is False
    assert conflict.structured_content["error"] == "skill_exists"

    assert "agent_delete_skill" in names
    deleted = await catalog.call_tool("agent_delete_skill", {"skill_id": "new-skill"})
    assert deleted.structured_content["data"] == {"deleted": True, "skill_id": "new-skill"}
    assert not (tmp_path / "new-skill").exists()
    gone = await catalog.call_tool("agent_read_skill", {"skill_id": "new-skill"})
    assert gone.structured_content["ok"] is False

    missing = await catalog.call_tool("agent_delete_skill", {"skill_id": "never-existed"})
    assert missing.structured_content["error"] == "skill_not_found"


def test_skill_inputs_reject_traversal_unknown_fields_and_nul() -> None:
    for value in ("../escape", "Upper", "has_underscore", "a" * 65):
        with pytest.raises(ValidationError):
            SkillIdInput(skill_id=value)
    with pytest.raises(ValidationError):
        SkillIdInput.model_validate({"skill_id": "safe", "extra": True})
    with pytest.raises(ValidationError):
        SkillAddInput(skill_id="safe", name="Safe", body="bad\x00body")


def test_symlinked_skill_is_never_listed_or_read(tmp_path, monkeypatch) -> None:
    from factory.agent.mcp import skills_tools

    outside = tmp_path / "outside"
    outside.mkdir()
    _seed(outside, "secret")
    root = tmp_path / "skills"
    root.mkdir()
    (root / "linked").symlink_to(outside / "secret", target_is_directory=True)
    monkeypatch.setattr(skills_tools, "_SKILLS_ROOT", root)
    assert skills_tools.list_skills() == []
    assert skills_tools._read_skill("linked") is None
    # A symlinked "skill" directory must never be deletable through this
    # path either — deletion must be as traversal-safe as read/list.
    assert skills_tools._delete_skill("linked") is False
    assert (outside / "secret").exists()


def test_runtime_skill_store_override_is_shared(tmp_path, monkeypatch) -> None:
    from factory.agent.mcp import skills_tools
    from factory.agent.registry.launch_validator import skills_dir

    monkeypatch.setenv("FACTORY_AGENT_SKILLS_DIR", str(tmp_path))
    assert skills_tools._skills_root() == tmp_path
    assert skills_dir() == tmp_path


@settings(max_examples=20, deadline=None)
@given(
    skill_id=st.from_regex(r"[a-z0-9][a-z0-9-]{0,15}", fullmatch=True),
    body=st.text(min_size=1, max_size=80).filter(
        lambda value: "\x00" not in value and bool(value.strip()),
    ),
)
def test_skill_authoring_round_trips_generated_content(
    skill_id: str, body: str,
) -> None:
    from factory.agent.mcp import skills_tools

    previous = skills_tools._SKILLS_ROOT
    with TemporaryDirectory() as temporary:
        skills_tools._SKILLS_ROOT = Path(temporary)
        try:
            skills_tools._add_skill(skill_id, "Generated", "Property", body)
            detail = skills_tools._read_skill(skill_id)
            assert detail is not None
            assert detail.body == body.strip()
        finally:
            skills_tools._SKILLS_ROOT = previous
