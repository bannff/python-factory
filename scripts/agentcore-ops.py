#!/usr/bin/env python3
"""AgentCore operations helper — gateway sync, runtime warmup, status checks.

Usage:
    python3 -u scripts/agentcore-ops.py status
    python3 -u scripts/agentcore-ops.py warm
    python3 -u scripts/agentcore-ops.py sync
    python3 -u scripts/agentcore-ops.py update-target
    python3 -u scripts/agentcore-ops.py fix-protocol

Env: AWS_PROFILE=burner (default)
"""
import boto3
import json
import os
import sys
import time
import urllib.request
import urllib.parse

PROFILE = os.environ.get("AWS_PROFILE", "burner")
REGION = "us-east-1"
RUNTIME_ID = "art_companion_x_runtime-J2jwR5C2kY"
RUNTIME_ARN = f"arn:aws:bedrock-agentcore:{REGION}:647239283265:runtime/{RUNTIME_ID}"
GATEWAY_ID = "art-mcp-gateway-mxbeovlsil"
TARGET_ID = "WUM3EVHABE"

# M2M Cognito pool (gateway -> runtime)
M2M_TOKEN_URL = "https://art-m2m-agentcore.auth.us-east-1.amazoncognito.com/oauth2/token"
M2M_CLIENT_ID = "7cvo1jm7079dr4ljuu7g2aib8k"
M2M_SECRET_ARN = "bedrock-agentcore-identity!default/oauth2/art-gateway-m2m-provider"
M2M_SCOPE = "agentcore-runtime/invoke"

# Inbound Cognito pool (Kiro -> gateway)
INBOUND_TOKEN_URL = "https://agentcore-19089a2b.auth.us-east-1.amazoncognito.com/oauth2/token"
INBOUND_CLIENT_ID = "7m52stvtrvrme2ed626177v6dq"
INBOUND_SECRET_ARN = "art/agentcore/inbound-gateway-client-secret"
INBOUND_SCOPE = "art-mcp-gateway/invoke"

RUNTIME_ENDPOINT = (
    "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/"
    "arn%3Aaws%3Abedrock-agentcore%3Aus-east-1%3A647239283265"
    "%3Aruntime%2Fart_companion_x_runtime-J2jwR5C2kY/invocations"
)

OAUTH_PROVIDER_ARN = (
    f"arn:aws:bedrock-agentcore:{REGION}:647239283265:"
    "token-vault/default/oauth2credentialprovider/art-gateway-m2m-provider"
)

CONTAINER_URI = "647239283265.dkr.ecr.us-east-1.amazonaws.com/art-companion-x:20260306-143000-99b15cb"
ROLE_ARN = "arn:aws:iam::647239283265:role/DeployAgents-Compute-AgentCoreRoleD989E366-umVT1IIKfNeQ"
AUTHORIZER_CONFIG = {
    "customJWTAuthorizer": {
        "discoveryUrl": f"https://cognito-idp.{REGION}.amazonaws.com/us-east-1_5kT4bg30K/.well-known/openid-configuration",
        "allowedClients": [M2M_CLIENT_ID],
    }
}
NETWORK_CONFIG = {
    "networkMode": "VPC",
    "networkModeConfig": {
        "securityGroups": ["sg-0d5808fe628ac8367"],
        "subnets": ["subnet-0d8227396ae8b6064", "subnet-0d210865720f7894a"],
    },
}


def get_session():
    return boto3.Session(profile_name=PROFILE, region_name=REGION)


def get_cp(session=None):
    """Control-plane client."""
    return (session or get_session()).client("bedrock-agentcore-control")


def get_dp(session=None):
    """Data-plane client."""
    return (session or get_session()).client("bedrock-agentcore")


def get_cognito_token(token_url, client_id, client_secret, scope):
    """Fetch an OAuth2 client_credentials token."""
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }).encode()
    req = urllib.request.Request(
        token_url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


def get_m2m_secret(session=None):
    """Retrieve M2M client secret from Secrets Manager."""
    sm = (session or get_session()).client("secretsmanager")
    secret = sm.get_secret_value(SecretId=M2M_SECRET_ARN)
    data = json.loads(secret["SecretString"])
    return data.get("client_secret") or data.get("clientSecret")


def get_inbound_secret(session=None):
    """Retrieve inbound gateway client secret from Secrets Manager."""
    sm = (session or get_session()).client("secretsmanager")
    secret = sm.get_secret_value(SecretId=INBOUND_SECRET_ARN)
    data = json.loads(secret["SecretString"])
    return data.get("client_secret") or data.get("clientSecret")


# ── Commands ────────────────────────────────────────────────────────


def cmd_status():
    """Show runtime and gateway target status."""
    session = get_session()
    cp = get_cp(session)

    rt = cp.get_agent_runtime(agentRuntimeId=RUNTIME_ID)
    print("=== RUNTIME ===")
    print(f"  Status: {rt['status']}")
    auth = rt.get("authorizerConfiguration", {})
    print(f"  Auth:   {json.dumps(auth, indent=2)}")
    proto = rt.get("protocolConfiguration", "MISSING")
    print(f"  Protocol: {proto}")

    tgt = cp.get_gateway_target(
        gatewayIdentifier=GATEWAY_ID, targetId=TARGET_ID
    )
    print("\n=== GATEWAY TARGET ===")
    print(f"  Status:  {tgt['status']}")
    reasons = tgt.get("statusReasons", [])
    if reasons:
        print(f"  Reasons: {reasons}")
    print(f"  Last sync: {tgt.get('lastSynchronizedAt', 'never')}")
    creds = tgt.get("credentialProviderConfigurations", [])
    print(f"  Cred providers: {len(creds)}")


def cmd_warm():
    """Warm the runtime by sending an MCP initialize via M2M token."""
    session = get_session()
    print("Fetching M2M secret + token...")
    m2m_secret = get_m2m_secret(session)
    token = get_cognito_token(M2M_TOKEN_URL, M2M_CLIENT_ID, m2m_secret, M2M_SCOPE)
    init_msg = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "warmup", "version": "0.1.0"}},
    })
    print("Sending initialize to runtime (timeout=120s)...")
    req = urllib.request.Request(
        RUNTIME_ENDPOINT, data=init_msg.encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f"Response: {resp.read().decode('utf-8')[:500]}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:500]}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_sync():
    """Trigger synchronize_gateway_targets."""
    cp = get_cp()
    print("Calling synchronize_gateway_targets...")
    try:
        resp = cp.synchronize_gateway_targets(
            gatewayIdentifier=GATEWAY_ID, targetId=TARGET_ID
        )
        print(f"Response: {resp.get('status', 'ok')}")
    except Exception as e:
        print(f"Error: {e}")


def cmd_update_target():
    """Re-submit update_gateway_target to reset UPDATE_UNSUCCESSFUL and trigger sync."""
    cp = get_cp()
    print("Submitting update_gateway_target...")
    resp = cp.update_gateway_target(
        gatewayIdentifier=GATEWAY_ID,
        targetId=TARGET_ID,
        name="companion-x",
        targetConfiguration={
            "mcp": {"mcpServer": {"endpoint": RUNTIME_ENDPOINT}}
        },
        credentialProviderConfigurations=[{
            "credentialProviderType": "OAUTH",
            "credentialProvider": {
                "oauthCredentialProvider": {
                    "providerArn": OAUTH_PROVIDER_ARN,
                    "scopes": ["agentcore-runtime/invoke"],
                }
            },
        }],
    )
    print(f"Status: {resp['status']}")

    # Poll for result
    for i in range(24):
        time.sleep(5)
        tgt = cp.get_gateway_target(
            gatewayIdentifier=GATEWAY_ID, targetId=TARGET_ID
        )
        status = tgt["status"]
        reasons = tgt.get("statusReasons", [])
        print(f"  [{(i+1)*5}s] {status} {reasons}")
        if status not in ("UPDATING", "CREATING"):
            break



def cmd_fix_protocol():
    """Restore protocolConfiguration + auth after agentcore deploy strips them."""
    session = get_session()
    cp = get_cp(session)

    rt = cp.get_agent_runtime(agentRuntimeId=RUNTIME_ID)
    current_uri = rt.get("agentRuntimeArtifact", {}).get("containerConfiguration", {}).get("containerUri", "MISSING")
    uri = CONTAINER_URI  # Always deploy the URI defined at top of file
    print(f"Current: status={rt['status']} proto={rt.get('protocolConfiguration', 'MISSING')}")
    print(f"Current image: {current_uri}")
    print(f"Target image:  {uri}")
    if current_uri == uri:
        print("Image already matches — applying protocol/auth only.")
    else:
        print("Deploying NEW image.")

    print("Applying protocolConfiguration={'serverProtocol': 'MCP'} + auth...")
    cp.update_agent_runtime(
        agentRuntimeId=RUNTIME_ID,
        agentRuntimeArtifact={"containerConfiguration": {"containerUri": uri}},
        roleArn=ROLE_ARN,
        networkConfiguration=NETWORK_CONFIG,
        authorizerConfiguration=AUTHORIZER_CONFIG,
        protocolConfiguration={"serverProtocol": "MCP"},
    )

    # Poll until stable
    for i in range(12):
        time.sleep(10)
        rt = cp.get_agent_runtime(agentRuntimeId=RUNTIME_ID)
        st = rt["status"]
        proto = rt.get("protocolConfiguration", "MISSING")
        print(f"  [{(i+1)*10}s] status={st} proto={proto}")
        if st not in ("UPDATING", "CREATING"):
            break

    if rt["status"] == "READY":
        print("Runtime ready. Re-syncing gateway target...")
        cmd_update_target()
    else:
        print(f"Runtime not ready ({rt['status']}). Run 'update-target' manually once it stabilizes.")


if __name__ == "__main__":
    cmds = {
        "status": cmd_status,
        "warm": cmd_warm,
        "sync": cmd_sync,
        "update-target": cmd_update_target,
        "fix-protocol": cmd_fix_protocol,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(f"Usage: {sys.argv[0]} {{{','.join(cmds)}}}")
        sys.exit(1)
    cmds[sys.argv[1]]()
