import { describe, expect, it } from "vitest";

import { profileSchema } from "@/lib/validation";

const base = { bio: "", country: "", website: "", github_url: "", avatar_url: "" };

describe("profileSchema", () => {
  it("accepts every field blank", () => {
    expect(profileSchema.safeParse(base).success).toBe(true);
  });

  it("accepts a fully filled-in profile", () => {
    const result = profileSchema.safeParse({
      bio: "I like graphs.",
      country: "IN",
      website: "https://ada.dev",
      github_url: "https://github.com/ada",
      avatar_url: "https://avatars.example/ada.png",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a bio over 500 characters", () => {
    expect(profileSchema.safeParse({ ...base, bio: "x".repeat(501) }).success).toBe(false);
  });

  it("rejects a country code that is not two letters", () => {
    for (const country of ["USA", "1", "u"]) {
      expect(profileSchema.safeParse({ ...base, country }).success).toBe(false);
    }
  });

  it.each(["website", "github_url", "avatar_url"] as const)("rejects a non-http(s) %s", (field) => {
    for (const value of ["javascript:alert(1)", "data:text/html,x", "ftp://example.com", "not a url"]) {
      const result = profileSchema.safeParse({ ...base, [field]: value });
      expect(result.success, `${field}=${value} should be rejected`).toBe(false);
    }
  });

  it.each(["website", "github_url", "avatar_url"] as const)("accepts a blank %s (clears the field)", (field) => {
    expect(profileSchema.safeParse({ ...base, [field]: "" }).success).toBe(true);
  });
});
