"""Red team playbook addendum — service mock detection + deployment.

Teaches recon agents to detect Amazon internal service dependencies
(AAA, Odin, CloudAuth, Coral, Turtle) in CDK code and write a
ServiceMockConfig entity to the graph. Teaches deploy agents to
read that config and apply mocks via sandbox.apply_service_mocks.
"""
from __future__ import annotations

# ── Recon addendum: detect internal service deps ─────────────────────

SERVICE_MOCK_DETECTION = (
    "\n== SERVICE DEPENDENCY DETECTION ==\n"
    "When reading CDK/code, detect Amazon internal service deps.\n"
    "For EACH detected dep, build a ServiceMockConfig and store it\n"
    "as a graph entity so the sandbox deployer can configure mocks.\n\n"
    "DETECTION PATTERNS:\n"
    "1. CloudAuth — look for: CloudAuthModule, CloudAuthAuthorizer,\n"
    "   cloudAuth.enabled, CloudAuthCredentials, oauth.cloudauth\n"
    "2. AAA — look for: AAASecurityDaemon, @AAA annotation,\n"
    "   AAA relationship configs, register_with_aaa, aaa.enabled\n"
    "3. Odin — look for: odin-get, OdinLocalRetriever, material\n"
    "   set references (com.amazon.*), odin.amazon.com URLs\n"
    "4. Coral — look for: Coral client configs (.config files),\n"
    "   CoralModule, RPC endpoints, Coral service model files\n"
    "5. Turtle — look for: turtleCredentialsPath,\n"
    "   ProfileCredentialsProvider, turtle credential file paths\n\n"
    "WHEN DETECTED, write to graph:\n"
    "  graph_add_entity(\n"
    "    entity_id='svc-mock-{{run_id}}',\n"
    "    entity_type='ServiceMockConfig',\n"
    "    properties={\n"
    "      'run_id': '{{run_id}}',\n"
    "      'app': '{{target_app}}',\n"
    "      'aaa': {'enabled': true, 'service_name': '<name>',\n"
    "              'operations': [...], 'bypass_mode': "
    "'authorize_all'},\n"
    "      'odin': {'enabled': true, 'material_sets': {\n"
    "        '<set_name>': {'aws_account_id': '<acct_id>'}}},\n"
    "      'cloudauth': {'enabled': true, "
    "'bypass_mode': 'disable'},\n"
    "      'coral': {'enabled': true, 'service_stubs': [\n"
    "        {'service_name': '<svc>', 'endpoint': '<url>'}]},\n"
    "      'turtle': {'enabled': true, 'credential_paths': [\n"
    "        '/apollo/var/env/<svc>/credentials/...']}\n"
    "    }\n"
    "  )\n\n"
    "If NO internal deps found, write config with all disabled.\n"
)

# ── Deploy addendum: apply service mocks after CFN ───────────────────

SERVICE_MOCK_DEPLOYMENT = (
    "\n== SERVICE MOCK DEPLOYMENT ==\n"
    "AFTER deploying CFN, apply service mocks:\n\n"
    "1. Look up the ServiceMockConfig via the typed graph tool\n"
    "   (backend-agnostic — no Cypher):\n"
    "   graph_find_entities(\n"
    "     entity_type='ServiceMockConfig',\n"
    "     properties={'run_id': '{{run_id}}'})\n\n"
    "2. If found, call sandbox.apply_service_mocks:\n"
    "   sandbox.apply_service_mocks(\n"
    "     env_id='<env_id>',\n"
    "     config=<ServiceMockConfig properties dict>\n"
    "   )\n\n"
    "3. Verify mocks applied:\n"
    "   - Odin: check AWS credentials are set correctly\n"
    "   - Turtle: verify credential files exist at paths\n"
    "   - CloudAuth: confirm bypass mode is active\n"
    "   - AAA: confirm authorize_all mode\n\n"
    "4. Store mock status in graph:\n"
    "   graph_add_entity(entity_id='mock-status-{{run_id}}',\n"
    "     entity_type='MockDeployStatus',\n"
    "     properties={run_id, app, mocks_applied: [...]})\n"
)

# ── Recon addendum: Veritas infra discovery ──────────────────────────

VERITAS_INFRA_DISCOVERY = (
    "\n== VERITAS INFRASTRUCTURE DISCOVERY ==\n"
    "Use search_resources (NOT raw Cypher) to find AWS infra.\n"
    "Raw Cypher joins timeout on the 6B+ node graph.\n\n"
    "FAST DISCOVERY PATTERN:\n"
    "For each resource type, call search_resources:\n"
    "  search_resources(resource_type='DynamoDB', "
    "name_contains='<app_short_name>')\n"
    "  search_resources(resource_type='Lambda', "
    "name_contains='<app_short_name>')\n"
    "  search_resources(resource_type='SQS', "
    "name_contains='<app_short_name>')\n"
    "  search_resources(resource_type='S3', "
    "name_contains='<app_short_name>')\n"
    "  search_resources(resource_type='IamRole', "
    "name_contains='<app_short_name>')\n"
    "  search_resources(resource_type='ECSCluster', "
    "name_contains='<app_short_name>')\n\n"
    "For each result, write to graph:\n"
    "  graph_add_entity(entity_id='ddb-<table_name>',\n"
    "    entity_type='DynamoDB',\n"
    "    properties={name, account, region, run_id, app})\n\n"
    "TWO PATHS FOR CFN GENERATION:\n"
    "1. CDK path: If pipeline contains 'CDK' or "
    "'Infrastructure' package, read it via builder MCP\n"
    "2. Veritas path: If no CDK, generate golden-default CFN\n"
    "   from discovered resources (the cfn-builder agent\n"
    "   reads your graph entities and builds CFN)\n\n"
    "ALWAYS discover infra via Veritas even if CDK exists —\n"
    "it validates what the CDK should contain.\n"
)
