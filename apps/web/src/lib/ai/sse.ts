import type { StreamEvent } from "@/lib/ai/types";

function toEvent(name: string, data: string): StreamEvent | null {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null; // a malformed frame is dropped, never rendered
  }
  switch (name) {
    case "start":
      return typeof payload.conversation_id === "string"
        ? { type: "start", conversationId: payload.conversation_id }
        : null;
    case "token":
      return typeof payload.content === "string" ? { type: "token", content: payload.content } : null;
    case "done":
      return { type: "done" };
    case "error":
      return {
        type: "error",
        code: typeof payload.code === "string" ? payload.code : "AI_UNAVAILABLE",
        message: typeof payload.message === "string" ? payload.message : "SahuCodeX AI stopped responding.",
      };
    default:
      return null;
  }
}

/**
 * Incremental Server-Sent Events parser. Network chunks split frames anywhere (even mid-UTF-8 sequence, which
 * `TextDecoder` with `stream: true` handles before we get here), so text is buffered until a blank line ends a frame.
 */
export function createSseParser(onEvent: (event: StreamEvent) => void): (chunk: string) => void {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let name = "message";
      const data: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      const event = toEvent(name, data.join("\n"));
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  };
}
