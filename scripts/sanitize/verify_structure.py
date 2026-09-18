"""Structural verification, including deleted-module import integrity."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from .safety import confined, iter_files

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".next",
              ".pytest_cache", ".ruff_cache", ".hypothesis", ".mypy_cache"}


def _deleted_modules(policy: dict[str, Any]) -> set[str]:
    modules: set[str] = set()
    for raw in [*(policy.get("delete_paths", []) or []),
                *(policy.get("delete_exact", []) or [])]:
        parts = Path(raw.rstrip("/")).parts
        if len(parts) == 2 and parts[0] in {"components", "bases"}:
            modules.add(f"factory.{parts[1]}")
        if "src" in parts:
            suffix = list(parts[parts.index("src") + 1:])
            if suffix:
                suffix[-1] = suffix[-1].removesuffix(".py")
                if suffix[-1] == "__init__":
                    suffix.pop()
                modules.add(".".join(suffix))
        if parts and parts[0] == "scripts":
            dotted = ".".join(parts).removesuffix(".py")
            modules.add(dotted)
            modules.add(".".join(parts[1:]).removesuffix(".py"))
    return {module for module in modules if module}


def _module_for(path: Path, root: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(root).parts)
    if "src" not in parts:
        return "", False
    suffix = parts[parts.index("src") + 1:]
    is_package = suffix[-1] == "__init__.py"
    suffix[-1] = suffix[-1].removesuffix(".py")
    if is_package:
        suffix.pop()
    return ".".join(suffix), is_package


def _imports(node: ast.AST, module: str, is_package: bool) -> set[str]:
    found: set[str] = set()
    dynamic_names = {"__import__"}
    for item in ast.walk(node):
        if isinstance(item, ast.ImportFrom) and item.module == "importlib":
            dynamic_names.update(alias.asname or alias.name for alias in item.names
                                 if alias.name == "import_module")
    for item in ast.walk(node):
        if isinstance(item, ast.Import):
            found.update(alias.name for alias in item.names)
        elif isinstance(item, ast.ImportFrom):
            if item.level:
                package = module if is_package else module.rpartition(".")[0]
                parts = package.split(".") if package else []
                base = parts[:max(0, len(parts) - item.level + 1)]
                if item.module:
                    base.extend(item.module.split("."))
                prefix = ".".join(base)
                found.add(prefix)
                if not item.module:
                    found.update(f"{prefix}.{alias.name}".strip(".")
                                 for alias in item.names)
            elif item.module:
                found.add(item.module)
                found.update(f"{item.module}.{alias.name}" for alias in item.names
                             if alias.name != "*")
        elif isinstance(item, ast.Call) and item.args:
            function = item.func
            dynamic = (
                isinstance(function, ast.Name)
                and function.id in dynamic_names
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
            )
            if dynamic and isinstance(item.args[0], ast.Constant):
                value = item.args[0].value
                if isinstance(value, str):
                    found.add(value)
    return found


def find_deleted_imports(root: Path, policy: dict[str, Any]) -> list[str]:
    deleted = _deleted_modules(policy)
    dangling: list[str] = []
    for path in iter_files(root, skip_dirs=_SKIP_DIRS):
        if path.suffix != ".py":
            continue
        try:
            node = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        module, is_package = _module_for(path, root)
        for imported in _imports(node, module, is_package):
            if any(imported == dead or imported.startswith(f"{dead}.")
                   for dead in deleted):
                dangling.append(f"{path.relative_to(root)} -> {imported}")
    return sorted(set(dangling))


def structural_checks(root: Path, policy: dict[str, Any], result: Any) -> None:
    structural = policy["structural"]
    components = sorted(path.name for path in (root / "components").iterdir()
                        if path.is_dir())
    bases = sorted(path.name for path in (root / "bases").iterdir() if path.is_dir())
    result.check("component_count", len(components) == structural["expected_components"],
                 f"expected {structural['expected_components']}, got {len(components)}")
    result.check("base_count", len(bases) == structural["expected_bases"],
                 f"expected {structural['expected_bases']}, got {len(bases)}")
    if structural.get("require_brick_yaml"):
        missing = [name for name in components
                   if not (root / "components" / name / "BRICK.yaml").is_file()]
        result.check("brick_yaml_present", not missing, f"missing: {missing}")
    stripped = structural["strip_brick_maps"]
    present = [name for name in stripped if (root / "components" / name).exists()]
    result.check("excluded_bricks_removed", not present, f"still present: {present}")
    if structural.get("require_no_dangling_index"):
        index = root / "BRICKS_INDEX.yaml"
        names = re.findall(r"^  - name: (\S+)$", index.read_text(), re.M) if index.is_file() else []
        dangling = [name for name in names if not (
            (root / "components" / name).is_dir() or (root / "bases" / name).is_dir())]
        result.check("bricks_index_no_dangling", not dangling, f"dangling: {dangling}")
    for relative in structural["pyproject_files"]:
        path = confined(root, relative)
        bad = [name for name in stripped if path.is_file()
               and f"components/{name}/" in path.read_text(encoding="utf-8")]
        result.check(f"pyproject_clean[{relative}]", not bad, f"still mapped: {bad}")
    imports = find_deleted_imports(root, policy)
    result.check("deleted_module_imports", not imports, "; ".join(imports[:10]))
    sanitizer_paths = [root / "scripts" / "sanitize", root / "scripts" / "sanitize_public.py"]
    present_tools = [str(path.relative_to(root)) for path in sanitizer_paths if path.exists()]
    result.check("sanitizer_tooling_removed", not present_tools,
                 f"still present: {present_tools}")
