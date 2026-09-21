import { describe, expect, it } from "vitest";

import { safeRedirect } from "@/lib/utils";

describe("safeRedirect (open-redirect guard)", () => {
  it("allows same-site relative paths, including query strings", () => {
    expect(safeRedirect("/dashboard")).toBe("/dashboard");
    expect(safeRedirect("/problems/two-sum?tab=editorial")).toBe("/problems/two-sum?tab=editorial");
  });

  it.each([
    ["absolute URL", "https://evil.example/phish"],
    ["protocol-relative URL", "//evil.example"],
    ["backslash trick", "/\\evil.example"],
    ["javascript: URL", "javascript:alert(1)"],
    ["relative without slash", "dashboard"],
    ["empty string", ""],
  ])("rejects %s", (_label, target) => {
    expect(safeRedirect(target)).toBe("/dashboard");
  });

  it("falls back for null/undefined and honours a custom fallback", () => {
    expect(safeRedirect(null)).toBe("/dashboard");
    expect(safeRedirect(undefined, "/home")).toBe("/home");
  });
});
