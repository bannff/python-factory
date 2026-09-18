# Requirements: LocalStack Sandbox Adapter

## Introduction

Add a `LocalStackAdapter` to the sandbox brick that spins up a LocalStack container providing real AWS API surfaces (IAM, Lambda, API Gateway, S3, DynamoDB, SQS, SNS, CloudFormation, STS) on `localhost:4566`. Security agents can then pentest realistic AWS environments locally — testing IAM misconfigs, Lambda privilege escalation, S3 bucket policy bypasses, API Gateway auth issues — without touching real AWS or spending money.

### Problem

The current sandbox is a plain Ubuntu Docker container. Agents can run curl and nmap inside it, but the target is always a simple Flask app. Real security work at Amazon involves AWS services — Lambda functions with overly permissive IAM roles, S3 buckets with public policies, API Gateways without auth. The sandbox doesn't model any of this.

### What This IS

- A new `LocalStackAdapter` in the sandbox brick implementing the existing `SandboxPort` protocol
- LocalStack container started via `docker compose` with `ENFORCE_IAM=1` for realistic IAM enforcement
- Vulnerable CloudFormation templates as "challenge apps" (like idor-warehouse but for AWS)
- AWS CLI available inside the sandbox for agents to interact with LocalStack services
- Integration with existing pentest tools — agents use `security_pentest_scan` against LocalStack endpoints

### What This is NOT

- A replacement for the Docker adapter (it's an additional adapter, selected via env var)
- A real AWS environment (it's emulated — some edge cases won't match production)
- A Personal Stacks integration (that's a future phase)

### Architecture

```
Strands Agent (pentest swarm)
    │ call_mcp_tool("sandbox.provision", options={"adapter": "localstack"})
    ▼
Sandbox Brick MCP
    │ SANDBOX_ADAPTER=localstack
    ▼
LocalStackAdapter
    │ docker compose up (localstack + awscli sidecar)
    ▼
┌─────────────────────────────────────────┐
│ LocalStack Container (localhost:4566)    │
│  IAM  │ Lambda │ S3 │ DynamoDB │ STS   │
│  API GW │ SQS │ SNS │ CloudFormation   │
│  ENFORCE_IAM=1 (realistic IAM)          │
└─────────────────────────────────────────┘
    │
    ▼ sandbox.execute("aws --endpoint-url=http://localhost:4566 ...")
    │
Agent runs AWS CLI commands against emulated services
```

## Requirements

### Requirement 1: LocalStackAdapter (SandboxPort Implementation)

**User Story:** As a security engineer, I want to provision a LocalStack environment through the same sandbox MCP tools I already use, so my agents can pentest AWS services locally.

#### Acceptance Criteria

1. `runtime/adapters/localstack_adapter.py` SHALL implement `SandboxPort` (same protocol as DockerAdapter).
2. `provision()` SHALL start a LocalStack container via `docker compose` with services: iam, lambda, s3, dynamodb, sqs, sns, apigateway, cloudformation, sts.
3. `provision()` SHALL set `ENFORCE_IAM=1` so IAM policies are actually enforced.
4. `execute()` SHALL run commands inside an "awscli sidecar" container that has AWS CLI pre-installed and `AWS_ENDPOINT_URL=http://localstack:4566` pre-configured.
5. `terminate()` SHALL `docker compose down` the entire stack.
6. `get_status()` SHALL check LocalStack's `/_localstack/health` endpoint.
7. The adapter SHALL be selected via `SANDBOX_ADAPTER=localstack` env var.
8. The adapter SHALL reuse a running LocalStack instance if one is already up (idempotent provision).

### Requirement 2: Challenge Templates (Vulnerable CloudFormation)

**User Story:** As a security engineer, I want pre-built vulnerable AWS environments that I can deploy into LocalStack, so my agents have realistic targets to pentest.

#### Acceptance Criteria

1. `challenges/localstack-iam-privesc/template.yaml` — CloudFormation template with:
   - A Lambda function with an overly permissive IAM role (iam:*, s3:*)
   - An S3 bucket with a public-read policy
   - An API Gateway endpoint with no auth
   - A DynamoDB table with no encryption
2. `challenges/localstack-ssrf-lambda/template.yaml` — CloudFormation template with:
   - A Lambda function that fetches a URL from user input (SSRF)
   - An IAM role with access to secrets in SSM Parameter Store
   - A secret stored in SSM at `/app/db-password`
3. Each template SHALL include a `gt_entries.json` with ground truth findings (same schema as idor-warehouse).
4. Each template SHALL be deployable via: `aws cloudformation deploy --template-file template.yaml --stack-name <name> --endpoint-url http://localhost:4566`
5. A `deploy_challenges.sh` script SHALL deploy all templates into a running LocalStack instance.

### Requirement 3: Docker Compose Configuration

**User Story:** As a developer, I want a single `docker-compose.yml` that starts LocalStack + an AWS CLI sidecar container, so provisioning is one command.

#### Acceptance Criteria

1. `challenges/localstack/docker-compose.yml` SHALL define two services:
   - `localstack`: `localstack/localstack:latest` with `ENFORCE_IAM=1`, ports 4566 exposed
   - `awscli`: Ubuntu container with AWS CLI v2, `AWS_ENDPOINT_URL=http://localstack:4566`, `AWS_DEFAULT_REGION=us-east-1`, `AWS_ACCESS_KEY_ID=test`, `AWS_SECRET_ACCESS_KEY=test`
2. The awscli container SHALL have `sleep infinity` as entrypoint (sandbox.execute runs commands in it).
3. The compose file SHALL include a healthcheck on LocalStack's `/_localstack/health` endpoint.
4. The compose file SHALL mount `challenges/localstack-*/` templates into the awscli container at `/challenges/`.

### Requirement 4: Pentest Tool Integration

**User Story:** As a Strands agent, I want to use the existing `security_pentest_scan` tools against LocalStack endpoints, so the same pentest workflow works for both simple apps and AWS environments.

#### Acceptance Criteria

1. `security_pentest_scan(scan_type="port_scan", target="localstack")` SHALL discover LocalStack's port 4566.
2. `security_pentest_scan(scan_type="http_probe", target="http://localstack:4566/_localstack/health")` SHALL return 200.
3. Agents SHALL be able to run AWS CLI commands via `sandbox.execute(env_id, "aws s3 ls --endpoint-url http://localstack:4566")`.
4. The pentest swarm's recon-agent SHALL enumerate LocalStack services via the health endpoint.

### Requirement 5: E2E Test — IAM Privilege Escalation

**User Story:** As a QA engineer, I want an E2E test that deploys the IAM privesc challenge into LocalStack and verifies an agent can discover and exploit the misconfiguration.

#### Acceptance Criteria

1. Test SHALL provision a LocalStack sandbox via `sandbox.provision`.
2. Test SHALL deploy `localstack-iam-privesc/template.yaml` via `sandbox.execute`.
3. Test SHALL verify the Lambda function exists: `aws lambda list-functions`.
4. Test SHALL verify the S3 bucket has public-read policy: `aws s3api get-bucket-policy`.
5. Test SHALL verify the API Gateway has no authorizer: `aws apigateway get-rest-apis`.
6. Test SHALL verify an agent can assume the Lambda's role and escalate to admin: `aws sts assume-role`.
7. Test SHALL verify findings are created in the graph with CWE-269 (Improper Privilege Management).
8. Test SHALL verify telemetry ToolInvocation nodes are created for each sandbox.execute call.

### Requirement 6: E2E Test — SSRF Lambda Exploitation

**User Story:** As a QA engineer, I want an E2E test that deploys the SSRF Lambda challenge and verifies an agent can discover the SSRF and extract the secret.

#### Acceptance Criteria

1. Test SHALL deploy `localstack-ssrf-lambda/template.yaml`.
2. Test SHALL invoke the Lambda with a crafted URL pointing to the SSM parameter.
3. Test SHALL verify the secret `/app/db-password` is extractable via the SSRF.
4. Test SHALL verify a Finding node is created with CWE-918 (Server-Side Request Forgery).

### Requirement 7: E2E Test — Full Pentest Swarm Against LocalStack

**User Story:** As a security engineer, I want to launch the `pentest-assessment` swarm against a LocalStack environment and verify the full pipeline works end-to-end.

#### Acceptance Criteria

1. Test SHALL provision LocalStack, deploy all challenge templates.
2. Test SHALL launch `pentest-assessment` swarm via `agent_launch_swarm` with target `http://localstack:4566`.
3. Test SHALL verify the swarm's recon-agent discovers LocalStack services.
4. Test SHALL verify the vuln-scanner identifies IAM misconfigs and public S3 buckets.
5. Test SHALL verify findings are persisted to graph with CWE classification.
6. Test SHALL verify metrics are recorded: `metrics_record(metric_id="pentest-findings", value=<count>)`.
7. Test SHALL verify memory stores learnings: `memory_memory_store(content="...", user_id="kiro-agent")`.
8. Test SHALL verify the regression gate works: set baseline, re-run, compare.
9. ALL verification SHALL use CompX MCP tools (graph_query, metrics_*, memory_*).

### Requirement 8: Pentest Swarm Preset for AWS Targets

**User Story:** As a security engineer, I want a swarm preset specifically designed for AWS environment pentesting (not just web apps).

#### Acceptance Criteria

1. `defaults_pentest.py` SHALL add an `aws-pentest` swarm with 4 agents:
   - `aws-recon`: enumerates IAM users/roles, S3 buckets, Lambda functions, API Gateways via AWS CLI
   - `iam-auditor`: checks IAM policies for overly permissive permissions, role chaining, privilege escalation paths
   - `exploit-tester`: attempts exploitation (assume-role, public S3 access, unauthenticated API calls)
   - `report-writer`: aggregates findings, maps to CWE, stores learnings
2. Each agent SHALL use `call_mcp_tool("sandbox.execute", ...)` to run AWS CLI commands.
3. The swarm SHALL accept `target_endpoint` in context (defaults to `http://localstack:4566`).

### Requirement 9: Factory Tenets

#### Acceptance Criteria

1. ALL files SHALL be under 200 LOC.
2. NO cross-brick imports — LocalStack access via sandbox brick MCP only.
3. Business logic in `runtime/`, MCP surface in `mcp/`.
4. `BRICK.yaml` updated with `localstack` adapter.
5. Guardian check SHALL pass 5/5.
6. Hypothesis property tests for any new parsers or data models.
