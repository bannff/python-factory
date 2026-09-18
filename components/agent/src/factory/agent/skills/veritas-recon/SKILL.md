---
name: veritas-recon
description: Discover AWS infrastructure for any app via the Veritas security graph.
---
# Veritas Reconnaissance

You are performing infrastructure discovery using the Veritas graph (6B+ nodes).

## Primary Tool: search_resources (FAST)

Use this for ALL infra discovery. It generates optimized Cypher that won't timeout.

```
search_resources(resource_type="DynamoDB", name_contains="<app_short_name>")
search_resources(resource_type="Lambda", name_contains="<app_short_name>")
search_resources(resource_type="SQS", name_contains="<app_short_name>")
search_resources(resource_type="S3", name_contains="<app_short_name>")
search_resources(resource_type="IamRole", name_contains="<app_short_name>")
search_resources(resource_type="ECSCluster", name_contains="<app_short_name>")
```

Returns: `[{type, name, account}]` — write each to local graph.

## App Topology

```
get_app_topology(app_name="<full_name>", exact=true)
```

Returns accounts, pipelines, bindles. Use to find account IDs and CDK packages.

## Security Profile

```
get_app_security_profile(app_name="<full_name>", exact=true)
```

Returns data classification, network exposure, connectivity risks.

## Resource Permissions

```
get_resource_permissions(resource_type="S3", resource_identifier="<bucket>")
```

Returns who can access a resource and how.

## Raw Cypher (use sparingly)

These Cypher examples target the **Veritas** service (via the
`query_veritas` MCP tool), NOT the local graph brick. Veritas
legitimately speaks Cypher; the local graph brick uses typed
tools (`graph_find_entities`, `graph_get_findings_for_run`, …)
because its networkx backend has no Cypher engine.

WARNING: Complex joins TIMEOUT on 6B+ nodes. Only use for anchored lookups:

```cypher
MATCH (a:VeritasApp {veritas_app_name: '<NAME>'}) RETURN a
MATCH (a:VeritasApp {veritas_app_name: '<NAME>'})-[:HAS_RESOURCE]->(p:Pipeline) RETURN p
```

Property names: `veritas_app_name`, `aws_account_id`, `stage`, `package_name`.

## Write to Local Graph

For each discovered resource:
```
graph_add_entity(entity_id="ddb-<name>", entity_type="DynamoDBTable",
  properties={name, account, region, run_id, app})
```

Always include `run_id` and `app` in properties for scoping.

## Chained Tool Examples

### Chain 1: Full resource audit (permissions + data flows)
After discovering a DynamoDB table, check who can access it and where data flows:
```
# Step 1: Find the table
search_resources(resource_type="DynamoDB", name_contains="Pets.Profile")

# Step 2: Check who has access
get_resource_permissions(resource_type="DynamoDB", resource_identifier="Pets.Profile.Pets")
# Returns: [{accessor_type: "IamRole", accessor_id: "ServiceRole", permission: "dynamodb:*"}]

# Step 3: Trace data flows
get_data_flows(resource_type="DynamoDB", resource_identifier="Pets.Profile.Pets", direction="outbound")
# Returns: where data goes (Lambda triggers, streams, etc.)

get_data_flows(resource_type="Lambda", resource_identifier="PetsProfileVetStreamProcessor", direction="outbound")
# Returns: where Lambda sends data (SQS, SNS, S3, etc.)

# Step 4: Write the full picture to graph
graph_add_entity(entity_id="ddb-pets", entity_type="DynamoDBTable", ...)
graph_add_entity(entity_id="role-service", entity_type="IAMRole", ...)
graph_add_relationship(relationship_id="rel-role-access-ddb",
  relationship_type="CAN_ACCESS", source_id="role-service", target_id="ddb-pets",
  properties={"permission": "dynamodb:*"})
```

### Chain 2: Security profile deep dive
```
# Step 1: Get app topology
get_app_topology(app_name="PetsProfileService", exact=true)

# Step 2: Get security profile (data classification, exposure)
get_app_security_profile(app_name="PetsProfileService", exact=true)
# Returns: DataProfileCard (PII, HIPAA), NetworkProfileCard (endpoints),
#          ConnectivityProfileCard (cross-account risks)

# Step 3: For each high-value resource, check permissions
get_resource_permissions(resource_type="S3", resource_identifier="pets-rx-images")
# Returns: who can read PII bucket

# Step 4: Store security observations
memory_store(content="PetsProfileService: CRITICAL data classification,
  22 S3 buckets with PII, 40 external endpoints, 197 AAA inbound connections",
  user_id="kiro-agent", category="fact")
```

### Chain 3: Deployment chain tracing
```
# Step 1: Get deployment chain for the pipeline
get_deployment_chain(identifier="PetsProfileService")
# Returns: pipeline stages, regions, prod/non-prod accounts

# Step 2: For each prod account, search for resources
search_resources(resource_type="DynamoDB", account_id="886436967791")
# Returns: prod DynamoDB tables
```

## Account-Scoped Discovery (STEP 2b)

Some resource types TIMEOUT when used with `name_contains` on the 6B+ node
graph. Use the `account_id` from STEP 1 instead:

```
search_resources(resource_type="IamRole",       account_id="<acct>", limit=50)
search_resources(resource_type="IamUser",       account_id="<acct>", limit=50)
search_resources(resource_type="IamPolicy",     account_id="<acct>", limit=50)
search_resources(resource_type="EC2",           account_id="<acct>", limit=50)
search_resources(resource_type="VPC",           account_id="<acct>", limit=50)
search_resources(resource_type="SecurityGroup", account_id="<acct>", limit=50)
```

Run for EACH account discovered in STEP 1.

## STEP 3 — Write the Workspace `recon.json`

Discovered resources go to a workspace JSON file, NOT to the graph. Only
curated entities (`TargetApp`, `ServiceMockConfig`) are graph-bound; the
sandbox-setup agent reads the rest from this file.

Workspace path: `/tmp/factory-sandbox/{env_id}/artifacts/recon.json`

Build the JSON object:
```json
{"app": "<target_app>", "run_id": "<run_id>",
 "resources": [
   {"type": "DynamoDB", "name": "...", "account": "..."},
   {"type": "Lambda",   "name": "...", "account": "..."}
 ],
 "security_profile": {...},
 "accounts": ["..."]}
```

Write it via sandbox.execute:
```
sandbox.execute(env_id,
  'cat > /tmp/factory-sandbox/{env_id}/artifacts/recon.json << EOF\n<json>\nEOF')
```

ONLY write to graph: `TargetApp` entity + `ServiceMockConfig`.
Everything else → workspace `recon.json` file.
