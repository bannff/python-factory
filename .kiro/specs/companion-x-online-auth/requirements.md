# Requirements: Companion-X Online Auth

## Introduction

Companion-X today runs locally and is invoked by IDEs (Kiro, Claude Code, Q CLI) over stdio. The online deployment path uses an AgentCore Gateway with a `CUSTOM_JWT` authorizer backed by Cognito, but the only configured client is a single shared M2M `client_credentials` app — every researcher looks identical to the gateway and to the bricks.

This spec turns Companion-X into an internal-employee platform where each invocation is bound to the calling Amazon employee's identity (Midway login), gated by Federate enrollment, and propagated through the brick envelope so authorization, audit, and RBAC work end-to-end. It also removes the local stdio→HTTP proxy whenever the IDE supports the MCP authorization spec natively.

## Related

- Existing online proof-of-concept: `iphled-mcp/` (proxy + Cognito M2M, single shared secret)
- Live infra: `art-platform` repo — `stacks/support/auth_stack.py` and `cdk.out/.../GatewayFA1BD5DB.template.json` define the current pool + JWT authorizer
- Existing Federate→Cognito federation pattern: `art-tracker/src/ArtTrackerCDK/lib/stacks/auth-stack.ts` — `UserPoolIdentityProviderOidc(name='FederateOIDC', issuerUrl=FEDERATE_CONFIG[stage].issuerUrl)`
- Federate profile already enrolled with Midway discovery + LDAP allow-list: `iphled-webapp-cognito-v2`
- Brick envelope plumbing: `bases/api/src/factory/api/runtime/bridge.py` and `bases/mcp_server/src/factory/mcp_server/runtime/{http_routes,progressive,instrumentation}.py`
- AgentCore inbound JWT authorizer: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/inbound-jwt-authorizer.html
- AgentCore inbound + outbound auth flows: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
- MCP authorization spec (2025-06-18 / 2025-11-25, RFC 9728 PRM, RFC 8707 audience binding): https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

## Existing Code References

- #[[file:components/auth/src/factory/auth/runtime/adapters/aws.py]] — CognitoAuthBackend already verifies RS256 against JWKS, populates `principal.subject` from `sub`. Needs to also surface `cognito:groups` and `identities[0].userId` for Federate-federated tokens.
- #[[file:bases/api/src/factory/api/runtime/bridge.py]] — `_extract_envelope` reads Bearer header, calls `auth_verify_access_token`, sets envelope contextvar. Already correct shape; just needs to fire on the AgentCore-mounted FastMCP path.
- #[[file:projects/companion_x/main.py]] — AgentCore entrypoint. Streamable HTTP on 8000.

## Requirements

### Requirement 1: Per-User JWT Inbound Auth

**User Story:** As an Amazon employee with Midway, I want my AgentCore-hosted Companion-X invocation to be authorized as me, so that audit logs, memory entries, and RBAC reflect my identity, not a shared M2M client.

#### Acceptance Criteria

1. THE AgentCore Runtime AND Gateway SHALL be configured with `CustomJWTAuthorizerConfiguration` whose `discoveryUrl` points at a Cognito User Pool that has a Federate OIDC IdP attached.
2. THE Cognito User Pool SHALL have a `UserPoolIdentityProviderOidc` configured with the Midway/Federate `issuerUrl` and the appropriate per-stage Federate `clientId`/`clientSecret`.
3. THE Cognito user pool client used for inbound auth SHALL support `authorization_code` grant with PKCE, and SHALL list `FederateOIDC` in `supportedIdentityProviders`.
4. THE JWT authorizer SHALL enforce a custom-claim rule that requires `cognito:groups` to contain at least one entry from a configured allow-list (mirrors the Federate-portal LDAP gating).
5. THE shared M2M `client_credentials` client SHALL still exist for service-to-service calls but SHALL be scoped via IAM `bedrock-agentcore:InvokeAgentRuntime` (NOT `InvokeAgentRuntimeForUser`) so it cannot impersonate end users.

### Requirement 2: Caller Identity in Brick Envelope

**User Story:** As a brick author, I want `get_principal_id()` to return the authenticated Midway login of the caller so I can persist findings, memory, and audit events keyed by user.

#### Acceptance Criteria

1. WHEN the AgentCore runtime forwards an inbound MCP request, THE `factory.auth.aws.CognitoAuthBackend.verify_access_token` SHALL return claims including `sub`, `username`, `cognito:groups`, and `identities[0].userId` (the Midway login).
2. THE envelope set by `bases/api/.../bridge.py::_extract_envelope` SHALL populate `principal_id` with the Midway login (preferring `identities[0].userId` over `sub` when present), and SHALL populate `tenant_id` from a configurable claim (default: first matching group).
3. THE FastMCP path mounted by `projects/companion_x/main.py` SHALL run the same Bearer-extraction middleware as the REST gateway, so MCP-protocol invocations propagate envelope identically.
4. THE telemetry sink SHALL record `principal_id` on every `ToolInvocation` graph node.
5. NO BRICK SHALL be modified — they already consume `get_principal_id()` from `factory.mcp_utils.interface`.

### Requirement 3: Native MCP OAuth — No Proxy for Kiro / Claude Code / Direct API

**User Story:** As an employee using Kiro (or any MCP-spec-compliant client), I want to add Companion-X by URL only, sign in once via the browser, and have zero local proxy involved.

#### Acceptance Criteria

1. THE AgentCore Gateway / Runtime endpoint SHALL serve RFC 9728 Protected Resource Metadata at the standard `.well-known/oauth-protected-resource` URL (AgentCore does this automatically when JWT authorizer is configured).
2. THE Cognito User Pool client used by IDE MCP clients SHALL be a **public** client (`generateSecret: false`) configured for `authorization_code` grant with PKCE, with redirect URIs that cover the loopback callback patterns used by Kiro, Claude Code, Q CLI, and `mcp-remote`.
3. WHEN connecting from Kiro, THE configuration SHALL be a single block in `.kiro/settings/mcp.json` of the form `{"url": "<gateway-url>", "headers": {...}}` — Kiro performs dynamic client registration and browser-based OAuth, then stores tokens locally.
4. WHEN connecting from any other native HTTP MCP client (Claude Code, direct API), THE same Cognito client SHALL serve them — one PKCE client covers all native paths.
5. WHEN connecting from a stdio-only legacy client (e.g. Claude Desktop), THE existing `art-mcp-proxy` SHALL remain as a fallback, retrofitted to use a per-user token (Track B in the design).
6. DOCUMENTATION SHALL list which clients use which path, with Kiro and Claude Code explicitly in Track A.

### Requirement 4: Token Acquisition for Stdio Fallback

**User Story:** As a researcher on a stdio-only client, I want a one-command login that gives the proxy a per-user token, so my MCP calls carry my identity even when the IDE can't speak OAuth.

#### Acceptance Criteria

1. THE proxy SHALL read its bearer token from `~/.art/credentials.json` (path overridable via env).
2. THE proxy SHALL provide `art-mcp-proxy login` that opens a browser to the Cognito hosted UI (Federate IdP), captures the authorization code via loopback redirect, exchanges it for tokens with PKCE, and writes the result to `~/.art/credentials.json`.
3. THE proxy SHALL refresh the access token automatically using the stored refresh token.
4. WHEN the refresh token is expired or revoked, THE proxy SHALL exit with a clear "run `art-mcp-proxy login` again" message — NOT silently fail.
5. THE old shared `client_credentials` flow SHALL remain available behind an explicit `--m2m` flag for service-to-service test rigs, but SHALL warn that it is not bound to a user identity.

### Requirement 5: Online/Local Parity

**User Story:** As a developer, I want the same Companion-X codebase to run locally (no auth) and online (Federate auth) so I don't maintain two builds.

#### Acceptance Criteria

1. WHEN `RUN_MODE=local` (the existing local stack), THE Bearer extraction middleware SHALL no-op — `get_principal_id()` returns `"kiro-agent"` as today, no Federate dependency.
2. WHEN `RUN_MODE=agentcore`, THE middleware SHALL require a valid Bearer and reject requests without one (403).
3. THE switch SHALL be driven by env var only — no code branching at the brick layer.
4. THE Companion-X Next.js dashboard (online deployment) SHALL re-use the existing NextAuth → Cognito → Federate pattern from `art-tracker`. When the user invokes a tool from the dashboard, the dashboard's session JWT is forwarded as the Bearer to the runtime.

### Requirement 6: Audit and Authorization Hooks

**User Story:** As security/compliance, I want every Companion-X invocation traceable to a Midway login and gated by group membership.

#### Acceptance Criteria

1. EACH invocation SHALL emit an audit log line via `logger` brick containing `{principal_id, tool_name, brick_name, timestamp, request_id}`.
2. THE permissions brick SHALL be wired so an authoring tool's policy can reference `envelope.principal_id` and `envelope.groups` for Cedar/AVP evaluation.
3. THE deny-by-default policy at the gateway tier (custom-claim allow-list of LDAP groups) SHALL be the first line of defense; brick-level permissions SHALL be the second.
