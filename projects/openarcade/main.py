"""OpenArcade entrypoint — proves the frontend brick wiring resolves.

Boots on the `ui` brick (the Flet/Flutter frontend substrate OpenArcade renders
through). The `evals` brick is wired in pyproject for later use by the agentic
test harness, but is NOT imported at startup — its top-level module boots an MCP
server (fastmcp) that the kiosk does not need.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger()


def main() -> None:
    # Prove the ui brick + its Flet adapter resolve under OpenArcade's lean deps.
    import factory.ui  # noqa: F401
    from factory.ui.runtime.adapters import flet_adapter  # noqa: F401

    log.info(
        "openarcade.ready",
        ui_brick="factory.ui",
        frontend_adapter="flet",
    )


if __name__ == "__main__":
    main()
