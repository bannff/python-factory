import type { NextConfig } from "next";
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
