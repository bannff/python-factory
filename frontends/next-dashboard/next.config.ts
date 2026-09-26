import type { NextConfig } from "next";
import path from "node:path";
import { buildSecurityHeaders } from "./lib/security/csp";

const SPA_VIEWS = ["graph", "timeline", "findings", "evals", "metrics", "ml"];

/**
 * Next.js host config.
 *
 * - `redirects()` collapses legacy SPA paths onto `/`.
 * - `headers()` ships companion security headers. CSP is generated once per
 *   document request by `middleware.ts`, which injects a nonce and forwards it
 *   to the App Router.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@companion-x/shared-renderer"],
  // Next copies this value into `outputFileTracingRoot`, so it decides the
  // standalone layout. Anchor it on the directory holding both this app and the
  // linked `../shared-renderer` package, via `__dirname` rather than
  // `process.cwd()`, so the emitted layout (`.next/standalone/next-dashboard/`)
  // is identical locally and under the Docker builder's `/app/next-dashboard`.
  turbopack: { root: path.resolve(__dirname, "..") },
  async redirects() {
    return SPA_VIEWS.map((v) => ({
      source: `/${v}`,
      destination: "/",
      permanent: false,
    }));
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: buildSecurityHeaders(),
      },
    ];
  },
};

export default nextConfig;
