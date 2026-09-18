"""Canary: composition-root AWS profile promotion (bd:python-factory-gtyb7).

Pins that ``_promote_aws_profile`` makes the namespaced
``COMPANION_X_AWS_PROFILE`` authoritative over an ambient ``AWS_PROFILE``
(the dev-shell shadow that ``uv run --env-file`` can't override). If this
behavior regresses, the backend silently builds boto3 clients against the
wrong account again.
"""
from __future__ import annotations

import os

from factory.api.main import _promote_aws_profile


def test_promotes_namespaced_over_ambient(monkeypatch) -> None:
    """The shadow case: ambient AWS_PROFILE is overwritten by the namespaced var."""
    monkeypatch.setenv("AWS_PROFILE", "art-support")  # the dev-shell shadow
    monkeypatch.setenv("COMPANION_X_AWS_PROFILE", "art-ml")
    _promote_aws_profile()
    assert os.environ["AWS_PROFILE"] == "art-ml"


def test_sets_when_ambient_unset(monkeypatch) -> None:
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("COMPANION_X_AWS_PROFILE", "art-ml")
    _promote_aws_profile()
    assert os.environ["AWS_PROFILE"] == "art-ml"


def test_noop_when_namespaced_unset(monkeypatch) -> None:
    """Back-compat: no namespaced var → ambient AWS_PROFILE untouched."""
    monkeypatch.delenv("COMPANION_X_AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_PROFILE", "some-other-profile")
    _promote_aws_profile()
    assert os.environ["AWS_PROFILE"] == "some-other-profile"


def test_noop_when_both_unset(monkeypatch) -> None:
    monkeypatch.delenv("COMPANION_X_AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    _promote_aws_profile()
    assert "AWS_PROFILE" not in os.environ
