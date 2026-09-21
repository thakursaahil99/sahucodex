import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useJudgeSocket } from "@/lib/submissions/socket";

const getWsTicket = vi.fn();
vi.mock("@/lib/submissions/api", () => ({ getWsTicket: (...args: unknown[]) => getWsTicket(...args) }));

class FakeSocket {
  static instances: FakeSocket[] = [];
  url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  getWsTicket.mockReset().mockResolvedValue({ ticket: "the-ticket", expires_in: 30 });
  vi.stubGlobal("WebSocket", FakeSocket as unknown as typeof WebSocket);
  vi.stubGlobal("location", { protocol: "https:", host: "sahucodex.example" });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("useJudgeSocket", () => {
  it("does nothing while disabled", () => {
    renderHook(() => useJudgeSocket(vi.fn(), false));
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("connects with the ticket in the URL and reports 'open' once connected", async () => {
    const { result } = renderHook(() => useJudgeSocket(vi.fn()));
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    expect(FakeSocket.instances[0]!.url).toBe("wss://sahucodex.example/api/ws?ticket=the-ticket");

    act(() => FakeSocket.instances[0]!.onopen?.());
    expect(result.current).toBe("open");
  });

  it("forwards parsed messages to the latest handler", async () => {
    const first = vi.fn();
    const { result, rerender } = renderHook(({ handler }) => useJudgeSocket(handler), { initialProps: { handler: first } });
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    act(() => FakeSocket.instances[0]!.onopen?.());

    const second = vi.fn();
    rerender({ handler: second });

    const event = { type: "submission.completed", data: { submission_id: "abc" }, ts: "2026-01-01T00:00:00Z" };
    act(() => FakeSocket.instances[0]!.onmessage?.({ data: JSON.stringify(event) }));

    expect(second).toHaveBeenCalledWith(event);
    expect(first).not.toHaveBeenCalled(); // the effect that keeps the ref current already re-ran before the message
    expect(result.current).toBe("open");
  });

  it("drops a malformed frame instead of throwing", async () => {
    const onEvent = vi.fn();
    renderHook(() => useJudgeSocket(onEvent));
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    expect(() => act(() => FakeSocket.instances[0]!.onmessage?.({ data: "not json" }))).not.toThrow();
    expect(onEvent).not.toHaveBeenCalled();
  });

  it("becomes unavailable if a ticket can never be minted", async () => {
    getWsTicket.mockReset().mockRejectedValue(new Error("not signed in"));
    const { result } = renderHook(() => useJudgeSocket(vi.fn()));
    await waitFor(() => expect(result.current).toBe("unavailable"));
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("becomes unavailable, without ever opening, when the socket errors before connecting", async () => {
    const { result } = renderHook(() => useJudgeSocket(vi.fn()));
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    act(() => FakeSocket.instances[0]!.close());
    await waitFor(() => expect(result.current).toBe("unavailable"));
  });

  it("closes the socket on unmount", async () => {
    const { unmount } = renderHook(() => useJudgeSocket(vi.fn()));
    await waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    act(() => FakeSocket.instances[0]!.onopen?.());
    unmount();
    expect(FakeSocket.instances[0]!.closed).toBe(true);
  });

  it("reconnects with backoff after repeated drops, and eventually gives up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { result } = renderHook(() => useJudgeSocket(vi.fn()));
    await vi.waitFor(() => expect(FakeSocket.instances).toHaveLength(1));
    // The only successful open in this test — every reconnect attempt below fails without ever opening, so the
    // retry counter (reset on each successful open) climbs instead of resetting, the way a real outage would.
    act(() => FakeSocket.instances[0]!.onopen?.());
    expect(result.current).toBe("open");

    // Five closes, each followed by one more scheduled reconnect attempt with growing, capped backoff.
    for (let round = 0; round < 5; round += 1) {
      const before = FakeSocket.instances.length;
      act(() => FakeSocket.instances.at(-1)!.close());
      await vi.advanceTimersByTimeAsync(15_000);
      await vi.waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(before));
    }
    expect(FakeSocket.instances).toHaveLength(6); // 1 initial connection + 5 reconnect attempts
    expect(result.current).toBe("open"); // stale from the one real open; nothing has set it since

    // The sixth close is past MAX_RECONNECTS: it gives up instead of scheduling a seventh attempt.
    act(() => FakeSocket.instances.at(-1)!.close());
    await vi.waitFor(() => expect(result.current).toBe("unavailable"));
    const finalCount = FakeSocket.instances.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(FakeSocket.instances).toHaveLength(finalCount);
  });
});
