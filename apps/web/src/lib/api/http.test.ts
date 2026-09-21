import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, fieldErrors, http, isApiError } from "@/lib/api/http";
import { apiError, jsonResponse, mockFetch } from "@/test-utils";

afterEach(() => vi.unstubAllGlobals());

describe("http", () => {
  it("returns parsed JSON and sends the bearer token and JSON body", async () => {
    const fetchMock = mockFetch().mockResolvedValue(jsonResponse(200, { ok: true }));
    const result = await http<{ ok: boolean }>("/things", { method: "POST", body: { a: 1 }, token: "tok" });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/things");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"a":1}');
    expect(init?.credentials).toBe("same-origin");
    expect(init?.headers).toMatchObject({ Authorization: "Bearer tok", "Content-Type": "application/json" });
  });

  it("returns undefined for 204 No Content", async () => {
    mockFetch().mockResolvedValue(new Response(null, { status: 204 }));
    await expect(http("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("does not send an Authorization header without a token", async () => {
    const fetchMock = mockFetch().mockResolvedValue(jsonResponse(200, {}));
    await http("/health");
    expect(fetchMock.mock.calls[0]![1]?.headers).not.toHaveProperty("Authorization");
  });

  it("turns the API error envelope into an ApiError", async () => {
    mockFetch().mockResolvedValue(apiError(409, "EMAIL_TAKEN", "An account with that email already exists"));
    const error = await http("/auth/register", { method: "POST", body: {} }).catch((e) => e);

    expect(isApiError(error)).toBe(true);
    expect(error).toMatchObject({ status: 409, code: "EMAIL_TAKEN", message: "An account with that email already exists" });
  });

  it("captures Retry-After from rate-limit responses", async () => {
    mockFetch().mockResolvedValue(apiError(429, "RATE_LIMITED", "Slow down", { "Retry-After": "42" }));
    const error = (await http("/auth/login", { method: "POST" }).catch((e) => e)) as ApiError;
    expect(error.retryAfter).toBe(42);
  });

  it("copes with non-JSON error bodies (e.g. a proxy 502)", async () => {
    mockFetch().mockResolvedValue(new Response("Bad Gateway", { status: 502 }));
    const error = (await http("/anything").catch((e) => e)) as ApiError;
    expect(error).toMatchObject({ status: 502, code: "HTTP_ERROR" });
  });

  it("reports network failures with a stable code", async () => {
    mockFetch().mockRejectedValue(new TypeError("Failed to fetch"));
    const error = (await http("/anything").catch((e) => e)) as ApiError;
    expect(error).toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });

  it("rethrows aborts untouched", async () => {
    const controller = new AbortController();
    controller.abort();
    mockFetch().mockRejectedValue(new DOMException("Aborted", "AbortError"));
    await expect(http("/anything", { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("fieldErrors", () => {
  it("keeps the first message per field", () => {
    const error = new ApiError(422, "VALIDATION_ERROR", "bad", [
      { field: "email", message: "Invalid email", type: "value_error" },
      { field: "email", message: "Second", type: "x" },
      { field: "password", message: "Too short", type: "string_too_short" },
    ]);
    expect(fieldErrors(error)).toEqual({ email: "Invalid email", password: "Too short" });
  });
});
