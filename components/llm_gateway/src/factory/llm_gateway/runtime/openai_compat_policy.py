"""Fail-closed policy for named OpenAI-compatible chat profiles."""
from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit

_PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
_CREDENTIALS = (
    re.compile(r"gh[pousr]_[a-z0-9_]{20,}"),
    re.compile(r"github_pat_[a-z0-9_]{20,}"),
    re.compile(r"sk-(?:proj_)?[a-z0-9_-]{20,}"),
    re.compile(r"(?:sk|pk)_(?:live|test)_[a-z0-9_]{16,}"),
    re.compile(r"xox[baprs]-[a-z0-9-]{10,}"),
)
_PROFILE_LIST_ENV = "COMPANION_X_OPENAI_COMPAT_PROFILES"
_REMOTE_ORIGINS_ENV = "COMPANION_X_OPENAI_COMPAT_REMOTE_ORIGINS"
SAFE_PROFILE_ERROR = "chat profile unavailable"


def configured_profile_names() -> tuple[str, ...]:
    """Return validated, de-duplicated profile names from the explicit allowlist."""
    values = tuple(filter(None, (
        item.strip() for item in os.getenv(_PROFILE_LIST_ENV, "").split(",")
    )))
    if any(not credential_clean_profile_name(item) for item in values):
        raise ValueError(SAFE_PROFILE_ERROR)
    return tuple(dict.fromkeys(values))


def credential_clean_profile_name(value: str) -> bool:
    """Accept only bounded identifiers that are not shaped like known credentials."""
    return bool(_PROFILE_RE.fullmatch(value)) and not any(
        pattern.fullmatch(value) for pattern in _CREDENTIALS
    )


def profile_env_stem(name: str) -> str:
    """Derive a non-secret environment stem after validating the profile name."""
    if not credential_clean_profile_name(name):
        raise ValueError(SAFE_PROFILE_ERROR)
    return name.upper().replace("-", "_")


def resolve_profile_inputs(name: str) -> tuple[str, str, str]:
    """Resolve safe profile fields while retaining only the credential env name."""
    if name not in configured_profile_names():
        raise ValueError(SAFE_PROFILE_ERROR)
    stem = profile_env_stem(name)
    base_url = os.getenv(f"{stem}_BASE_URL", "").strip()
    api_key_env = f"{stem}_API_KEY"
    api_key = os.getenv(api_key_env, "").strip()
    model = os.getenv(f"{stem}_MODEL", "").strip()
    if not base_url or not api_key or not model:
        raise ValueError(SAFE_PROFILE_ERROR)
    try:
        return validate_base_url(base_url), api_key_env, model
    except (OSError, ValueError) as exc:
        raise ValueError(SAFE_PROFILE_ERROR) from exc


def validate_base_url(value: str) -> str:
    """Allow loopback HTTP or operator-allowlisted remote HTTPS endpoints."""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(SAFE_PROFILE_ERROR)
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(SAFE_PROFILE_ERROR) from exc
    if parsed.scheme == "https" and _origin(parsed) in _remote_origins():
        return value.rstrip("/")
    if _host_is_loopback(parsed.hostname, parsed.port):
        return value.rstrip("/")
    raise ValueError(SAFE_PROFILE_ERROR)


def _host_is_loopback(host: str, port: int | None) -> bool:
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(SAFE_PROFILE_ERROR) from exc
    return bool(addresses) and all(
        ipaddress.ip_address(item[4][0]).is_loopback for item in addresses
    )


def _origin(parsed) -> str:
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if parsed.scheme == "https" else 80
    suffix = "" if parsed.port in {None, default_port} else f":{parsed.port}"
    return f"{parsed.scheme}://{host}{suffix}"


def _remote_origins() -> frozenset[str]:
    origins: set[str] = set()
    for raw in os.getenv(_REMOTE_ORIGINS_ENV, "").split(","):
        candidate = raw.strip().rstrip("/")
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(SAFE_PROFILE_ERROR)
        origins.add(_origin(parsed))
    return frozenset(origins)


__all__ = [
    "SAFE_PROFILE_ERROR", "configured_profile_names",
    "credential_clean_profile_name", "profile_env_stem",
    "resolve_profile_inputs", "validate_base_url",
]
