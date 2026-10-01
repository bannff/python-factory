"""Read-only host toolchain probes for native mobile experiment planning."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import (
    NativePreflightOutput,
    NativeRunResult,
    NativeScenario,
    NativeTarget,
    PreflightReport,
    ToolchainRequirement,
    scenario_digest,
)
from .device_inventory import android_avd_target_available, simulator_target_available


@dataclass(frozen=True)
class ProbeDependencies:
    """Inject operating-system boundaries so probe decisions are deterministic in tests."""

    which: Callable[[str], str | None] = shutil.which
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    host_platform: str = platform.system().lower()
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    avd_home: Path | None = None


def _command(
    deps: ProbeDependencies,
    argv: Sequence[str],
    *,
    available: bool,
    missing_detail: str | None = None,
) -> tuple[bool, str, str]:
    if not available:
        return False, missing_detail or f"required executable {argv[0]!r} was not found on PATH", ""
    try:
        result = deps.run(
            list(argv), capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{argv[0]} probe failed: {type(exc).__name__}", ""
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0:
        detail = output.splitlines()[0] if output else f"exit status {result.returncode}"
        return False, f"{argv[0]} probe failed: {detail[:180]}", output
    summary = output.splitlines()[0][:180] if output else "command succeeded"
    return True, summary, output


def _sdk_executable(sdk_path: Path | None, relative_path: str) -> Path | None:
    """Resolve a required Android binary only inside the configured SDK root."""
    if sdk_path is None:
        return None
    executable_names = (relative_path, f"{relative_path}.exe")
    for executable_name in executable_names:
        candidate = sdk_path / executable_name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _report(
    scenario: NativeScenario,
    checks: Sequence[tuple[str, bool, str]],
    commands: tuple[str, ...],
) -> PreflightReport:
    requirements = tuple(
        ToolchainRequirement(name=name, available=available, detail=detail)
        for name, available, detail in checks
    )
    blocked = tuple(
        f"{item.name}: {item.detail}" for item in requirements if not item.available
    )
    return PreflightReport(
        scenario_id=scenario.scenario_id,
        target=scenario.target,
        status="ready" if not blocked else "blocked",
        requirements=requirements,
        blocked_reasons=blocked,
        planned_commands=commands,
    )


def _probe_ios(scenario: NativeScenario, deps: ProbeDependencies) -> PreflightReport:
    checks: list[tuple[str, bool, str]] = [
        (
            "macOS host",
            deps.host_platform == "darwin",
            f"host platform is {deps.host_platform}; iOS Simulator requires macOS",
        )
    ]
    xcodebuild_ok, xcodebuild_detail, _ = _command(
        deps, ("xcodebuild", "-version"), available=deps.which("xcodebuild") is not None
    )
    checks.append(("xcodebuild", xcodebuild_ok, xcodebuild_detail))

    xcrun_exists = deps.which("xcrun") is not None
    xcrun_ok, xcrun_detail, simctl_path_output = _command(
        deps, ("xcrun", "--find", "simctl"), available=xcrun_exists
    )
    checks.append(("xcrun", xcrun_ok, xcrun_detail))
    simctl_path = xcrun_ok and bool(simctl_path_output.strip())
    checks.append(("simctl", simctl_path, "xcrun must resolve Apple's simctl executable" if not simctl_path else "xcrun resolved simctl"))

    devices_available = False
    device_detail = "simctl device listing was not run because simctl is unavailable"
    if simctl_path:
        listed, listing_detail, inventory = _command(
            deps, ("xcrun", "simctl", "list", "devices", "available"), available=True
        )
        if listed:
            devices_available = simulator_target_available(
                inventory, scenario.device_name, scenario.os_version
            )
            device_detail = (
                f"requested simulator {scenario.device_name!r} on {scenario.os_version!r} is available"
                if devices_available
                else f"no available simulator exactly matches {scenario.device_name!r} on {scenario.os_version!r}"
            )
        else:
            device_detail = listing_detail
    checks.append(("requested simulator device and OS", devices_available, device_detail))
    return _report(
        scenario,
        checks,
        ("xcodebuild -version", "xcrun --find simctl", "xcrun simctl list devices available"),
    )


def _probe_android(scenario: NativeScenario, deps: ProbeDependencies) -> PreflightReport:
    sdk_raw = deps.environ.get("ANDROID_SDK_ROOT") or deps.environ.get("ANDROID_HOME")
    sdk_path = Path(sdk_raw).expanduser() if sdk_raw else None
    sdk_layout_ok = bool(
        sdk_path
        and sdk_path.is_dir()
        and (sdk_path / "platform-tools").is_dir()
        and (sdk_path / "emulator").is_dir()
        and any((sdk_path / "platforms").glob("android-*"))
    )
    checks: list[tuple[str, bool, str]] = [
        (
            "Android SDK configuration",
            sdk_layout_ok,
            "configured Android SDK has platform-tools, emulator, and an installed Android platform"
            if sdk_layout_ok
            else "ANDROID_SDK_ROOT/ANDROID_HOME must name an SDK with platform-tools, emulator, and an installed Android platform",
        )
    ]

    java_ok, java_detail, _ = _command(
        deps, ("java", "-version"), available=deps.which("java") is not None
    )
    checks.append(("java", java_ok, java_detail))
    adb_path = _sdk_executable(sdk_path, "platform-tools/adb")
    adb_expected = sdk_path / "platform-tools" / "adb" if sdk_path else Path("<ANDROID_SDK_ROOT>/platform-tools/adb")
    adb_ok, adb_detail, _ = _command(
        deps,
        (str(adb_path or adb_expected), "version"),
        available=adb_path is not None,
        missing_detail=f"adb is missing or not executable under configured SDK root at {adb_expected}",
    )
    checks.append(("adb", adb_ok, adb_detail))
    emulator_path = _sdk_executable(sdk_path, "emulator/emulator")
    emulator_expected = sdk_path / "emulator" / "emulator" if sdk_path else Path("<ANDROID_SDK_ROOT>/emulator/emulator")
    emulator_available = emulator_path is not None
    avds: list[str] = []
    target_available = False
    emulator_detail = (
        f"emulator is missing or not executable under configured SDK root at {emulator_expected}"
    )
    if emulator_available:
        try:
            result = deps.run(
                [str(emulator_path), "-list-avds"], capture_output=True,
                text=True, timeout=10, check=False,
            )
            emulator_available = result.returncode == 0
            avds = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            avd_home = deps.avd_home or Path(
                deps.environ.get("ANDROID_AVD_HOME", str(Path.home() / ".android" / "avd"))
            ).expanduser()
            target_available = android_avd_target_available(
                avds, avd_home, scenario.device_name, scenario.os_version
            )
            emulator_detail = (
                f"emulator probe succeeded; {len(avds)} AVD(s) available"
                if emulator_available
                else "emulator -list-avds failed"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            emulator_available = False
            emulator_detail = f"emulator probe failed: {type(exc).__name__}"
    checks.append(("emulator", emulator_available, emulator_detail))
    checks.append(
        (
            "requested Android device and OS",
            target_available,
            f"an AVD matches {scenario.device_name!r} on {scenario.os_version!r}"
            if target_available
            else f"no listed AVD matches {scenario.device_name!r} on {scenario.os_version!r}",
        )
    )
    return _report(
        scenario,
        checks,
        ("java -version", "adb version", "emulator -list-avds"),
    )


def probe_host(
    scenario: NativeScenario, *, deps: ProbeDependencies | None = None
) -> NativePreflightOutput:
    """Probe only host prerequisites; never builds or launches an application."""
    deps = deps or ProbeDependencies()
    report = (
        _probe_ios(scenario, deps)
        if scenario.target is NativeTarget.IOS_SIMULATOR
        else _probe_android(scenario, deps)
    )
    digest = scenario_digest(scenario)
    result = NativeRunResult(
        schema_version=1,
        result_id=f"preflight-{digest[:16]}",
        scenario_id=scenario.scenario_id,
        scenario_sha256=digest,
        target=scenario.target,
        status="preflight_only",
        model_sha256=scenario.model_sha256,
        dataset_sha256=scenario.dataset_sha256,
        runtime_version=None,
        native_artifact_sha256=None,
        parity=None,
    )
    return NativePreflightOutput(preflight=report, result=result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="path to a strict NativeScenario JSON file")
    args = parser.parse_args(argv)
    scenario = NativeScenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
    output = probe_host(scenario)
    print(output.model_dump_json(indent=2))
    return 0 if output.preflight.status == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
