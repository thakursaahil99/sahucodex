import { describe, expect, it } from "vitest";

import { createSseParser } from "@/lib/ai/sse";
import type { StreamEvent } from "@/lib/ai/types";

function collect() {
  const events: StreamEvent[] = [];
  return { events, push: createSseParser((event) => events.push(event)) };
}

const frame = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;

describe("createSseParser", () => {
  it("parses the four event types the server sends", () => {
    const { events, push } = collect();
    push(
      frame("start", { conversation_id: "c1" }) +
        frame("token", { content: "Hi" }) +
        frame("error", { code: "AI_UNAVAILABLE", message: "stopped" }) +
        frame("done", {}),
    );
    expect(events).toEqual([
      { type: "start", conversationId: "c1" },
      { type: "token", content: "Hi" },
      { type: "error", code: "AI_UNAVAILABLE", message: "stopped" },
      { type: "done" },
    ]);
  });

  it("reassembles a frame that the network split anywhere, even mid-field", () => {
    const { events, push } = collect();
    const whole = frame("token", { content: "hello world" });
    for (const piece of [whole.slice(0, 5), whole.slice(5, 22), whole.slice(22)]) push(piece);
    expect(events).toEqual([{ type: "token", content: "hello world" }]);
  });

  it("keeps multi-line and non-ASCII token content intact", () => {
    const { events, push } = collect();
    push(frame("token", { content: "line1\nline2 — ✓ 你好" }));
    expect(events).toEqual([{ type: "token", content: "line1\nline2 — ✓ 你好" }]);
  });

  it("accepts CRLF line endings", () => {
    const { events, push } = collect();
    push('event: token\r\ndata: {"content":"x"}\r\n\r\n');
    expect(events).toEqual([{ type: "token", content: "x" }]);
  });

  it("drops malformed, unknown and incomplete frames instead of rendering them", () => {
    const { events, push } = collect();
    push("event: token\ndata: {not json}\n\n");
    push(frame("mystery", { content: "ignored" }));
    push(frame("token", { content: 42 })); // wrong shape
    push(frame("start", {})); // missing id
    push('event: token\ndata: {"content":"pending"}'); // no terminating blank line yet
    expect(events).toEqual([]);
    push("\n\n");
    expect(events).toEqual([{ type: "token", content: "pending" }]);
  });

  it("falls back to a safe message when an error frame is vague", () => {
    const { events, push } = collect();
    push(frame("error", {}));
    expect(events).toEqual([{ type: "error", code: "AI_UNAVAILABLE", message: "SahuCodeX AI stopped responding." }]);
  });
});
