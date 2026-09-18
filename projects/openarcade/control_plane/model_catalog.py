"""Curated + live per-provider model catalog: friendly label -> real model ID.

For Bedrock we prefer LIVE discovery — querying the account's active
inference profiles — so deprecated / end-of-life models never appear (they are
a security risk). Falls back to a minimal current-model list if discovery
fails. Other providers keep a small static catalog; ollama/litellm are
free-text.

Pure-ish: only boto3 (already a dependency), no Strands/Flet imports.
"""

from __future__ import annotations

# --- Static catalogs (fallbacks / providers without live discovery) ---
# Bedrock fallback is intentionally minimal and CURRENT (Sonnet 4.5, confirmed
# non-deprecated). Live discovery below supersedes this when creds are present.
_BEDROCK_FALLBACK: tuple[tuple[str, str], ...] = (
    ("Claude Sonnet 4.5", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"),
)

MODEL_CATALOG: dict[str, tuple[tuple[str, str], ...]] = {
    "bedrock": _BEDROCK_FALLBACK,
    "openai": (
        ("GPT-4o", "gpt-4o"),
        ("GPT-4o mini (fast)", "gpt-4o-mini"),
        ("o3-mini (reasoning)", "o3-mini"),
    ),
    "anthropic": (
        ("Claude Sonnet 4.5", "claude-sonnet-4-5"),
        ("Claude Haiku 4.5 (fast)", "claude-haiku-4-5"),
    ),
    "gemini": (
        ("Gemini 2.5 Pro", "gemini-2.5-pro"),
        ("Gemini 2.5 Flash (fast)", "gemini-2.5-flash"),
    ),
}

# Module-level cache so the live Bedrock query runs at most once per process.
_UNRESOLVED: object = object()
_RESOLVED_PROFILE: object | str | None = _UNRESOLVED
_BEDROCK_LIVE_CACHE: tuple[tuple[str, str], ...] | None = None


def resolve_boto_session():  # noqa: ANN201
    """Return a boto3 Session with working credentials — profile-agnostic.

    Tries the default chain first, then every configured profile, and returns
    the first whose STS get_caller_identity succeeds. The winning profile is
    cached, but a FRESH Session is built each call so rotated creds are picked
    up. Returns None if nothing resolves. boto3-only (no Strands import) so the
    lean UI/settings path can use it.
    """
    import boto3

    global _RESOLVED_PROFILE

    def _works(sess) -> bool:
        try:
            sess.client("sts").get_caller_identity()
            return True
        except Exception:
            return False

    if _RESOLVED_PROFILE is not _UNRESOLVED:
        return boto3.Session() if _RESOLVED_PROFILE is None else boto3.Session(
            profile_name=_RESOLVED_PROFILE
        )

    default = boto3.Session()
    if _works(default):
        _RESOLVED_PROFILE = None
        return default
    for prof in default.available_profiles:
        try:
            sess = boto3.Session(profile_name=prof)
        except Exception:
            continue
        if _works(sess):
            _RESOLVED_PROFILE = prof
            return sess
    return None


def list_bedrock_models(session=None) -> tuple[tuple[str, str], ...] | None:
    """Discover the account's ACTIVE Claude inference profiles (never deprecated).

    Returns (label, inferenceProfileId) pairs, newest-looking first. Returns
    None on any failure (no creds, no access, API error) so the caller can fall
    back to the static current-model list. Cached per process.
    """
    global _BEDROCK_LIVE_CACHE
    if _BEDROCK_LIVE_CACHE is not None:
        return _BEDROCK_LIVE_CACHE
    try:
        sess = session or resolve_boto_session()
        if sess is None:
            return None
        region = sess.region_name or "us-east-1"
        client = sess.client("bedrock", region_name=region)
        resp = client.list_inference_profiles(typeEquals="SYSTEM_DEFINED", maxResults=100)
        out: list[tuple[str, str]] = []
        for p in resp.get("inferenceProfileSummaries", []):
            if p.get("status") != "ACTIVE":
                continue  # skip anything not currently active (deprecated/EOL)
            name = (p.get("inferenceProfileName") or "").strip()
            pid = p.get("inferenceProfileId") or ""
            if pid and "claude" in name.lower():
                out.append((name, pid))
        # Prefer newer/US profiles first; stable, readable ordering.
        out.sort(key=lambda t: t[0])
        _BEDROCK_LIVE_CACHE = tuple(out) or None
        return _BEDROCK_LIVE_CACHE
    except Exception:
        return None


def models_for(provider: str) -> tuple[tuple[str, str], ...]:
    """Return (label, model_id) choices for a provider, or () if free-text.

    For Bedrock, prefer LIVE discovery (active, non-deprecated models); fall
    back to the static current list if discovery is unavailable.
    """
    if provider == "bedrock":
        live = list_bedrock_models()
        return live if live else _BEDROCK_FALLBACK
    return MODEL_CATALOG.get(provider, ())


def label_for_model(provider: str, model_id: str) -> str:
    """Reverse lookup: the friendly label for a stored model_id (or the id itself)."""
    for label, mid in models_for(provider):
        if mid == model_id:
            return label
    return model_id
