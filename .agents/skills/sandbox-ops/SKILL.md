---
name: sandbox-ops
description: Provisions, configures, and operates LocalStack sandbox environments for red team exercises. Use for AWS sandbox testing, CLI commands, and CloudFormation deploys.
---

# Sandbox Ops Skill

Teaches agents to provision, configure, and operate LocalStack sandbox environments for red team exercises.

## AWS CLI Prefix

Every AWS CLI command in the sandbox MUST use this prefix:

```bash
AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test aws --endpoint-url=http://localhost:4566
```

When using `sandbox.execute`, the prefix is applied automatically by the sidecar. Just pass the `aws ...` command.

## Sandbox MCP Tools

| Tool | Purpose |
|------|---------|
| `sandbox.provision` | Create a new sandbox environment (supports `profile` param for builtin targets) |
| `sandbox.list_profiles` | List available target profiles with image, ports, health_check_url |
| `sandbox.execute` | Run a command in the sandbox |
| `sandbox.list_environments` | List all sandbox environments |
| `sandbox.get_status` | Check environment status |
| `sandbox.terminate` | Destroy an environment |
| `sandbox.deploy_cfn` | Deploy a CloudFormation stack |
| `sandbox.list_stacks` | List CFN stacks |
| `sandbox.describe_stack` | Get stack status, outputs, resources |
| `sandbox.delete_stack` | Remove a CFN stack |
| `sandbox.translate_cfn` | Filter CFN template for LocalStack compatibility |
| `sandbox.generate_cfn_from_recon` | Build CFN from Veritas search_resources output |
| `sandbox.apply_service_mocks` | Configure AAA/Odin/CloudAuth/Coral/Turtle mocks |
| `sandbox.workspace_dir` | Get artifact staging directory |

## Profile-Based Provisioning

Sandbox ships 5 builtin target profiles for common vulnerable apps. Use
`sandbox.list_profiles()` to discover them, then pass a profile name to
`sandbox.provision()` to spin up a ready-to-attack container in one call.

### Available Profiles

| Profile | Image | Ports | Health Check |
|---------|-------|-------|-------------|
| `webgoat` | `webgoat/webgoat:latest` | 8080, 9090 | `/WebGoat` |
| `dvwa` | `vulnerables/web-dvwa:latest` | 8080→80 | `/login.php` |
| `vampi` | `erev0s/vampi:latest` | 5050→5000 | `/` |
| `juice_shop` | `bkimminich/juice-shop:latest` | 3000 | `/` |
| `idor_warehouse` | `python:3.11-slim` | 5050→5000 | `/health` |

### Usage

```python
# 1. List available profiles (deterministic — no side effects)
sandbox.list_profiles()
# Returns: {"profiles": {"webgoat": {"image": ..., "ports": ..., "health_check_url": ...}, ...}}

# 2. Provision a target by profile name
#    Auto-terminates any existing sandbox, then starts the profile's container
sandbox.provision(profile="webgoat")
# Returns: {"success": true, "environment": {...}, "profile": "webgoat"}

# 3. Run commands against the provisioned target
sandbox.execute(env_id="<env_id>", command="curl -s http://localhost:8080/WebGoat")
```

When `profile` is set, `instance_type` and `ami_id` are ignored — the profile's
Docker image, ports, and entrypoint are used instead. Only one sandbox runs at a
time; provisioning a new profile auto-terminates the previous one.

The `idor_warehouse` profile starts a bare `python:3.11-slim` container with
`sleep infinity` — upload your app code and install deps via `sandbox.execute`.

## Direct Resource Creation (No CFN Needed)

For quick setup, create resources directly via CLI through `sandbox.execute`.

### DynamoDB

```bash
aws dynamodb create-table \
  --table-name OrdersTable \
  --attribute-definitions AttributeName=pk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

With sort key:
```bash
aws dynamodb create-table \
  --table-name EventsTable \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

### SQS

```bash
aws sqs create-queue --queue-name my-queue
aws sqs create-queue --queue-name my-dlq
```

### S3

```bash
aws s3 mb s3://my-data-bucket
aws s3 mb s3://my-config-bucket
```

### IAM Role

```bash
aws iam create-role \
  --role-name MyServiceRole \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
```

Attach an overpermissive policy (for pentest scenarios):
```bash
aws iam put-role-policy \
  --role-name MyServiceRole \
  --policy-name AdminAccess \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
```

### Lambda

```bash
aws lambda create-function \
  --function-name MyFunction \
  --runtime python3.11 \
  --handler index.handler \
  --role arn:aws:iam::000000000000:role/MyServiceRole \
  --zip-file fileb://function.zip
```

## Verification Commands

Run these after creating resources to confirm they exist:

```bash
aws dynamodb list-tables
aws sqs list-queues
aws s3 ls
aws iam list-roles
aws iam list-role-policies --role-name MyServiceRole
aws iam get-role-policy --role-name MyServiceRole --policy-name AdminAccess
aws lambda list-functions
aws dynamodb describe-table --table-name OrdersTable
aws s3api get-bucket-acl --bucket my-data-bucket
```

## CFN Deployment Path

When you have a CFN template (from CDK analysis or `sandbox.generate_cfn_from_recon`):

```python
# 1. Deploy the stack
sandbox.deploy_cfn(
    env_id="companion_x-localstack-1",
    stack_name="target-app-stack",
    template_body="<YAML or JSON string>",
    capabilities=["CAPABILITY_NAMED_IAM"])

# 2. Verify deployment
sandbox.describe_stack(env_id="companion_x-localstack-1", stack_name="target-app-stack")
sandbox.list_stacks(env_id="companion_x-localstack-1")
```

### Translating CDK output for LocalStack

```python
# Filter a full CDK-synth template to LocalStack-supported resources
sandbox.translate_cfn(template_body="<full CFN YAML>", mode="security")
# mode="supported" keeps all LocalStack resources
# mode="security" keeps only security-relevant resources (IAM, S3, Lambda, DynamoDB, etc.)
```

### Generating CFN from Veritas recon

```python
sandbox.generate_cfn_from_recon(
    resources=[{"type": "DynamoDB", "name": "orders-table"},
               {"type": "S3", "name": "data-bucket"}],
    description="MyService sandbox replica")
```

## Service Mock Configuration

After creating resources, apply auth mocks. The recon agent writes a
`ServiceMockConfig` entity to the graph; the deploy agent reads and applies.

```python
graph_query(cypher="MATCH (s:ServiceMockConfig {run_id: '<run_id>'}) RETURN s")

sandbox.apply_service_mocks(env_id="companion_x-localstack-1", config={
    "aaa": {"enabled": True, "bypass_mode": "authorize_all"},
    "odin": {"enabled": True, "material_sets": {
        "com.amazon.myservice.prod": {"aws_account_id": "123456789012"}}},
    "cloudauth": {"enabled": True, "bypass_mode": "disable"},
    "turtle": {"enabled": True, "credential_paths": [
        "/apollo/var/env/MyService/credentials/prod"]}
})
```

## Workspace Files (Artifacts Directory)

Sandbox workspace = scratchpad for recon/deploy agents. Flushed on terminate.

```python
sandbox.workspace_dir(env_id)
# Returns: {"workspace_dir": "/tmp/factory-sandbox/{env_id}/artifacts/"}
```

| File | Written by | Read by |
|------|-----------|---------|
| `recon.json` | Recon agent | Sandbox setup, App deploy |
| `cfn-template.yaml` | Code discovery | App deploy |
| `code/<filename>` | Code discovery | App deploy |
| `dependencies.json` | Code discovery | App deploy |
| `sandbox-status.json` | Sandbox setup | Sandbox summary |

Workspace files = scratchpad. Neo4j graph = curated only: `TargetApp`,
`ServiceMockConfig`, `SandboxValidation`, `AppDeployment`, `ProvenExploit`,
`Vulnerability`.

## LocalStack Supported Services

IAM, Lambda, S3, DynamoDB, SQS, SNS, API Gateway, CloudFormation, STS, SSM. IAM enforcement is enabled (`ENFORCE_IAM=1`).

## Deployment Sequence

### Profile path (quickest — single vulnerable app)

1. `sandbox.list_profiles()` — discover available targets
2. `sandbox.provision(profile="webgoat")` — auto-terminates previous, starts container
3. Wait for health check, then attack

### LocalStack path (full AWS emulation)

1. `sandbox.list_environments()` — find or provision a LocalStack env
2. `sandbox.provision()` — if no env exists (adapter: `localstack`)
3. Deploy resources via CFN or direct CLI
4. `sandbox.apply_service_mocks()` — if ServiceMockConfig exists in graph
5. Verify all resources with list/describe commands
6. Hand off `env_id` + resource list to pentest agents
