import { describe, expect, it } from "vitest";

import { describeUserAgent, timeAgo } from "@/lib/format";

describe("describeUserAgent", () => {
  it.each([
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Chrome on Windows",
    ],
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15", "Safari on macOS"],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0", "Firefox on Linux"],
    [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 Edg/126.0",
      "Edge on Windows",
    ],
  ])("summarises %#", (ua, expected) => {
    expect(describeUserAgent(ua)).toBe(expected);
  });

  it("handles missing or unrecognised agents", () => {
    expect(describeUserAgent(null)).toBe("Unknown device");
    expect(describeUserAgent("curl/8.0")).toBe("Unknown device");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-09-21T12:00:00Z");
  it("formats past times relatively", () => {
    expect(timeAgo("2026-09-21T11:55:00Z", now)).toBe("5 minutes ago");
    expect(timeAgo("2026-09-21T09:00:00Z", now)).toBe("3 hours ago");
    expect(timeAgo("2026-09-20T12:00:00Z", now)).toBe("yesterday");
  });
  it("says 'just now' for very recent times", () => {
    expect(timeAgo("2026-09-21T11:59:40Z", now)).toBe("just now");
  });
});
