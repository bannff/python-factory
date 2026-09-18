"""Red team graph defaults.

bd python-factory-nrt5: ``REDTEAM_SANDBOX_GRAPH`` (v1 5-swarm chain
recon → pull-artifacts → setup-sandbox → scan → prove,
id ``redteam-sandbox-pipeline``) was deleted. Its setup-sandbox CFN
provisioning is superseded by the LocalStack-direct sandbox-setup
workflow (bd-m4cp); its pull-artifacts CDK reading is subsumed by
recon-app via the cdk-analysis skill (bd-s5ev).

The remaining standalone DAST scan (``SCAN_IDOR_GRAPH``) and the
focused redteam swarms (``RT_FOCUSED_SWARMS``) carry forward
independently of the meta-pipeline.
"""
from __future__ import annotations

from .defaults_redteam_swarms import RT_FOCUSED_SWARMS
from .defaults_redteam_idor import SCAN_IDOR_GRAPH

REDTEAM_SWARMS: list[dict] = RT_FOCUSED_SWARMS
REDTEAM_AGENTS: list[dict] = []
REDTEAM_GRAPHS: list[dict] = [SCAN_IDOR_GRAPH]
