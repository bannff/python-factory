"""Red team setup swarms — analyze + deploy with ensemble + rosters."""
from __future__ import annotations

from .redteam_playbooks import (
    ANALYZE_CODE_READER, ANALYZE_ATTACK_PLANNER,
    DEPLOY_SANDBOX_DEPLOYER, DEPLOY_ENV_VALIDATOR,
)
from .redteam_service_mocks import (
    SERVICE_MOCK_DETECTION, SERVICE_MOCK_DEPLOYMENT,
    VERITAS_INFRA_DISCOVERY,
)
from .models import HAIKU, SONNET, NOVA2_LITE, SCOUT, MAVERICK, GPT_OSS

_ANALYZE_ROSTER = (
    "\n\nYOUR TEAM (hand off to each in order):\n"
    "1. code-reader — reads CDK source, models in graph\n"
    "2. attack-planner — plans attack paths from graph model\n"
    "3. analyze-scout — independent CDK review, finds missed configs\n"
    "4. analyze-maverick — deep-dives on IAM policies in CDK\n"
    "5. analyze-nova — checks for secrets, env vars, hardcoded creds\n"
    "6. graph-modeler — final graph model, stores consolidated plan\n"
    "After YOUR work, hand off to the next agent who hasn't gone."
)

_DEPLOY_ROSTER = (
    "\n\nYOUR TEAM (hand off to each in order):\n"
    "1. sandbox-deployer — deploys CFN to LocalStack\n"
    "2. env-validator — validates deployed resources match target\n"
    "3. deploy-scout — enumerates all resources independently\n"
    "4. deploy-maverick — checks IAM roles/policies in sandbox\n"
    "5. deploy-nova — validates data stores (DynamoDB, S3)\n"
    "6. resource-auditor — final audit, flags drift, stores summary\n"
    "After YOUR work, hand off to the next agent who hasn't gone."
)

_A_SCOUT = (
    "\n\nYou are analyze-scout. Do independent CDK review — look "
    "for configs code-reader missed: Lambda handlers, API Gateway "
    "routes, CloudWatch rules, SNS/SQS queues. Store new findings."
)
_A_MAV = (
    "\n\nYou are analyze-maverick. Deep-dive on IAM policies in "
    "CDK: inline policies, managed policies, trust relationships, "
    "resource-based policies. Flag overpermissive patterns."
)
_A_NOVA = (
    "\n\nYou are analyze-nova. Search CDK for secrets, env vars, "
    "hardcoded credentials, API keys. Check stages.ts and any "
    "config files. Store each finding with severity."
)
_A_MODELER = (
    "\n\nYou are graph-modeler (final). Retrieve all findings from "
    "memory. Build consolidated graph model. Store ANALYSIS SUMMARY."
)

ANALYZE_SWARM: dict = {
    "id": "redteam-analyze",
    "name": "Red Team Analyze Swarm",
    "description": "Read CDK, model app in graph, plan attack paths.",
    "entry_point": "code-reader",
    "max_handoffs": 20,
    "max_iterations": 40,
    "agents": [
        {"id": "code-reader", "model": HAIKU,
         "system_prompt": ANALYZE_CODE_READER + SERVICE_MOCK_DETECTION
         + VERITAS_INFRA_DISCOVERY + _ANALYZE_ROSTER, "tools": []},
        {"id": "attack-planner", "model": SONNET,
         "system_prompt": ANALYZE_ATTACK_PLANNER + _ANALYZE_ROSTER,
         "tools": []},
        {"id": "analyze-scout", "model": SCOUT,
         "system_prompt": ANALYZE_CODE_READER + _ANALYZE_ROSTER
         + _A_SCOUT, "tools": []},
        {"id": "analyze-maverick", "model": MAVERICK,
         "system_prompt": ANALYZE_ATTACK_PLANNER + _ANALYZE_ROSTER
         + _A_MAV, "tools": []},
        {"id": "analyze-nova", "model": NOVA2_LITE,
         "system_prompt": ANALYZE_CODE_READER + _ANALYZE_ROSTER
         + _A_NOVA, "tools": []},
        {"id": "graph-modeler", "model": GPT_OSS,
         "system_prompt": ANALYZE_ATTACK_PLANNER + _ANALYZE_ROSTER
         + _A_MODELER, "tools": []},
    ],
}

_D_SCOUT = (
    "\n\nYou are deploy-scout. Enumerate all deployed resources "
    "independently: list IAM roles, S3 buckets, DynamoDB tables, "
    "Lambda functions. Compare against what deployer reported."
)
_D_MAV = (
    "\n\nYou are deploy-maverick. Check IAM roles and policies in "
    "the sandbox. Test assume-role, list attached policies, check "
    "for Action:*/Resource:* patterns."
)
_D_NOVA = (
    "\n\nYou are deploy-nova. Validate data stores: DynamoDB table "
    "schemas, S3 bucket encryption, access logging. Check for "
    "unencrypted data at rest."
)
_D_AUDITOR = (
    "\n\nYou are resource-auditor (final). Retrieve all deploy "
    "findings from memory. Compare deployed state vs intended. "
    "Flag drift. Store DEPLOY SUMMARY."
)

DEPLOY_SWARM: dict = {
    "id": "redteam-deploy",
    "name": "Red Team Deploy Swarm",
    "description": "Deploy CFN to LocalStack, validate resources.",
    "entry_point": "sandbox-deployer",
    "max_handoffs": 20,
    "max_iterations": 40,
    "agents": [
        {"id": "sandbox-deployer", "model": HAIKU,
         "system_prompt": DEPLOY_SANDBOX_DEPLOYER
         + SERVICE_MOCK_DEPLOYMENT + _DEPLOY_ROSTER,
         "tools": []},
        {"id": "env-validator", "model": SONNET,
         "system_prompt": DEPLOY_ENV_VALIDATOR + _DEPLOY_ROSTER,
         "tools": []},
        {"id": "deploy-scout", "model": SCOUT,
         "system_prompt": DEPLOY_SANDBOX_DEPLOYER + _DEPLOY_ROSTER
         + _D_SCOUT, "tools": []},
        {"id": "deploy-maverick", "model": MAVERICK,
         "system_prompt": DEPLOY_ENV_VALIDATOR + _DEPLOY_ROSTER
         + _D_MAV, "tools": []},
        {"id": "deploy-nova", "model": NOVA2_LITE,
         "system_prompt": DEPLOY_SANDBOX_DEPLOYER + _DEPLOY_ROSTER
         + _D_NOVA, "tools": []},
        {"id": "resource-auditor", "model": GPT_OSS,
         "system_prompt": DEPLOY_ENV_VALIDATOR + _DEPLOY_ROSTER
         + _D_AUDITOR, "tools": []},
    ],
}

SETUP_SWARMS: list[dict] = [ANALYZE_SWARM, DEPLOY_SWARM]
