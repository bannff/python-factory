# Dataset Generation Design

The authoritative design, acceptance criteria, and implementation status are
in `.github/spec/ml-dataset-generation.md`. The interfaces below are the
original design anchors; implementation work must follow the linked canonical
spec and a corresponding Beads issue.

## Overview
Dataset generation is now owned by the `components/dataset/` brick. The system must operate asynchronously to prevent event loop blocking.

## Core Abstractions

### 1. Interface (components/dataset/src/factory/dataset/interface.py)
A lightweight public contract focused on job management:
* `start_generation_job(config: dict) -> JobID`
* `get_job_status(job_id: JobID) -> JobStatus`
* `get_dataset_uri(job_id: JobID) -> str`

### 2. Execution Layer (Worker Queue)
The multi-hour pipeline (legacy `s2m`/`apigenmt`) will run entirely out-of-process.
* The `dataset` interface acts as the dispatch.
* A persistent queue/worker picks up the task; the concrete backend is selected
	and tracked in Beads before implementation.
* The worker resolves a versioned recipe, runs checkpointable stage adapters,
	applies schema and quality gates, and persists immutable stage artifacts.
* Recovery semantics include leases, retries, cancellation, restart recovery,
	idempotency, and resume from the last valid checkpoint.

### 3. MCP Surface (bases/mcp_server or components/dataset/mcp/)
Tools are purely non-blocking state managers:
* `submit_pipeline_tool`
* `poll_status_tool`

## Removal of Cross-Coupling
The `machine_learning` brick interface will no longer manage generation. Its models will expect a resolvable `dataset_uri` representing an artifact produced by the `dataset` brick.

## Reproducibility and Companion-X Control Plane

The completed bundle must contain a manifest with recipe, input, stage,
context, tool-schema, quality, provenance, and authorized-fallback digests. A
selected named training view must produce a verified `training_uri` before the
ML backend launches. Companion-X may author or select the recipe, freeze
bounded graph/memory/tool-schema context through MCP, submit the job, observe
status, and hand the artifact to ML; it does not execute or retry stages.
