"""Fail-closed content and runtime verification for sanitized output."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .safety import SafetyError, confined, iter_files
from .verify_structure import structural_checks

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".next",
              ".pytest_cache", ".ruff_cache", ".hypothesis", ".mypy_cache"}
_SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
                ".gz", ".zip", ".7z", ".woff", ".woff2", ".ttf",
                ".safetensors", ".bin", ".sqlite", ".db", ".lock"}


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str


@dataclass
class VerifyResult:
    findings: list[Finding] = field(default_factory=list)
    structural: list[tuple[str, bool, str]] = field(default_factory=list)
    exceptions_applied: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings and all(passed for _, passed, _ in self.structural)

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.structural.append((name, passed, detail))


def _rules(policy: dict[str, Any]) -> list[tuple[str, re.Pattern[str]]]:
    return [(rule["name"], re.compile(rule["pattern"])) for rule in policy["forbid"]]


def _exceptions(policy: dict[str, Any]) -> list[tuple[str, re.Pattern[str], str]]:
    return [(item["path"], re.compile(item["pattern"]), item["reason"])
            for item in policy.get("allow_exceptions", []) or []]


def scan_forbidden(root: Path, policy: dict[str, Any], result: VerifyResult) -> None:
    exceptions = _exceptions(policy)
    for relative, _, _ in exceptions:
        confined(root, relative)
    for path in iter_files(root, skip_dirs=_SKIP_DIRS):
        if path.suffix.lower() in _SKIP_SUFFIX:
            continue
        relative = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for name, pattern in _rules(policy):
                if not pattern.search(line):
                    continue
                exception = next((reason for exc_path, exc_pattern, reason in exceptions
                                  if relative == exc_path and exc_pattern.search(line)), None)
                if exception:
                    note = f"{relative}:{line_number} [{name}] excused: {exception.strip()}"
                    if note not in result.exceptions_applied:
                        result.exceptions_applied.append(note)
                else:
                    result.findings.append(Finding(
                        relative, line_number, name, line.strip()[:140],
                    ))


def scan_git_tracked(clone: Path, policy: dict[str, Any], result: VerifyResult) -> None:
    process = subprocess.run(
        ["git", "ls-files", "-z"], cwd=clone, capture_output=True, text=True,
    )
    if process.returncode:
        result.check("git_tracked_clean", False, process.stderr.strip())
        return
    tracked = [item for item in process.stdout.split("\0") if item]
    hits = 0
    exceptions = _exceptions(policy)
    for relative in tracked:
        try:
            path = confined(clone, relative)
        except SafetyError as error:
            result.check("git_tracked_paths_confined", False, str(error))
            continue
        if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIX:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            for name, pattern in _rules(policy):
                if not pattern.search(line):
                    continue
                if any(relative == ep and erx.search(line) for ep, erx, _ in exceptions):
                    continue
                result.findings.append(Finding(
                    relative, line_number, f"{name}(tracked)", line.strip()[:140],
                ))
                hits += 1
    result.check("git_tracked_clean", hits == 0,
                 f"{len(tracked)} tracked files scanned, {hits} forbidden hits")


def run_compileall(root: Path, result: VerifyResult) -> None:
    process = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "components", "bases", "scripts"],
        cwd=root, capture_output=True, text=True,
    )
    errors = [line for line in (process.stdout + process.stderr).splitlines()
              if "Error" in line or "SyntaxError" in line]
    result.check("compileall", process.returncode == 0 and not errors,
                 "; ".join(errors[:5]) or "no syntax errors")


def run_pytest_collect(root: Path, result: VerifyResult) -> None:
    paths = [str(path) for group in ("bases", "components")
             for path in sorted((root / group).glob("*/src")) if path.is_dir()]
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=root, capture_output=True, text=True,
        env={"PYTHONPATH": ":".join(paths), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    lines = (process.stdout + process.stderr).strip().splitlines()
    errors = sum(line.startswith("ERROR ") for line in lines)
    result.check("pytest_collect", errors == 0 and process.returncode in (0, 5),
                 f"rc={process.returncode} errors={errors} :: {(lines[-1] if lines else '')[:160]}")


def render(result: VerifyResult) -> str:
    output = ["=" * 72, "FAIL-CLOSED VERIFY", "=" * 72]
    if result.findings:
        output.append(f"FORBIDDEN PATTERN HITS: {len(result.findings)}")
        for finding in result.findings[:40]:
            output.append(f"   {finding.path}:{finding.line} [{finding.rule}] {finding.excerpt}")
    else:
        output.append("no forbidden patterns found")
    if result.exceptions_applied:
        output.extend(["", "documented exceptions applied:",
                       *(f"   {item}" for item in result.exceptions_applied)])
    output.extend(["", "=" * 72, "STRUCTURAL VERIFY", "=" * 72])
    output.extend(f"   [{'PASS' if passed else 'FAIL'}] {name:34s} {detail}"
                  for name, passed, detail in result.structural)
    output.extend(["", f"RESULT: {'PASS' if result.ok else 'FAIL'}"])
    return "\n".join(output)
