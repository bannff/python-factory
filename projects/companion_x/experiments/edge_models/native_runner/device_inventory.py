"""Pure target matching for simulator listings and local Android AVD profiles."""
from __future__ import annotations

import re
from pathlib import Path

_SIMULATOR_ROW = re.compile(r"^(?P<name>.+?) \([0-9A-Fa-f-]{36}\) \((?:Booted|Shutdown)\)$")
_ANDROID_API = re.compile(r"(?:android|api)[\s_-]*(\d+)", re.IGNORECASE)
_ANDROID_RELEASE = re.compile(r"android\s+(\d+(?:\.\d+)?)", re.IGNORECASE)
_RELEASE_API = {"15": "35", "14": "34", "13": "33", "12": "31"}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def simulator_target_available(inventory: str, device_name: str, os_version: str) -> bool:
    """Require an exact simulator device name under the requested runtime heading."""
    runtime: str | None = None
    requested_runtime = _normalize(os_version)
    for raw_line in inventory.splitlines():
        line = raw_line.strip()
        if line.startswith("-- ") and line.endswith(" --"):
            runtime = line[3:-3].strip()
            continue
        match = _SIMULATOR_ROW.fullmatch(line)
        if (
            match
            and _normalize(match.group("name")) == _normalize(device_name)
            and runtime
            and _normalize(runtime) == requested_runtime
        ):
            return True
    return False


def _read_ini(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";")) or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip()
    except OSError:
        return {}
    return values


def _android_api(config: dict[str, str]) -> str | None:
    targets = (config.get("target", ""), config.get("image.sysdir.1", ""))
    for target in targets:
        match = _ANDROID_API.search(target)
        if match:
            return match.group(1)
    return None


def _requested_android_api(os_version: str) -> str | None:
    release = _ANDROID_RELEASE.fullmatch(os_version.strip())
    if release:
        return _RELEASE_API.get(release.group(1).split(".", 1)[0])
    match = _ANDROID_API.search(os_version)
    if match:
        return match.group(1)
    return None


def android_avd_target_available(
    avd_names: list[str], avd_home: Path, device_name: str, os_version: str
) -> bool:
    """Match requested hardware identity and Android API against listed AVD profiles."""
    requested_api = _requested_android_api(os_version)
    if requested_api is None:
        return False
    requested_device = _normalize(device_name)
    for avd_name in avd_names:
        config = _read_ini(avd_home / f"{avd_name}.avd" / "config.ini")
        # AVD names and display names are user-defined labels; they don't prove
        # which hardware profile the emulator actually configures. Require the
        # SDK's hardware identity field and API level from config.ini.
        hardware_identity = _normalize(config.get("hw.device.name", ""))
        if hardware_identity == requested_device and _android_api(config) == requested_api:
            return True
    return False
