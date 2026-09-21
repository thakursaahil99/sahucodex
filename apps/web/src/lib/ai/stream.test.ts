import { beforeEach, describe, expect, it, vi } from "vitest";

import { streamAi } from "@/lib/ai/stream";
import type { StreamEvent } from "@/lib/ai/types";
import { isApiError } from "@/lib/api/http";
import { useAuthStore } from "@/lib/auth/store";

const refreshSession = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth/session", () => ({ refreshSession }));

const encoder = new TextEncoder();

function sseResponse(chunks: Array<string | Uint8Array>): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function jsonError(status: number, code: string, message: string, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ success: false, error: { code, message } }), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  refreshSession.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  useAuthStore.setState({ accessToken: "tok", status: "authenticated" });
});

async function run(): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  await streamAi("/ai/conversations", { message: "hi" }, (event) => events.push(event));
  return events;
}

describe("streamAi", () => {
  it("delivers events as chunks arrive and sends the bearer token", async () => {
    fetchMock.mockResolvedValue(
      sseResponse([
        'event: start\ndata: {"conversation_id":"c1"}\n\nevent: tok',
        'en\ndata: {"content":"Hel"}\n\nevent: token\ndata: {"content":"lo"}\n\n',
        "event: done\ndata: {}\n\n",
      ]),
    );
    const events = await run();
    expect(events.map((e) => e.type)).toEqual(["start", "token", "token", "done"]);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/ai/conversations");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
    expect(JSON.parse(init.body as string)).toEqual({ message: "hi" });
  });

  it("does not split a multi-byte character that straddles two network chunks", async () => {
    const bytes = encoder.encode('event: token\ndata: {"content":"✓"}\n\n');
    const cut = bytes.indexOf(0xe2) + 1; // inside the 3-byte ✓
    fetchMock.mockResolvedValue(sseResponse([bytes.slice(0, cut), bytes.slice(cut)]));
    expect(await run()).toEqual([{ type: "token", content: "✓" }]);
  });

  it.each([
    [503, "AI_UNAVAILABLE", "SahuCodeX AI is not configured"],
    [422, "AI_INPUT_TOO_LARGE", "Message is limited"],
    [404, "CONVERSATION_NOT_FOUND", "Conversation not found"],
  ])("rejects a %i before the stream starts with the server's own error", async (status, code, message) => {
    fetchMock.mockResolvedValue(jsonError(status, code, message));
    const error = await run().catch((e: unknown) => e);
    expect(isApiError(error) && [error.status, error.code, error.message]).toEqual([status, code, message]);
  });

  it("carries a 429's Retry-After so the UI can say when to come back", async () => {
    fetchMock.mockResolvedValue(jsonError(429, "RATE_LIMITED", "Slow down", { "Retry-After": "120" }));
    const error = await run().catch((e: unknown) => e);
    expect(isApiError(error) && error.retryAfter).toBe(120);
  });

  it("refreshes an expired session once and retries", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonError(401, "TOKEN_EXPIRED", "expired"))
      .mockResolvedValueOnce(sseResponse(["event: done\ndata: {}\n\n"]));
    refreshSession.mockImplementation(async () => {
      useAuthStore.setState({ accessToken: "fresh" });
      return true;
    });
    expect(await run()).toEqual([{ type: "done" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const retry = fetchMock.mock.calls[1] as [string, RequestInit];
    expect((retry[1].headers as Record<string, string>).Authorization).toBe("Bearer fresh");
  });

  it("gives up with the 401 when the session cannot be refreshed", async () => {
    fetchMock.mockResolvedValue(jsonError(401, "TOKEN_EXPIRED", "expired"));
    refreshSession.mockResolvedValue(false);
    const error = await run().catch((e: unknown) => e);
    expect(isApiError(error) && error.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports an unreachable API as a NETWORK_ERROR, not a crash", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const error = await run().catch((e: unknown) => e);
    expect(isApiError(error) && error.code).toBe("NETWORK_ERROR");
  });

  it("propagates a user abort untouched", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementation(async () => {
      controller.abort();
      throw new DOMException("aborted", "AbortError");
    });
    await expect(streamAi("/ai/conversations", {}, () => {}, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });
});
