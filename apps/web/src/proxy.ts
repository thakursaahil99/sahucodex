import { NextResponse, type NextRequest } from "next/server";

/** Non-secret "you look signed in" flag set by the API next to the httpOnly refresh cookie. */
const SESSION_HINT_COOKIE = "sahucodex_session";

const PROTECTED_PREFIXES = ["/dashboard", "/settings", "/admin", "/submissions", "/ai"];
const GUEST_ONLY_PATHS = ["/login", "/register"];

const isProd = process.env.NODE_ENV === "production";
const httpsOnly = process.env.HTTPS_ONLY === "true";

function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    // 'strict-dynamic' lets the nonce'd bootstrap script load Next's chunks; no inline script runs without it.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isProd ? "" : " 'unsafe-eval'"}`,
    "style-src 'self' 'unsafe-inline'", // Radix/Tailwind set inline style attributes
    // https: (any host) is for user-set avatar URLs (profiles, phase 4) — images cannot execute script, so this
    // is the standard, low-risk way to allow them without a proxy or a per-host allow-list.
    "img-src 'self' blob: data: https:",
    "font-src 'self' data:", // Monaco inlines its icon font as a data: URI
    `connect-src 'self'${isProd ? "" : " ws: wss:"}`,
    "worker-src 'self' blob:", // Monaco Editor runs its language services in blob workers
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  // Only over TLS: on plain http://localhost this would make browsers try https:// for every asset.
  if (httpsOnly) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * Runs before every page request. It (1) sends users without a session hint to /login and signed-in
 * users away from /login, purely as a UX shortcut — the API re-verifies every call — and
 * (2) attaches a nonce-based Content-Security-Policy.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = request.cookies.get(SESSION_HINT_COOKIE)?.value === "1";

  if (matches(pathname, PROTECTED_PREFIXES) && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  if (matches(pathname, GUEST_ONLY_PATHS) && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    url.search = "";
    return NextResponse.redirect(url);
  }

  const nonce = btoa(crypto.randomUUID());
  const csp = buildCsp(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Skip the API proxy, Next internals and static files. Prefetches don't need a nonce.
      source: "/((?!api/|_next/static|_next/image|favicon.ico|icon.svg|healthz).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
