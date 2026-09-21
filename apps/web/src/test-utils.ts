import { vi } from "vitest";

import type { User } from "@/lib/api/types";

/** A fetch Response carrying JSON (or nothing, for 204). */
export function jsonResponse(status: number, body?: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function apiError(status: number, code: string, message = code, headers?: Record<string, string>): Response {
  return jsonResponse(status, { success: false, error: { code, message } }, headers);
}

export function mockFetch() {
  const fn = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const sampleUser: User = {
  id: "0b6f6d5e-4d1e-4d4e-8f4b-2f2f5f0f0001",
  email: "ada@example.com",
  username: "ada",
  roles: ["USER"],
  email_verified: false,
  created_at: "2026-09-01T10:00:00Z",
  profile: { avatar_url: null, bio: null, country: null, website: null, github_url: null },
};

export function tokenBody(overrides: Partial<{ access_token: string; expires_in: number }> = {}) {
  return { access_token: "access-1", token_type: "bearer", expires_in: 900, user: sampleUser, ...overrides };
}
