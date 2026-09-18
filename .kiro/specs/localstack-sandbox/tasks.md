# Tasks: LocalStack Sandbox Adapter

## Task 1: LocalStackAdapter
- [ ] Create `components/sandbox/src/factory/sandbox/runtime/adapters/localstack_adapter.py`
- [ ] Implement `provision()` — `docker compose up -d`, wait for healthcheck
- [ ] Implement `execute()` — `docker compose exec awscli sh -c "{command}"`
- [ ] Implement `terminate()` — `docker compose down -v`
- [ ] Implement `get_status()` — curl LocalStack health endpoint
- [ ] Implement `list_files()`, `upload_file()`, `download_file()` via docker cp
- [ ] Add `localstack` case to `runtime.py:create_adapter()`
- [ ] Update sandbox `BRICK.yaml` with `localstack` adapter

## Task 2: Docker Compose Configuration
- [ ] Create `challenges/localstack/docker-compose.yml` (localstack + awscli sidecar)
- [ ] Configure `ENFORCE_IAM=1`, services list, healthcheck
- [ ] Mount challenge template directories into awscli container
- [ ] Create `challenges/localstack/README.md`

## Task 3: IAM Privilege Escalation Challenge
- [ ] Create `challenges/localstack-iam-privesc/template.yaml`
  - Lambda with overly permissive IAM role (iam:*, s3:*, lambda:*)
  - S3 bucket with public-read policy
  - API Gateway with no authorizer
  - DynamoDB table with no encryption
- [ ] Create `challenges/localstack-iam-privesc/gt_entries.json` (4 GT entries)
- [ ] Verify template deploys successfully into LocalStack

## Task 4: SSRF Lambda Challenge
- [ ] Create `challenges/localstack-ssrf-lambda/template.yaml`
  - Lambda function that fetches user-supplied URL
  - IAM role with ssm:GetParameter access
  - SSM parameter at /app/db-password with a secret value
- [ ] Create `challenges/localstack-ssrf-lambda/handler.py` (vulnerable Lambda code)
- [ ] Create `challenges/localstack-ssrf-lambda/gt_entries.json` (2 GT entries)
- [ ] Verify template deploys and Lambda is invocable

## Task 5: Deploy Script
- [ ] Create `challenges/localstack/deploy_challenges.sh`
- [ ] Script deploys all challenge templates into running LocalStack
- [ ] Script verifies each stack deployed successfully
- [ ] Script is idempotent (re-running doesn't fail)

## Task 6: AWS Pentest Swarm Preset
- [ ] Add `aws-pentest` swarm to `defaults_pentest.py`
  - aws-recon: enumerates IAM, S3, Lambda, API GW via AWS CLI
  - iam-auditor: checks policies for overly permissive permissions
  - exploit-tester: attempts assume-role, public S3, unauth API calls
  - report-writer: aggregates findings, stores learnings
- [ ] Each agent uses sandbox.execute to run AWS CLI commands
- [ ] Register in defaults.py

## Task 7: E2E Test — IAM Privilege Escalation
- [ ] Provision LocalStack sandbox
- [ ] Deploy iam-privesc challenge template
- [ ] Verify Lambda function exists (aws lambda list-functions)
- [ ] Verify S3 bucket has public-read policy
- [ ] Verify API Gateway has no authorizer
- [ ] Verify agent can assume-role and escalate
- [ ] Verify Finding nodes in graph with CWE-269, CWE-284, CWE-306
- [ ] Verify ToolInvocation telemetry nodes created

## Task 8: E2E Test — SSRF Lambda
- [ ] Deploy ssrf-lambda challenge template
- [ ] Invoke Lambda with crafted SSRF URL
- [ ] Verify secret extracted from SSM
- [ ] Verify Finding node with CWE-918

## Task 9: E2E Test — Full Pentest Swarm
- [ ] Provision LocalStack, deploy all challenges
- [ ] Launch aws-pentest swarm via agent_launch_swarm
- [ ] Verify recon-agent discovers services
- [ ] Verify iam-auditor identifies misconfigs
- [ ] Verify findings persisted to graph
- [ ] Verify metrics recorded
- [ ] Verify memory stores learnings
- [ ] Verify regression gate (baseline → compare → BLOCK/WARN/PASS)
- [ ] All verification via CompX MCP tools

## Task 10: Guardian + Docs
- [ ] Update sandbox BRICK.yaml with localstack adapter
- [ ] Run foreman_guardian_check — must pass 5/5
- [ ] Update brick-inventory.md with LocalStack adapter
- [ ] Update security-ops recipe with LocalStack workflow
