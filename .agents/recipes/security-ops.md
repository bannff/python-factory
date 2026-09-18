# Recipe: Security Operations

Full security workflow: analyze targets, query the resource graph, mine the data lake, trace provenance, enforce access control, and audit everything.

## Bricks Used
- `security` — Threat modeling, vulnerability scanning, code analysis, finding persistence, deterministic endpoint scanning, deterministic confidence classification, deterministic taint tracing
- `veritas` — Security knowledge graph (6B+ nodes): AWS resources, permissions, deployments, security posture
- `sipp` — Security data lake: database/table discovery, schema inspection, Spark SQL queries
- `gated_garden` — Software provenance tracking: version-level artifact lineage across Brazil/GitFarm/Apollo/Pipelines
- `sandbox` — LocalStack environment provisioning (docker compose + awscli sidecar) for AWS pentest workflows
- `agent` — AWS pentest swarm preset (aws-recon → iam-auditor → exploit-tester → report-writer)
- `permissions` — Policy-based access control
- `auth` — Token verification
- `logger` — Audit logging

## Security Domain Overview

The 4 security-domain bricks form a pipeline:

1. **veritas** — Understand the target. Query the Veritas graph for resource topology, permissions, deployment chains, and security posture. This is your map.
2. **sipp** — Mine historical data. Query the SIPP data lake for vulnerabilities, security events, compliance scores, and auth logs. This is your evidence.
3. **security** — Analyze and find issues. Run code analysis, threat modeling, or vuln scanning against the target. This is your assessment.
4. **gated_garden** — Assess blast radius. Trace software provenance to understand what's affected if a vulnerability is exploited. This is your impact analysis.

Workflow: `veritas` (what exists?) → `sipp` (what happened?) → `security` (what's wrong?) → `gated_garden` (what's at risk?)

## Prerequisites

- No AWS required (all bricks support memory adapters)
- Bricks instantiated with memory adapters

## Steps

### Step 1: Initialize All Bricks

```python
import asyncio, tempfile
from pathlib import Path
import yaml

# Security
from factory.security.runtime.adapters.mock import MockAnalyzer
from factory.security.runtime.runtime import SecurityRuntime
security = SecurityRuntime(analyzer=MockAnalyzer())

# Veritas — memory adapter returns sample graph data
from factory.veritas.runtime.runtime import VeritasRuntime
veritas = VeritasRuntime({"backend": "memory"})

# SIPP — memory adapter returns sample catalog + query results
from factory.sipp.runtime.runtime import SIPPRuntime
sipp = SIPPRuntime({"backend": "memory"})

# GatedGarden — memory adapter returns sample provenance data
from factory.gated_garden.runtime.runtime import GatedGardenRuntime
gated_garden = GatedGardenRuntime({"backend": "memory"})

# Permissions
tmpdir_perm = Path(tempfile.mkdtemp())
(tmpdir_perm / "policies").mkdir(parents=True, exist_ok=True)
(tmpdir_perm / "settings.yaml").write_text(yaml.safe_dump({
    "schema_version": 1, "service_name": "security-ops-recipe",
    "backend": "filesystem",
    "policy_store": {"policies_subdir": "policies"},
}))
(tmpdir_perm / "policies" / "security.yaml").write_text(yaml.safe_dump({
    "schema_version": 1, "id": "security-policy", "name": "Security Operations Policy", "version": "0.1",
    "rules": [
        {"id": "allow_scan", "effect": "allow", "actions": ["scan"], "resource_types": ["codebase"]},
        {"id": "deny_deploy_unscanned", "effect": "deny", "actions": ["deploy"], "resource_types": ["artifact"],
         "conditions": [{"field": "context.scanned", "operator": "equals", "value": False}]},
    ],
}))
from factory.permissions.runtime.runtime import PermissionsRuntime
permissions = PermissionsRuntime.from_config_dir(tmpdir_perm)

# Auth + Logger
from factory.auth.runtime.adapters import MemoryBackend
auth_backend = MemoryBackend()
tmpdir_log = Path(tempfile.mkdtemp())
from factory.logger.runtime.runtime import LoggerRuntime
logger = LoggerRuntime(log_dir=str(tmpdir_log))
```

### Step 2: Query Veritas for Resource Topology

```python
# Get app topology — resources, pipelines, environments
topology = veritas.get_app_topology(app_name="my-service")
# Get security posture — cert status, color, ring, reviews
posture = veritas.get_security_posture(identifier="my-service")
# Trace permissions for a specific resource
perms = veritas.get_resource_permissions(resource_type="Lambda", resource_identifier="my-service")
# Raw Cypher for custom queries
results = veritas.query("MATCH (a:VeritasApp)-[:OWNS]->(r) WHERE a.veritas_app_name CONTAINS 'my-service' RETURN r LIMIT 10")
```

### Step 3: Query SIPP for Historical Security Data

```python
# Discover available databases and tables
databases = sipp.list_databases()
tables = sipp.list_tables("security")
schema = sipp.get_schema("security", "vulnerabilities")
# Execute a query against the data lake
from factory.sipp.runtime.models import QueryRequest
query_id = sipp.submit_query(QueryRequest(
    sql_expression="SELECT severity, COUNT(*) FROM security.vulnerabilities GROUP BY severity LIMIT 100",
    group="TEAM-AppSec", timeout=300, create_preview=True,
))
status = sipp.get_query_status(query_id)
preview = sipp.get_query_preview(query_id)  # CSV preview, up to 500 rows
```

### Step 4: Run Security Analysis

```python
from factory.security.core import AnalysisType
analysis = await security.analyze(target="components/auth/", analysis_type=AnalysisType.CODE_ANALYSIS)
# Returns: AnalysisResult(analysis_id="...", findings=[...], status="completed")
```

### Step 4b: Scan Endpoints (Deterministic)

```python
# Regex-based endpoint discovery — no LLM, no AWS credentials needed
from factory.security.runtime.endpoint_scanner import scan_endpoints

source = open("components/auth/src/factory/auth/mcp/server.py").read()
endpoints = scan_endpoints(source, framework="auto", file_path="auth/mcp/server.py")
# Returns: [{"method": "POST", "path": "/login", "file": "...", "line": 42,
#            "params": [{"name": "username", "source": "body"}], "framework": "flask"}, ...]

# Via MCP tool:
# result = security.scan_endpoints(source_code=source, framework="flask", file_path="server.py")
# result = {"endpoints": [...], "count": N}
```

### Step 5: Trace Provenance with GatedGarden

```python
# Entity types: 0=GitFarmCommit, 1=BrazilPackageVersionPlatform, 2=BrazilVersionSet,
#               3=BrazilVersionSetRevision, 4=ApolloEnvironmentNameAndStage, 5=Pipeline, 6=PipelineExecution, 7=PipelineStage
entity_types = gated_garden.list_entity_types()
# Blast radius — what consumes this package?
blast = gated_garden.query_active_places(entity_type=1, identifier="MyPackage-1.0/AL2_x86_64")
# Full dependency tree
tree = gated_garden.get_expanded_document(entity_type=1, identifier="MyPackage-1.0/AL2_x86_64")
# W3C PROV lineage chain (commit → build → version set → deployment)
prov = gated_garden.get_prov_document(entity_type=1, identifier="MyPackage-1.0/AL2_x86_64")
# Analytics SQL for fleet-wide trends (weekly snapshots)
trend = gated_garden.analytics_query("SELECT COUNT(*) FROM entities WHERE entity_type = 'BrazilPackageVersionPlatform'")
```

### Step 6: Enforce Access Control and Audit

```python
auth_backend.add_user("sec-ops-1", "security-analyst", email="analyst@example.com", scopes=["scan", "review"])
token, _ = auth_backend.create_token("sec-ops-1")

from factory.permissions.runtime.envelope import Envelope
result = permissions.evaluate(action="scan", resource={"type": "codebase", "id": "main-repo"}, envelope=Envelope())
# Returns: {"decision": "allow", ...}

# Deny deploy without scan
result = permissions.evaluate(action="deploy", resource={"type": "artifact", "id": "build-123"}, context={"scanned": False}, envelope=Envelope())
# Returns: {"decision": "deny", ...}

logger.info(f"Security scan completed: {analysis.analysis_id}", source="security-ops",
    context={"target": analysis.target, "findings_count": len(analysis.findings)})
logs = logger.tail(n=5)
```

## Typed FastMCP Contract

Security’s canonical FastMCP surface contains 31 tools: 11 deterministic, 14 operational, and 6 authoring. Each tool accepts flat, strict same-brick Pydantic v2 input fields and returns `ToolResult[OutputDTO]`; consume successful payloads from `result.data`, not from the envelope itself. The six authoring tools are always discoverable. With authoring disabled, `security.authoring.get_status` returns `data.enabled=False`; mutations raise the authoring-disabled error.

`security.threat_model` preserves its two successful payload shapes inside `result.data`: `{\"target\", \"analysis\"}` when an LLM adapter is available, or `{\"error\": \"LLM adapter not configured — compose llm_gateway brick\"}` when it is not. Pentest tools likewise keep their legacy fields at `result.data` top level (for example `job_id`, `status`, `findings`, and `exit_code`); invalid scan types are successful envelopes whose `data` contains `error` and `valid` scan types.

## Success Criteria

- [x] Veritas returns resource topology and security posture
- [x] SIPP discovers databases/tables and executes queries
- [x] Security analysis runs and returns findings
- [x] GatedGarden traces provenance and blast radius
- [x] Permission check allows scan, denies deploy without scan
- [x] All security events logged with context and audit trail retrievable

## Pentest Workflow

Automated penetration testing using the 5 pentest MCP tools. The `SandboxPentestAdapter` provisions Docker containers via the sandbox brick and runs nmap, nuclei, gobuster, sqlmap, and curl inside them. Findings auto-persist to the graph with CWE classification.

### Step 7: Run a Pentest Scan

```python
# Via the typed MCP tool boundary. ToolResult is the envelope; payload is .data.
launch = await security_pentest_scan(scan_type="port_scan", target="host.docker.internal:5050")
assert launch.ok
job = launch.data
# job.job_id, job.status, job.scan_type, and job.target retain their legacy names.

# Check status (useful for long-running scans)
status_result = await security_pentest_status(job_id=job.job_id)
assert status_result.ok

# Fetch results
results_result = await security_pentest_results(job_id=job.job_id)
assert results_result.ok
results = results_result.data
# results.findings, results.duration_ms, and results.exit_code are payload fields.
```

### Step 8: Full Pentest Assessment (Multi-Scan)

```python
# 1. Recon — discover open ports and services
recon = await security_pentest_scan(scan_type="port_scan", target="10.0.0.1")

# 2. HTTP probe — check discovered web services
probe = await security_pentest_scan(scan_type="http_probe", target="http://10.0.0.1:8080")

# 3. Vulnerability scan — run nuclei templates
vuln = await security_pentest_scan(scan_type="vuln_scan", target="http://10.0.0.1:8080")

# 4. SQL injection — test suspicious endpoints
sqli = await security_pentest_scan(
    scan_type="sql_inject", target="http://10.0.0.1:8080/api/search?q=test")

# 5. Web fuzzing — enumerate directories
fuzz = await security_pentest_scan(scan_type="web_fuzz", target="http://10.0.0.1:8080")

# 6. List all jobs and collect results
jobs_result = await security_pentest_list_jobs()
assert jobs_result.ok
for job in jobs_result.data.jobs:
    result = await security_pentest_results(job_id=job["job_id"])
    assert result.ok
    print(f"{job['scan_type']}: {len(result.data.findings)} findings")
```

### Step 9: Cancel a Running Scan

```python
cancel_result = await security_pentest_cancel(job_id="pentest-a1b2c3d4")
assert cancel_result.ok
# cancel_result.data.job_id == "pentest-a1b2c3d4"
# cancel_result.data.cancelled is True
```

### Step 10: Use the Pentest Swarm (4-Agent Pipeline)

The `pentest-assessment` swarm preset automates the full workflow with 4 agents:
- `recon-agent` — port scan + HTTP probe, hands off to vuln-scanner
- `vuln-scanner` — nuclei vulnerability scan, hands off to exploit-tester
- `exploit-tester` — sql_inject + web_fuzz on confirmed vulns, hands off to report-writer
- `report-writer` — collects all results, stores learnings in memory, writes structured report

```python
from factory.agent.interface import create_runtime
agent_rt = create_runtime()
result = await agent_rt.reason(
    prompt="Run a pentest assessment against host.docker.internal:5050",
    hint="swarm:pentest-assessment",
)
```

### Pentest Scan Types

| Scan Type | Tool | Description |
|-----------|------|-------------|
| `port_scan` | nmap | TCP/UDP port scan with service detection |
| `vuln_scan` | nuclei | Vulnerability scan with nuclei templates |
| `web_fuzz` | gobuster | Web directory/file enumeration |
| `sql_inject` | sqlmap | SQL injection detection |
| `http_probe` | curl | HTTP endpoint probing |
| `nuclei_scan` | nuclei | Nuclei scan with custom templates (pass `options.templates`) |

### Pentest Resource & Prompts

| Type | URI / Name | Description |
|------|-----------|-------------|
| Resource | `security://schemas/pentest-tools` | Available scan types, tools, and example invocations |
| Prompt | `run_pentest_assessment` | Guide an agent through a full pentest assessment (5-step) |
| Prompt | `analyze_scan_results` | Guide an agent to interpret results and classify findings |

## LocalStack AWS Pentest Workflow

End-to-end AWS security testing using LocalStack emulation. The `localstack` sandbox adapter provisions a LocalStack container + awscli sidecar via docker compose. Agents run real AWS CLI commands against emulated services with `ENFORCE_IAM=1`.

### Prerequisites

- Docker + docker compose
- `SANDBOX_ADAPTER=localstack` (env var or config)
- Challenge templates in `projects/companion_x/challenges/localstack-iam-privesc/` and `projects/companion_x/challenges/localstack-ssrf-lambda/`

### Step 11: Provision LocalStack Environment

```python
# Via MCP tools (agent workflow)
env = await sandbox_provision(config={"adapter": "localstack"})
# env = {"env_id": "localstack-a1b2c3d4"}
# Starts: LocalStack (IAM, Lambda, S3, DynamoDB, SQS, SNS, API GW, CFN, STS, SSM)
#         + awscli sidecar with challenge volumes mounted
```

### Step 12: Deploy a Challenge Template (IAM Privesc)

```python
# Deploy the intentionally vulnerable IAM config
result = await sandbox_execute(
    env_id=env["env_id"],
    command="aws cloudformation deploy --template-file /challenges/iam-privesc/template.yaml --stack-name iam-privesc --capabilities CAPABILITY_NAMED_IAM"
)
# Creates: vulnerable-lambda-role (iam:*, s3:*, lambda:*, dynamodb:*), public-data-bucket
```

### Step 12b: Apply Service Mocks (Post-CFN)

After deploying a CFN stack, configure auth service mocks discovered by recon agents:

```python
# Apply auth mocks for services the target app depends on
await sandbox_apply_service_mocks(
    env_id=env["env_id"],
    config={
        "aaa": {"enabled": True, "service_name": "my-service", "bypass_mode": "authorize_all"},
        "odin": {"enabled": True, "material_sets": {"default": {"aws_account_id": "000000000000"}}},
        "cloudauth": {"enabled": True, "bypass_mode": "mock_server"},
        "coral": {"enabled": False},
        "turtle": {"enabled": False},
    },
)
# Configures LocalStack to mock AAA, Odin, CloudAuth so the deployed app
# can authenticate without real Amazon internal services.
```

### Step 13: Deploy a Challenge Template (SSRF Lambda)

```python
result = await sandbox_execute(
    env_id=env["env_id"],
    command="aws cloudformation deploy --template-file /challenges/ssrf-lambda/template.yaml --stack-name ssrf-lambda --capabilities CAPABILITY_NAMED_IAM"
)
# Creates: ssrf-vulnerable-function (fetches any URL), /app/db-password SSM param
```

### Step 14: Run AWS Recon Commands

```python
# Enumerate IAM roles
roles = await sandbox_execute(
    env_id=env["env_id"],
    command="aws iam list-roles --query 'Roles[].RoleName'"
)
# Enumerate S3 buckets
buckets = await sandbox_execute(
    env_id=env["env_id"],
    command="aws s3 ls"
)
# Enumerate Lambda functions
lambdas = await sandbox_execute(
    env_id=env["env_id"],
    command="aws lambda list-functions --query 'Functions[].FunctionName'"
)
```

### Step 15: Audit IAM Policies

```python
# Get role policies
policies = await sandbox_execute(
    env_id=env["env_id"],
    command="aws iam list-role-policies --role-name vulnerable-lambda-role"
)
# Get policy document — flag Action: *, Resource: *
doc = await sandbox_execute(
    env_id=env["env_id"],
    command="aws iam get-role-policy --role-name vulnerable-lambda-role --policy-name overly-permissive-policy"
)
```

### Step 16: Exploit and Validate Findings

```python
# Attempt privilege escalation via role assumption
assume = await sandbox_execute(
    env_id=env["env_id"],
    command="aws sts assume-role --role-arn arn:aws:iam::000000000000:role/vulnerable-lambda-role --role-session-name test"
)
# Test SSRF — invoke Lambda with internal URL
ssrf = await sandbox_execute(
    env_id=env["env_id"],
    command='aws lambda invoke --function-name ssrf-vulnerable-function --payload \'{"url":"http://localhost:4566/_localstack/health"}\' /dev/stdout'
)
# Read plaintext secret via SSM
secret = await sandbox_execute(
    env_id=env["env_id"],
    command="aws ssm get-parameter --name /app/db-password --query 'Parameter.Value' --output text"
)
```

### Step 17: Use the AWS Pentest Swarm (4-Agent Pipeline)

The `aws-pentest` swarm preset (`defaults_aws_pentest.py`) automates the full workflow:
- `aws-recon` — enumerates IAM roles, S3 buckets, Lambda functions
- `iam-auditor` — checks role policies, flags overly permissive configs
- `exploit-tester` — attempts role assumption, reads public S3 objects
- `report-writer` — stores learnings in memory, writes structured report

```python
from factory.agent.interface import create_runtime
agent_rt = create_runtime()
result = await agent_rt.reason(
    prompt="Run an AWS pentest against the LocalStack environment",
    hint="swarm:aws-pentest",
)
```

### Challenge Templates

| Challenge | Path | Vulnerabilities | CWEs |
|-----------|------|----------------|------|
| IAM Privesc | `projects/companion_x/challenges/localstack-iam-privesc/` | Overly permissive IAM role (iam:*/s3:*/lambda:*/dynamodb:* on *), public S3 bucket | CWE-269, CWE-284 |
| SSRF Lambda | `projects/companion_x/challenges/localstack-ssrf-lambda/` | SSRF via user-supplied URL in Lambda, plaintext SSM secret | CWE-918, CWE-312 |

Each challenge includes `template.yaml` (CloudFormation) and `gt_entries.json` (ground truth for eval pipelines).

### Step 18: Tear Down

```python
await sandbox_terminate(env_id=env["env_id"])
# Runs: docker compose down -v (removes containers + volumes)
```

## API Reference

| Brick | Import | Key Methods |
|-------|--------|-------------|
| security | `factory.security.runtime.runtime.SecurityRuntime` | `analyze()`, `threat_model()`, `health_check()` |
| security (endpoints) | `factory.security.runtime.endpoint_scanner.scan_endpoints` | `scan_endpoints(source_code, framework, file_path)` |
| security (confidence) | `factory.security.runtime.confidence.classify` | `classify(agent_consensus, total_agents, has_taint_trace, has_mitigating_control, has_code_evidence, is_sensitive_operation, historical_tp_rate, confidence_score)` → `{confidence_level, confidence_score, reason, level_index}` |
| security (taint) | `factory.security.runtime.taint_tracer.trace` | `trace(source_code, endpoint, param, taint_sinks, taint_sources, file_path)` → `{endpoint, param, file, hops[], hop_count, sink_reached, auth_gap, auth_checks[]}` |
| security (pentest) | `factory.security.runtime.pentest.PentestRuntime` | `scan()`, `get_status()`, `get_results()`, `cancel()`, `list_jobs()`, `cleanup()` |
| sandbox (localstack) | `factory.sandbox.runtime.adapters.localstack_adapter.LocalStackAdapter` | `provision()`, `execute()`, `terminate()`, `get_status()`, `upload_file()`, `download_file()`, `list_files()` |
| sandbox (mocks) | `factory.sandbox.runtime.models.ServiceMockConfig` | `apply_service_mocks()` — configures AAA, Odin, CloudAuth, Coral, Turtle mocks |
| agent (aws-pentest) | `factory.agent.registry.defaults_aws_pentest.AWS_PENTEST_SWARM` | 4-agent swarm config (aws-recon, iam-auditor, exploit-tester, report-writer) |
| veritas | `factory.veritas.runtime.runtime.VeritasRuntime` | `query()`, `get_app_topology()`, `search_resources()`, `get_security_posture()`, `get_resource_permissions()`, `get_deployment_chain()`, `get_data_flows()`, `get_app_security_profile()` |
| sipp | `factory.sipp.runtime.runtime.SIPPRuntime` | `list_databases()`, `list_tables()`, `get_schema()`, `submit_query()`, `get_query_status()`, `get_query_preview()` |
| gated_garden | `factory.gated_garden.runtime.runtime.GatedGardenRuntime` | `list_entity_types()`, `query_active_places()`, `get_expanded_document()`, `get_prov_document()`, `analytics_query()` |
| permissions | `factory.permissions.runtime.runtime.PermissionsRuntime` | `evaluate()`, `explain()`, `batch_evaluate()` |
| logger | `factory.logger.runtime.runtime.LoggerRuntime` | `log()`, `info()`, `tail()`, `search()` |

## MCP Tools

| Tool | Brick | Description |
|------|-------|-------------|
| `security.analyze` | security | Run security analysis on a target |
| `security.scan_endpoints` | security | Deterministic regex-based HTTP endpoint scanner — discovers routes across spring_mvc, jax_rs, flask, express, django. Returns structured inventory (method, path, file, line, params, framework). No LLM needed. |
| `security.classify_confidence` | security | Deterministic 5-level confidence classification (Strong_Safe → Confirmed). Inputs: agent_consensus, total_agents, has_taint_trace, has_mitigating_control, has_code_evidence, is_sensitive_operation, historical_tp_rate, confidence_score. Returns: confidence_level, confidence_score, reason, level_index. No LLM needed. |
| `security.trace_taint` | security | Deterministic interprocedural taint tracer — regex-based, no LLM. Follows data from user-controlled source to sink across method boundaries, checking for auth controls at each hop. Polymorphic via `taint_sinks` arg (populated from `vuln_class_config`). Inputs: source_code, param, taint_sinks (JSON array), taint_sources (JSON array), endpoint, file_path. Returns: {endpoint, param, file, hops[], hop_count, sink_reached, auth_gap, auth_checks[]}. SAST Phase 3 calls this deterministically before LLM reasoning. |
| `security.threat_model` | security | Generate threat model using LLM |
| `query_veritas` | veritas | Execute Cypher against the 6B+ node graph |
| `get_app_topology` | veritas | App resources, pipelines, environments |
| `search_resources` | veritas | Search by type, owner, name, account |
| `get_security_posture` | veritas | Cert status, color, ring, reviews |
| `get_resource_permissions` | veritas | IAM/access relationships for a resource |
| `get_deployment_chain` | veritas | Pipeline stages and deployment targets |
| `get_data_flows` | veritas | Trace inbound/outbound data flows |
| `sipp_list_databases` | sipp | List available SIPP databases |
| `sipp_list_tables` | sipp | List tables in a database |
| `sipp_get_table_schema` | sipp | Column definitions for a table |
| `sipp_run_query` | sipp | Execute Spark SQL (SELECT only, auto-limited) |
| `gated_garden_query_active_places` | gated_garden | Blast radius: find all consumers of an entity |
| `gated_garden_get_expanded_document` | gated_garden | Full dependency tree for an entity |
| `gated_garden_get_prov_document` | gated_garden | W3C PROV lineage chain |
| `gated_garden_analytics_query` | gated_garden | SQL against weekly analytics snapshots |
| `security_pentest_scan` | security | Launch a pentest scan (port_scan, vuln_scan, web_fuzz, sql_inject, http_probe, nuclei_scan) |
| `security_pentest_status` | security | Check status of a pentest scan job |
| `security_pentest_results` | security | Fetch results of a completed scan (raw_output, findings, duration, exit_code) |
| `security_pentest_cancel` | security | Cancel a running pentest scan |
| `security_pentest_list_jobs` | security | List all pentest scan jobs in the current session |
| `sandbox.provision` | sandbox | Provision a sandbox environment (docker, localstack, ec2, ssm) |
| `sandbox.execute` | sandbox | Execute a command in a provisioned sandbox |
| `sandbox.terminate` | sandbox | Tear down a sandbox environment |
| `sandbox.get_status` | sandbox | Get sandbox environment health/status |
| `sandbox.upload_file` | sandbox | Upload a file into the sandbox |
| `sandbox.download_file` | sandbox | Download a file from the sandbox |
| `sandbox.list_files` | sandbox | List files in a sandbox directory |
| `sandbox.apply_service_mocks` | sandbox | Configure auth mocks (AAA, Odin, CloudAuth, Coral, Turtle) in a sandbox environment via `ServiceMockConfig` — call after CFN deployment |
| `sandbox.generate_cfn_from_recon` | sandbox | Generate golden-default CFN templates from Veritas `search_resources` output (13 resource types: DynamoDB, SQS, S3, IamRole, Lambda, SNS, ECSCluster, ApiGateway, ApiGatewayMethod, KMS, Secret, SSMParameter) for LocalStack deployment when no CDK package exists |
| `sandbox.workspace_dir` | sandbox | Return scoped temp directory (`/tmp/factory-sandbox/{env_id}/artifacts/`) for artifact staging during recon — created on provision, cleaned on terminate |
