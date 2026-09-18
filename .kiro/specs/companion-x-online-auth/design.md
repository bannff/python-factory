# Design: Companion-X Online Auth

## Overview

Two-track design: native MCP OAuth where the client supports it (no proxy), per-user proxy-mode where it doesn't. Both terminate at the same AgentCore JWT authorizer pointed at a Cognito user pool federated with Midway via the existing `iphled-webapp-cognito-v2` Federate profile pattern.

## Architecture — The Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│ MCP-spec-compliant clients (Claude Code, future Kiro)           │
│   add Companion-X by URL → discover via PRM → PKCE in browser   │
│   → store tokens locally → speak Streamable HTTP directly       │
└─────────────────────┬───────────────────────────────────────────┘
                      │  Authorization: Bearer <user-jwt>
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stdio-only clients (Kiro today, Q CLI offline) → art-mcp-proxy  │
│   login → ~/.art/credentials.json → Bearer on every JSON-RPC    │
└─────────────────────┬───────────────────────────────────────────┘
                      │  Authorization: Bearer <user-jwt>
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ AgentCore Gateway / Runtime — CUSTOM_JWT authorizer             │
│   discoveryUrl = Cognito user pool with Federate OIDC IdP       │
│   custom-claim rule: cognito:groups CONTAINS_ANY [allow-list]   │
│   serves RFC 9728 PRM at .well-known/oauth-protected-resource   │
└─────────────────────┬───────────────────────────────────────────┘
                      │  forwards request + JWT in headers
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│ Companion-X (FastMCP, port 8000)                                │
│   middleware: extract Bearer → CognitoAuthBackend.verify        │
│              → set_envelope({principal_id: midway_login,        │
│                              tenant_id: group, ...})            │
│   bricks read get_principal_id() — unchanged                    │
└─────────────────────────────────────────────────────────────────┘
```

## Token Shape

A Federate-federated Cognito access token decoded:

```json
{
  "sub": "8e7b...uuid",
  "username": "FederateOIDC_wdaniero",
  "iss": "https://cognito-idp.us-east-1.amazonaws.com/<pool-id>",
  "client_id": "<companion-x-mcp-cli>",
  "scope": "openid profile email agentcore-runtime/invoke",
  "cognito:groups": ["project-delphi-webapp", "delphi-workstream-leads"],
  "identities": [{
    "userId": "wdaniero",
    "providerName": "FederateOIDC",
    "providerType": "OIDC"
  }]
}
```

`identities[0].userId` is the Midway login. That becomes `envelope.principal_id`.

## Track A — Native MCP OAuth (default; covers Kiro, Claude Code, direct API)

The MCP authorization spec (revisions 2025-06-18 and 2025-11-25) standardizes:
- Bearer token in HTTP `Authorization` header
- 401 + `WWW-Authenticate` with `resource_metadata` URL
- RFC 9728 Protected Resource Metadata at `.well-known/oauth-protected-resource`
- RFC 8707 audience binding
- PKCE-first authorization_code flow

AgentCore Runtime + Gateway already implement the server side when configured with a JWT authorizer.

**Cognito setup:**
- Public app client (no secret), `authorization_code` grant, PKCE required.
- Allowed identity providers: `FederateOIDC`.
- Callback URLs: `http://127.0.0.1:33418/callback` and similar loopback patterns the major clients use (Claude Code, Q CLI, `mcp-remote`). Adding `http://localhost:*/callback` is not standard — list specific ports per client.
- Allowed scopes: `openid email profile agentcore-runtime/invoke`.

**Client UX:**
1. User adds `Companion-X` to MCP config with one line: a URL.
2. First call → 401 + PRM URL in `WWW-Authenticate`.
3. Client fetches PRM, finds the Cognito hosted UI authorization endpoint.
4. Client opens browser → Federate sign-in → Cognito → loopback redirect with code.
5. Client exchanges code for tokens via PKCE (no secret needed).
6. Refresh token cached locally by the client.

**Reality check (today):**
- **Kiro**: native Streamable HTTP + dynamic client registration with browser-based OAuth — configure `{"url": "...", "headers": {...}}` in `.kiro/settings/mcp.json`, Kiro pops the sign-in browser, stores tokens. Confirmed in [kiro.dev blog 2025-10-31](https://kiro.dev/blog/introducing-remote-mcp/) and [docs/mcp/configuration](https://kiro.dev/docs/mcp/configuration).
- **Claude Code**: native remote HTTP MCP + OAuth.
- **Anthropic API "MCP connector"**: HTTP/SSE remote MCP servers (no stdio).
- **Q CLI**: support varies by build; verify.
- **Claude Desktop / older clients**: still stdio-only — these need the bridge.

Kiro, Claude Code, and direct-API users all use Track A today. Track B's audience is Claude Desktop and any other stdio-only client.

## Track B — Stdio Fallback Proxy (legacy clients only — Claude Desktop etc., NOT Kiro)

Existing `art-mcp-proxy` extended with `login` subcommand and per-user token storage.

**Replaces** the current shared `COGNITO_CLIENT_SECRET` config. The shared M2M client stays alive **only** for service-to-service test rigs (CI, scheduled jobs) under an explicit `--m2m` flag.

**Flow:**
1. `art-mcp-proxy login` → opens Cognito hosted UI with PKCE.
2. User signs in via Federate → loopback callback captures code.
3. Proxy exchanges code → access + refresh + ID tokens → writes `~/.art/credentials.json` (mode 0600).
4. Subsequent stdio runs read the file, send access token as Bearer, refresh on expiry.
5. On refresh failure → exit with: "run `art-mcp-proxy login` again".

**Same MCP config in the IDE as today**, just no shared secret in `env`:
```json
{
  "mcpServers": {
    "companion-x": {
      "command": "art-mcp-proxy",
      "env": { "GATEWAY_URL": "https://...gateway.bedrock-agentcore..." }
    }
  }
}
```

## Cognito + Federate CDK Wiring

The shape is already in `art-tracker/src/ArtTrackerCDK/lib/stacks/auth-stack.ts`. Mirror it in `art-platform/stacks/support/auth_stack.py`:

```python
self.federate_idp = cognito.UserPoolIdentityProviderOidc(
    self, "FederateOIDC",
    user_pool=self.user_pool,
    name="FederateOIDC",
    client_id=FEDERATE_CONFIG[stage].client_id,
    client_secret=cdk.SecretValue.secrets_manager(
        "/art/auth/federate-client-secret"
    ).unsafe_unwrap(),
    issuer_url=FEDERATE_CONFIG[stage].issuer_url,
    scopes=["openid"],
    attribute_mapping=cognito.AttributeMapping(
        email=cognito.ProviderAttribute.other("EMAIL"),
        given_name=cognito.ProviderAttribute.other("GIVEN_NAME"),
        family_name=cognito.ProviderAttribute.other("FAMILY_NAME"),
        preferred_username=cognito.ProviderAttribute.other("sub"),
    ),
)

# Public client for IDE MCP clients (PKCE, no secret)
self.cli_client = self.user_pool.add_client(
    "MCPCLIClient",
    user_pool_client_name=f"{RESOURCE_PREFIX}-mcp-cli",
    generate_secret=False,
    o_auth=cognito.OAuthSettings(
        flows=cognito.OAuthFlows(authorization_code_grant=True),
        scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL,
                cognito.OAuthScope.resource_server(self.resource_server,
                    self.invoke_scope)],
        callback_urls=[
            "http://127.0.0.1:33418/callback",     # mcp-remote default
            "http://localhost:33418/callback",
            # add other client-specific loopback URLs as needed
        ],
    ),
    supported_identity_providers=[
        cognito.UserPoolClientIdentityProvider.custom("FederateOIDC")
    ],
)
```

The existing M2M client stays for service-to-service.

## Gateway / Runtime JWT Authorizer Update

Update `art-platform/cdk.out/.../GatewayFA1BD5DB.template.json`'s `CustomJWTAuthorizer`:

```json
{
  "AllowedClients": [<m2m-client-id>, <mcp-cli-client-id>],
  "DiscoveryUrl": "https://cognito-idp.<region>.amazonaws.com/<pool-id>/.well-known/openid-configuration",
  "RequiredCustomClaims": [{
    "InboundTokenClaimName": "cognito:groups",
    "InboundTokenClaimValueType": "STRING_ARRAY",
    "AuthorizingClaimMatchValue": {
      "ClaimMatchValue": ["project-delphi-webapp", "autosec-model-experiment", "delphi-workstream-leads"],
      "ClaimMatchOperator": "CONTAINS_ANY"
    }
  }]
}
```

LDAP gating now lives at the gateway tier — bricks see only authorized callers.

## Auth Adapter Change (small)

`components/auth/src/factory/auth/runtime/adapters/aws.py::CognitoAuthBackend.verify_access_token`:

```python
# After existing claim validation:
identities = claims.get("identities", [])
midway_login = identities[0].get("userId") if identities else None

return {"ok": True, "claims": claims, "principal": {
    "subject": midway_login or claims.get("sub"),     # prefer Midway login
    "cognito_sub": claims.get("sub"),                  # keep the UUID for joins
    "username": claims.get("username"),
    "groups": claims.get("cognito:groups", []),
    "scopes": claims.get("scope", "").split(),
}}
```

`bases/api/src/factory/api/runtime/bridge.py::_extract_envelope` updates the envelope shape:

```python
return {
    "principal_id": result["principal"]["subject"],
    "tenant_id": (result["principal"]["groups"] or [None])[0],
    "groups": result["principal"]["groups"],
    "cognito_sub": result["principal"]["cognito_sub"],
}
```

The MCP path (`bases/mcp_server/src/factory/mcp_server/runtime/http_routes.py`) does the same — that file already has `_extract_envelope`; just align it with the bridge.

## Files Created / Changed

| File | Change |
|------|--------|
| `art-platform/stacks/support/auth_stack.py` | Add `UserPoolIdentityProviderOidc` + public PKCE client + RequiredCustomClaims |
| `art-platform/stacks/agents/gateway_stack.py` (or wherever the gateway is created) | Update authorizer's `AllowedClients` + `RequiredCustomClaims` |
| `components/auth/src/factory/auth/runtime/adapters/aws.py` | Surface `cognito:groups` and `identities[0].userId` |
| `bases/api/src/factory/api/runtime/bridge.py` | Map richer claims into envelope |
| `bases/mcp_server/src/factory/mcp_server/runtime/http_routes.py` | Same envelope mapping for MCP path |
| `iphled-mcp/proxy/art_mcp_proxy.py` | Add `login` subcommand + `~/.art/credentials.json` + refresh logic |

## Files NOT Changed

| File | Why |
|------|-----|
| Any brick except `auth` | Bricks already consume `get_principal_id()` |
| `projects/companion_x/main.py` | Just a Streamable HTTP server — middleware lives in the api/mcp_server bases |
| `frontends/next-dashboard/` | Already speaks NextAuth → Cognito → Federate via the art-tracker pattern |

## Open Questions

1. Single Cognito pool or two? `art-platform` has `art-companion-x` pool with M2M-only auto-created at gateway creation. Cleanest is to **delete the auto-created pool**, point the gateway authorizer at the Federate-enabled pool that already exists (`iphled-webapp-cognito-v2` pattern), and add the M2M client there. Reduces pools to one per stage.
2. Direct Federate vs. Cognito-fronted: pointing the JWT authorizer at Federate's discovery URL skips Cognito entirely, but loses Cognito's user attribute mapping and group claim. Defer; Cognito-fronted is the path.
3. Token caching for the dashboard server-side: when the Next.js dashboard forwards a session JWT, NextAuth currently issues its own opaque session — confirm we forward the Cognito access token (`account.access_token` callback) and not the NextAuth opaque session ID.

## References

- AgentCore inbound JWT: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html
- AgentCore inbound + outbound: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- MCP authorization spec: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- RFC 9728 Protected Resource Metadata: https://datatracker.ietf.org/doc/html/rfc9728
- RFC 8707 audience binding: https://datatracker.ietf.org/doc/html/rfc8707
- art-tracker reference (Federate IdP CDK): `~/workplace/art-tracker/src/ArtTrackerCDK/lib/stacks/auth-stack.ts`
- iphled-mcp reference (current proxy): `~/workplace/iphled-mcp/proxy/art_mcp_proxy.py`
