import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { SdkErrorCode, SdkHttpError } from "@modelcontextprotocol/client";

import { localMcpAuthorizationHeaders, proxyLocalApi, proxyLocalMcp } from "@/lib/mcp-local-bff";
import {
  McpAuthenticationError, normalizeMcpConnectionError,
} from "@/lib/mcp-client";

function request(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest("http://localhost:3000/mcp", {
    method: "POST",
    headers: {
      host: "localhost:3000",
      origin: "http://localhost:3000",
      "sec-fetch-site": "same-origin",
      "content-type": "application/json",
      "x-companion-x-local": "1",
      ...headers,
    },
    body: "{}",
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("local MCP credential BFF", () => {
  it("injects only the server token and never forwards browser authority", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    vi.stubEnv("API_URL", "http://localhost:8000");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("ok", {
        status: 200,
        headers: { "content-type": "application/json", "set-cookie": "secret=bad" },
      }),
    );

    const response = await proxyLocalMcp(request({
      authorization: "Bearer browser-attacker",
      cookie: "credential=attacker",
      forwarded: "host=attacker.example",
      "x-forwarded-host": "attacker.example",
    }));

    expect(response.status).toBe(200);
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("authorization")).toBe("Bearer server-local-token-123456");
    expect(headers.get("cookie")).toBeNull();
    expect(headers.get("forwarded")).toBeNull();
    expect(headers.get("x-forwarded-host")).toBeNull();
    expect(init.redirect).toBe("manual");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("rejects cross-origin and unguarded requests before the upstream", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    const fetchMock = vi.spyOn(globalThis, "fetch");

    expect((await proxyLocalMcp(request({ origin: "https://attacker.example" }))).status)
      .toBe(403);
    expect((await proxyLocalMcp(request({ "x-companion-x-local": "" }))).status)
      .toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed when local auth is disabled or unconfigured", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "false");
    expect((await proxyLocalMcp(request())).status).toBe(401);

    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "short");
    expect((await proxyLocalMcp(request())).status).toBe(401);

    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "unsafe-token-with-newline\n1234");
    expect((await proxyLocalMcp(request())).status).toBe(401);
  });

  it("admits IPv6 loopback", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("ok"));
    const ipv6 = new NextRequest("http://[::1]:3000/mcp", {
      method: "POST",
      headers: {
        host: "[::1]:3000", origin: "http://[::1]:3000",
        "sec-fetch-site": "same-origin", "content-type": "application/json",
        "x-companion-x-local": "1",
      },
      body: "{}",
    });
    expect((await proxyLocalMcp(ipv6)).status).toBe(200);
  });

  it("admits only an exact owner-scoped Terminal completion path", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    vi.stubEnv("API_URL", "http://localhost:8000");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    const session = `term_${"a".repeat(32)}`;
    expect((await proxyLocalApi(request(), `/api/terminal/sessions/${session}/complete`)).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect((await proxyLocalApi(request(), "/api/terminal/sessions/not-a-session/complete")).status).toBe(404);
  });

  it("maps version-probe authentication failures to an actionable error", () => {
    const sdkError = new SdkHttpError(
      SdkErrorCode.ClientHttpAuthentication,
      "Version negotiation failed: HTTP 401",
      { status: 401, statusText: "Unauthorized", text: "" },
    );
    expect(normalizeMcpConnectionError(sdkError)).toBeInstanceOf(McpAuthenticationError);
    const other = new Error("offline");
    expect(normalizeMcpConnectionError(other)).toBe(other);
  });

  it("rejects credentialed redirects and hides upstream topology", async () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, { status: 307, headers: { location: "http://attacker/" } }),
    );
    const response = await proxyLocalMcp(request());
    expect(response.status).toBe(502);
    expect(await response.text()).not.toContain("attacker");
  });

  it("projects the validated server token into server-side AG-UI only", () => {
    vi.stubEnv("MCP_LOCAL_AUTH", "true");
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "server-local-token-123456");
    expect(localMcpAuthorizationHeaders()).toEqual({
      authorization: "Bearer server-local-token-123456",
    });
    vi.stubEnv("MCP_LOCAL_AUTH_TOKEN", "short");
    expect(localMcpAuthorizationHeaders()).toEqual({});
    vi.stubEnv("MCP_LOCAL_AUTH", "false");
    expect(localMcpAuthorizationHeaders()).toEqual({});
  });
});
