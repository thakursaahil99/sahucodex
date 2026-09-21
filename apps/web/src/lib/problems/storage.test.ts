import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  clampFont,
  clearDraft,
  DEFAULT_PREFS,
  loadDraft,
  loadLanguage,
  loadPrefs,
  normalizeWhitespace,
  saveDraft,
  saveLanguage,
  savePrefs,
} from "@/lib/problems/storage";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("drafts", () => {
  it("round-trips per problem and language", () => {
    expect(loadDraft("two-sum", "python")).toBeNull();
    expect(saveDraft("two-sum", "python", "print(1)")).toBe(true);
    saveDraft("two-sum", "cpp", "int main(){}");
    saveDraft("other", "python", "x = 1");

    expect(loadDraft("two-sum", "python")).toBe("print(1)");
    expect(loadDraft("two-sum", "cpp")).toBe("int main(){}");
    expect(loadDraft("other", "python")).toBe("x = 1");
  });

  it("clears one draft without touching the others", () => {
    saveDraft("a", "python", "1");
    saveDraft("a", "cpp", "2");
    clearDraft("a", "python");
    expect(loadDraft("a", "python")).toBeNull();
    expect(loadDraft("a", "cpp")).toBe("2");
  });

  it("keeps working when localStorage throws (private windows, blocked storage)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadDraft("a", "python")).toBeNull();
    expect(saveDraft("a", "python", "x")).toBe(false);
    expect(() => clearDraft("a", "python")).not.toThrow();
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
    expect(loadLanguage("a")).toBeNull();
  });

  it("remembers the last language per problem", () => {
    saveLanguage("a", "cpp");
    expect(loadLanguage("a")).toBe("cpp");
    expect(loadLanguage("b")).toBeNull();
  });
});

describe("editor preferences", () => {
  it("defaults when nothing is stored", () => {
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);
  });

  it("persists valid values", () => {
    savePrefs({ fontSize: 18, minimap: false, wordWrap: true });
    expect(loadPrefs()).toEqual({ fontSize: 18, minimap: false, wordWrap: true });
  });

  it("repairs corrupted or hostile stored values", () => {
    window.localStorage.setItem("sahucodex:editor-prefs", "{not json");
    expect(loadPrefs()).toEqual(DEFAULT_PREFS);

    window.localStorage.setItem("sahucodex:editor-prefs", JSON.stringify({ fontSize: 9999, minimap: "yes", wordWrap: 1 }));
    expect(loadPrefs()).toEqual({ ...DEFAULT_PREFS, fontSize: 28 });
  });

  it("clamps the font size", () => {
    expect([clampFont(3), clampFont(14), clampFont(90), clampFont(Number.NaN)]).toEqual([10, 14, 28, 14]);
  });
});

describe("normalizeWhitespace (used for languages without a formatter)", () => {
  it("trims trailing whitespace and ends with exactly one newline", () => {
    expect(normalizeWhitespace("a = 1   \nb = 2\t\n\n\n")).toBe("a = 1\nb = 2\n");
    expect(normalizeWhitespace("no newline")).toBe("no newline\n");
  });

  it("never changes indentation or blank lines inside the code", () => {
    const code = "def f():\n    x = 1\n\n\n    return x\n";
    expect(normalizeWhitespace(code)).toBe(code);
  });

  it("normalises Windows line endings", () => {
    expect(normalizeWhitespace("a\r\nb\r\n")).toBe("a\nb\n");
  });
});
