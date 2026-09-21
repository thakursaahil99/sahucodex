import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api/client";
import { login, logout, refreshSession, register } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";
import { apiError, jsonResponse, mockFetch, sampleUser, tokenBody } from "@/test-utils";

function resetStore() {
  useAuthStore.setState({ status: "loading", accessToken: null, expiresAt: null, user: null });
}

beforeEach(resetStore);
afterEach(() => vi.unstubAllGlobals());

const urlOf = (call: unknown[]) => call[0] as string;

describe("refreshSession", () => {
  it("stores the new session on success", async () => {
    mockFetch().mockResolvedValue(jsonResponse(200, tokenBody()));
    await expect(refreshSession()).resolves.toBe(true);

    const state = useAuthStore.getState();
    expect(state.status).toBe("authenticated");
    expect(state.accessToken).toBe("access-1");
    expect(state.user?.username).toBe("ada");
  });

  it("is single-flight: concurrent callers share one request (refresh tokens rotate!)", async () => {
    const fetchMock = mockFetch().mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(jsonResponse(200, tokenBody())), 20)),
    );
    const results = await Promise.all([refreshSession(), refreshSession(), refreshSession()]);

    expect(results).toEqual([true, true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("signs the user out locally when the server says the session is dead", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "old", user: sampleUser });
    mockFetch().mockResolvedValue(apiError(401, "REFRESH_TOKEN_REUSED"));

    await expect(refreshSession()).resolves.toBe(false);
    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", accessToken: null, user: null });
  });

  it("retries once when another tab won the rotation race, without logging out", async () => {
    const fetchMock = mockFetch()
      .mockResolvedValueOnce(apiError(401, "REFRESH_TOKEN_RACE"))
      .mockResolvedValueOnce(jsonResponse(200, tokenBody({ access_token: "access-2" })));

    await expect(refreshSession()).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(useAuthStore.getState().accessToken).toBe("access-2");
  });

  it("reports 'unavailable' (not logged out) when the API cannot be reached on first load", async () => {
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(refreshSession()).resolves.toBe(false);
    expect(useAuthStore.getState().status).toBe("unavailable");
  });

  it("keeps an existing session when a background refresh fails on a network error", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "still-good", user: sampleUser });
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(refreshSession()).resolves.toBe(false);
    expect(useAuthStore.getState()).toMatchObject({ status: "authenticated", accessToken: "still-good" });
  });
});

describe("login / register / logout", () => {
  it("login posts credentials and stores the session", async () => {
    const fetchMock = mockFetch().mockResolvedValue(jsonResponse(200, tokenBody()));
    await login("ada", "hunter2hunter2");

    expect(urlOf(fetchMock.mock.calls[0]!)).toBe("/api/auth/login");
    expect(JSON.parse(fetchMock.mock.calls[0]![1]!.body as string)).toEqual({
      identifier: "ada",
      password: "hunter2hunter2",
    });
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("register creates the account and then signs in", async () => {
    const fetchMock = mockFetch()
      .mockResolvedValueOnce(jsonResponse(201, { user: sampleUser }))
      .mockResolvedValueOnce(jsonResponse(200, tokenBody()));
    await register({ email: "ada@example.com", username: "ada", password: "correct-horse-battery" });

    expect(fetchMock.mock.calls.map(urlOf)).toEqual(["/api/auth/register", "/api/auth/login"]);
    expect(useAuthStore.getState().status).toBe("authenticated");
  });

  it("logout clears local state even if the server is unreachable", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "tok", user: sampleUser });
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));

    await logout();
    expect(useAuthStore.getState()).toMatchObject({ status: "anonymous", accessToken: null, user: null });
  });
});

describe("api (authenticated wrapper)", () => {
  it("attaches the in-memory access token", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "tok", user: sampleUser });
    const fetchMock = mockFetch().mockResolvedValue(jsonResponse(200, { hello: "world" }));

    await expect(api("/users/me")).resolves.toEqual({ hello: "world" });
    expect(fetchMock.mock.calls[0]![1]!.headers).toMatchObject({ Authorization: "Bearer tok" });
  });

  it("transparently refreshes an expired token and retries the request once", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "expired", user: sampleUser });
    const fetchMock = mockFetch()
      .mockResolvedValueOnce(apiError(401, "TOKEN_EXPIRED"))
      .mockResolvedValueOnce(jsonResponse(200, tokenBody({ access_token: "fresh" })))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await expect(api("/users/me")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls.map(urlOf)).toEqual(["/api/users/me", "/api/auth/refresh", "/api/users/me"]);
    expect(fetchMock.mock.calls[2]![1]!.headers).toMatchObject({ Authorization: "Bearer fresh" });
  });

  it("signs out locally when the server reports the session was revoked", async () => {
    useAuthStore.setState({ status: "authenticated", accessToken: "tok", user: sampleUser });
    mockFetch().mockResolvedValue(apiError(401, "TOKEN_REVOKED"));

    await expect(api("/users/me")).rejects.toMatchObject({ code: "TOKEN_REVOKED" });
    expect(useAuthStore.getState().status).toBe("anonymous");
  });

  it("tries to restore a session first when there is no access token yet", async () => {
    const fetchMock = mockFetch()
      .mockResolvedValueOnce(jsonResponse(200, tokenBody({ access_token: "restored" })))
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }));

    await expect(api("/users/me")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls.map(urlOf)).toEqual(["/api/auth/refresh", "/api/users/me"]);
  });

  it("fails with NOT_AUTHENTICATED when no session can be restored", async () => {
    mockFetch().mockResolvedValue(apiError(401, "REFRESH_TOKEN_MISSING"));
    await expect(api("/users/me")).rejects.toMatchObject({ status: 401, code: "NOT_AUTHENTICATED" });
  });
});
