"""Strict data-driven runtime selection tests."""

import pytest
from pydantic import ValidationError

from factory.agent.runtime.runtime_selection import load_runtime_selection


def test_loads_project_runtime_adapter_yaml(tmp_path) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text(
        "schema_version: v1\nruntime_adapter_id: langchain-langgraph\noptions: {}\n",
        encoding="utf-8",
    )
    selection = load_runtime_selection(path)
    assert selection.runtime_adapter_id == "langchain-langgraph"


def test_rejects_unknown_configuration_fields(tmp_path) -> None:
    path = tmp_path / "runtime.yaml"
    path.write_text(
        "schema_version: v1\nruntime_adapter_id: test\nframework_class: bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_runtime_selection(path)
