---
name: builder-recon
description: Reads Amazon internal code repositories via the builder brick and extracts infrastructure and service dependency information. Use for internal code search, pipeline health, and package file discovery.
---

# Builder Recon Skill

Teaches agents to read Amazon internal code repositories via the builder brick and extract infrastructure and service dependency information.

## Builder MCP Tools

| Tool | Category | Purpose |
|------|----------|---------|
| `builder_list_package_files` | operational | List files in a Brazil package directory |
| `builder_read_package_file` | operational | Read a specific file from a package |
| `builder_search_code` | operational | Search internal code repos (regex, repo:, fp: filters) |
| `builder_read_url` | operational | Read content from internal Amazon URLs |
| `builder_get_pipeline` | operational | Get pipeline stages and health |

## Reading Package Files

### List files in a package

```python
builder_list_package_files(package_name="MyServiceCDK")
builder_list_package_files(package_name="MyServiceCDK", path="lib")
builder_list_package_files(package_name="MyServiceCDK", path="lib", branch="mainline")
```

Parameters: `package_name` (required), `path` (default: root), `branch` (default: `mainline`).

### Read a specific file

```python
builder_read_package_file(package_name="MyServiceCDK", file_path="lib/my-service-stack.ts")
builder_read_package_file(package_name="MyServiceCDK", file_path="cdk.json")
builder_read_package_file(package_name="MyServiceCDK", file_path="bin/app.ts")
```

Parameters: `package_name` (required), `file_path` (required), `branch` (default: `mainline`).

## What to Look For in CDK Packages

CDK packages contain the infrastructure-as-code that defines the target app's AWS resources.

### File structure

```
MyServiceCDK/
├── bin/app.ts              ← Entry point, stack instantiation
├── lib/
│   ├── my-service-stack.ts ← Main stack (resources defined here)
│   ├── constructs/         ← Custom L2/L3 constructs
│   └── config/             ← Environment configs
├── cdk.json                ← CDK app config, context values
├── package.json            ← Dependencies (look for @aws-cdk/* versions)
└── tsconfig.json
```

### Priority files to read

1. `lib/*.ts` — Main stack files. This is where DynamoDB tables, Lambda functions, IAM roles, S3 buckets, SQS queues, and API Gateways are defined.
2. `bin/*.ts` — Stack instantiation. Shows which stacks exist and how they're parameterized.
3. `cdk.json` — Context values, feature flags, account/region config.

### What to extract

| Resource | CDK Pattern |
|----------|-------------|
| DynamoDB | `new dynamodb.Table(`, `new dynamodb.TableV2(` |
| Lambda | `new lambda.Function(`, `new NodejsFunction(`, `new PythonFunction(` |
| S3 | `new s3.Bucket(` |
| SQS | `new sqs.Queue(` |
| IAM Role | `new iam.Role(`, `.addToPolicy(`, `.grantReadWrite(`, `.grant(` |
| API Gateway | `new apigateway.RestApi(`, `new HttpApi(` |
| ECS | `new ecs.FargateService(`, `new ecs.Ec2Service(` |
| Step Functions | `new sfn.StateMachine(` |
| EventBridge | `new events.Rule(` |

## What to Look For in Service Packages

Service packages contain application code (Java, Python, etc.).

| Priority | Path | Why |
|----------|------|-----|
| 1 | `src/` | Business logic, handlers, Guice/Dagger modules |
| 2 | `configuration/` | Runtime configs, feature flags, endpoint URLs |
| 3 | `definition.yaml` | RDE setup — ports, local dependencies |
| 4 | `build.gradle` / `pom.xml` | Dependency list reveals internal integrations |

## Detecting Service Dependencies

When reading code, detect these Amazon internal service patterns. Each detected dependency becomes a `ServiceMockConfig` entry for the sandbox deployer.

| Service | Code Patterns to Grep | Mock Config |
|---------|----------------------|-------------|
| CloudAuth | `CloudAuthModule`, `CloudAuthAuthorizer`, `CloudAuthCredentials`, `cloudAuth.enabled`, `oauth.cloudauth` | `cloudauth: {enabled: true, bypass_mode: "disable"}` |
| AAA | `AAASecurityDaemon`, `@AAA`, `register_with_aaa`, `aaa.enabled` | `aaa: {enabled: true, service_name: "<name>", operations: [...], bypass_mode: "authorize_all"}` |
| Odin | `odin-get`, `OdinLocalRetriever`, `com.amazon.*` material sets, `odin.amazon.com` | `odin: {enabled: true, material_sets: {"<set>": {"aws_account_id": "<acct>"}}}` |
| Coral | `CoralModule`, Coral `.config` files, RPC endpoints, service model files | `coral: {enabled: true, service_stubs: [{service_name: "<svc>", endpoint: "<url>"}]}` |
| Turtle | `turtleCredentialsPath`, `ProfileCredentialsProvider`, `/apollo/var/env/<svc>/credentials` | `turtle: {enabled: true, credential_paths: ["..."]}` |

## Writing ServiceMockConfig to Graph

After detecting dependencies, write a single config entity for the sandbox deployer:

```python
graph_add_entity(
    entity_id="svc-mock-<run_id>",
    entity_type="ServiceMockConfig",
    properties={
        "run_id": "<run_id>",
        "app": "<target_app>",
        "aaa": {"enabled": True, "service_name": "MyService",
                "operations": ["GetItem"], "bypass_mode": "authorize_all"},
        "odin": {"enabled": True, "material_sets": {
            "com.amazon.myservice.prod": {"aws_account_id": "123456789012"}}},
        "cloudauth": {"enabled": True, "bypass_mode": "disable"},
        "coral": {"enabled": False},
        "turtle": {"enabled": False}
    })
```

If NO internal dependencies are found, write config with all services disabled:

```python
graph_add_entity(
    entity_id="svc-mock-<run_id>",
    entity_type="ServiceMockConfig",
    properties={"run_id": "<run_id>", "app": "<target_app>",
                "aaa": {"enabled": False}, "odin": {"enabled": False},
                "cloudauth": {"enabled": False}, "coral": {"enabled": False},
                "turtle": {"enabled": False}})
```

## Recommended Recon Sequence

1. Get CDK package name from Veritas pipeline data (recon agent provides this)
2. `builder_list_package_files(package_name="<CDK pkg>")` — survey the repo
3. `builder_list_package_files(package_name="<CDK pkg>", path="lib")` — find stack files
4. `builder_read_package_file` on each `lib/*.ts` file — extract resource definitions
5. `builder_read_package_file` on `bin/app.ts` — understand stack composition
6. If service package exists, read `src/` and `configuration/` for dependency detection
7. Write discovered resources to graph as entities (see veritas-recon skill)
8. Write `ServiceMockConfig` entity to graph for sandbox deployer
9. Store observations in memory: `memory_store(content="...", user_id="kiro-agent", category="fact")`

## Searching Code

For broader discovery when you don't know the exact package name:

```python
builder_search_code(query="MyServiceName CDK", search_type="repositories")
builder_search_code(query="repo:MyServiceCDK new dynamodb.Table", search_type="code")
builder_search_code(query="fp:lib/*.ts CloudAuthModule", search_type="code")
```

## Pipeline Inspection

```python
builder_get_pipeline(pipeline_name="MyServicePipeline")
```

Returns stages, health status, and deployment history. Cross-reference with `get_deployment_chain` from the veritas brick for account mapping.
