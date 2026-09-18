"""Test a single SAST graph node in isolation.

Runs one agent with the SAST prompt against WebGoat source,
records tool usage and findings to an experiment file.

Usage:
    python -m factory.agent.scripts.test_single_node \
        --agent-id sonnet-sast \
        --run-id test-sonnet-001 \
        --output /path/to/experiments/
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
logging.getLogger("strands.agent").setLevel(logging.INFO)
logger = logging.getLogger("test-node")


class ToolTracker:
    """Tracks tool calls made by the agent."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, tool_name: str, args: dict, result: Any) -> None:
        self.calls.append({
            "tool": tool_name, "args_keys": list(args.keys()),
            "result_preview": str(result)[:200],
            "timestamp": time.time(),
        })

    def summary(self) -> dict[str, Any]:
        tools_used = {}
        for c in self.calls:
            t = c["tool"]
            tools_used[t] = tools_used.get(t, 0) + 1
        return {
            "total_calls": len(self.calls),
            "tools_used": tools_used,
            "calls": self.calls,
        }


async def run_single_agent(
    agent_id: str, run_id: str, output_dir: str,
    vuln_class: str = "IDOR", target_app: str = "webgoat",
    workspace: str = "/tmp/factory-sast/webgoat/src/main/java/org/owasp/webgoat/lessons/idor",
) -> dict[str, Any]:
    """Run a single SAST agent and record results."""
    t0 = time.time()

    # 1. Init aggregator for MCP tools
    os.environ.setdefault("EAGER_LOAD", "0")
    from factory.mcp_server.interface import get_server, get_aggregator
    get_server()
    agg = get_aggregator()
    if not agg:
        return {"error": "No aggregator"}

    # 2. Load required bricks
    for brick in ["graph", "security", "memory", "kb"]:
        try:
            agg.get_brick_tools(brick)
        except Exception as e:
            logger.warning("Skip brick %s: %s", brick, e)

    # 3. Build scoped MCPClient
    tool_names: set[str] = set()
    for brick in ["graph", "security", "memory", "kb"]:
        tool_names.update(agg.get_brick_tool_names(brick))
    from factory.agent.runtime.adapters.strands_mcp_graph import (
        create_mcp_client,
    )
    mcp_client = create_mcp_client(allowlist=tool_names)
    logger.info("Created MCPClient with %d tool names", len(tool_names))

    # 4. Resolve graph config to get the agent node
    from factory.agent.registry.defaults_code_scan import SAST_SCAN_GRAPH
    node_config = None
    for n in SAST_SCAN_GRAPH["nodes"]:
        if n["id"] == agent_id:
            node_config = n
            break
    if not node_config:
        return {"error": f"Agent '{agent_id}' not in graph"}

    # 5. Build the agent via GraphNodeBuilder
    from factory.agent.executors.graph_nodes import GraphNodeBuilder
    builder = GraphNodeBuilder()
    builder._mcp_tools = [mcp_client]
    context = {
        "vuln_class": vuln_class, "target_app": target_app,
        "run_id": run_id, "sast_workspace": workspace,
        "target_packages": "org.owasp.webgoat.lessons.idor",
    }
    agent = builder._build_agent_node(node_config, context)
    logger.info("Built agent: %s (model=%s)", agent_id, node_config["model"])

    # 6. Run the agent
    task = (
        f"Scan {target_app} source code in {workspace} for "
        f"{vuln_class} vulnerabilities. Read every file, analyze "
        f"for missing authorization checks, store findings."
    )
    logger.info("Invoking agent with task: %s", task[:100])
    try:
        result = await agent.invoke_async(task)
        output = str(result)
        status = "completed"
    except Exception as e:
        output = str(e)
        status = "error"
        logger.error("Agent failed: %s", e)

    elapsed = time.time() - t0

    # 7. Query graph for findings from this agent
    findings = []
    try:
        qr = agg.invoke_tool(
            "graph_graph_find_entities", entity_type=None,
            properties={"run_id": run_id}, limit=20,
        )
        entities = qr.data.entities if qr and qr.ok and qr.data is not None else []
        findings = [
            entity.properties for entity in entities
            if entity.properties.get("agent_id") == agent_id
            or (entity.properties.get("cwe") and entity.id.startswith("finding-"))
        ]
    except Exception as e:
        logger.warning("Finding query failed: %s", e)

    # 8. Build experiment record
    record = {
        "experiment": "single-node-sast",
        "agent_id": agent_id,
        "model": node_config["model"],
        "run_id": run_id,
        "vuln_class": vuln_class,
        "target_app": target_app,
        "workspace": workspace,
        "status": status,
        "elapsed_seconds": round(elapsed, 1),
        "findings_count": len(findings),
        "findings": findings,
        "output_preview": output[:3000],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # 9. Write to experiments dir
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    fname = out_path / f"{run_id}.json"
    fname.write_text(json.dumps(record, indent=2, default=str))
    logger.info("Wrote %s (%.1fs, %d findings)", fname, elapsed, len(findings))
    return record


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--agent-id", required=True,
                   help="Node ID: sonnet-sast, gptoss-sast, nova2-sast")
    p.add_argument("--run-id", required=True, help="Unique run identifier")
    p.add_argument("--output", default="projects/companion_x/challenges/experiments",
                   help="Output directory for experiment records")
    p.add_argument("--vuln-class", default="IDOR")
    p.add_argument("--target-app", default="webgoat")
    p.add_argument("--workspace",
                   default="/tmp/factory-sast/webgoat/src/main/java/org/owasp/webgoat/lessons/idor")
    args = p.parse_args()
    asyncio.run(run_single_agent(
        args.agent_id, args.run_id, args.output,
        args.vuln_class, args.target_app, args.workspace,
    ))
