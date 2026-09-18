# Tasks: Companion-X Online Auth

- [ ] 1. Add Federate OIDC IdP to companion-x Cognito pool (CDK in art-platform)
  - Mirror `art-tracker` `UserPoolIdentityProviderOidc` shape
  - Use `/art/auth/federate-client-secret` from Secrets Manager
  - Per-stage `FEDERATE_CONFIG` (alpha/beta/prod)

- [ ] 2. Add public PKCE client for IDE MCP clients
  - `generateSecret: false`, `authorization_code` grant only
  - `supportedIdentityProviders=['FederateOIDC']`
  - Loopback callback URLs for Claude Code / Q CLI / mcp-remote

- [ ] 3. Update gateway/runtime JWT authorizer
  - `AllowedClients` includes both M2M and PKCE client IDs
  - `RequiredCustomClaims` enforces `cognito:groups CONTAINS_ANY [allow-list]`

- [ ] 4. Surface richer claims in `CognitoAuthBackend.verify_access_token`
  - Extract `cognito:groups`, `identities[0].userId`
  - Prefer Midway login as `principal.subject`, keep UUID as `cognito_sub`

- [ ] 5. Align envelope mapping in api + mcp_server bases
  - `bases/api/.../bridge.py::_extract_envelope`
  - `bases/mcp_server/.../http_routes.py::_extract_envelope`
  - Populate `principal_id`, `tenant_id`, `groups`, `cognito_sub`

- [ ] 6. Add `RUN_MODE` switch
  - `local` → middleware no-op, `principal_id="kiro-agent"` (today)
  - `agentcore` → require Bearer, 403 if missing

- [ ] 7. Retrofit `art-mcp-proxy` for per-user tokens — **legacy clients only (Claude Desktop, etc.)**
  - `art-mcp-proxy login` subcommand: PKCE + loopback + token write
  - Read from `~/.art/credentials.json` (mode 0600)
  - Refresh on expiry, fail loud on revoked refresh
  - Keep `--m2m` flag for service rigs only
  - Note: Kiro and Claude Code do NOT need this — they go via Track A

- [ ] 8. Verify native MCP OAuth path with Kiro and Claude Code
  - Add Companion-X by URL, sign in, run a tool
  - Confirm PRM is served at `.well-known/oauth-protected-resource`
  - Confirm Kiro's dynamic client registration completes against Cognito

- [ ] 9. Forward Cognito access token from Next.js dashboard
  - NextAuth `account.access_token` → API request `Authorization` header
  - End-to-end: dashboard click → brick sees `principal_id` = Midway login

- [ ] 10. Telemetry + audit
  - Confirm `principal_id` lands on `ToolInvocation` graph nodes
  - Logger brick emits per-invocation audit line with principal + tool

- [ ] 11. Docs
  - `.agents/recipes/auth-flow.md` updated with online path
  - `iphled-mcp/README.md` updated for `login` subcommand
  - Steering note on `RUN_MODE` and envelope shape change
