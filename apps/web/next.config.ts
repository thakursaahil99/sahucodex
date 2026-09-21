import type { NextConfig } from "next";

/** Set HTTPS_ONLY=true when the site is served over TLS (HSTS is meaningless, and can hurt, over plain HTTP). */
const httpsOnly = process.env.HTTPS_ONLY === "true";

/**
 * Local development convenience only. With `npm run dev` the browser talks to this origin and
 * `/api/*` is proxied to FastAPI, keeping cookies same-origin (no CORS).
 *
 * In docker compose and production, Caddy sits in front and routes /api/* straight to FastAPI
 * instead (infrastructure/docker/Caddyfile). Do NOT rely on this rewrite in production: it does not
 * append the client address to X-Forwarded-For, so the API could not tell users apart.
 */
const API_INTERNAL_URL = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Lets a second build (e.g. an end-to-end test stack) live beside a running `next dev` without clobbering it.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@sahucodex/shared"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_INTERNAL_URL}/api/:path*` }];
  },
  async headers() {
    // The Content-Security-Policy (which needs a per-request nonce) is set in src/proxy.ts.
    // /api/* is excluded: FastAPI sets its own headers, and two CSPs would both be enforced.
    return [
      {
        source: "/((?!api/).*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          ...(httpsOnly
            ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
            : []),
        ],
      },
    ];
  },
};

export default nextConfig;
