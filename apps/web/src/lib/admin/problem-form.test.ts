import { describe, expect, it } from "vitest";

import {
  caseCounts,
  emptyCase,
  emptyForm,
  fromAdmin,
  localIssues,
  slugify,
  toInput,
  type AdminProblem,
} from "@/lib/admin/problem-form";

const serverProblem: AdminProblem = {
  id: "p1",
  slug: "harbor-cranes",
  title: "Harbor Cranes",
  description: "desc",
  difficulty: "EASY",
  constraints: "c",
  input_format: "i",
  output_format: "o",
  time_limit_ms: 2000,
  memory_limit_mb: 256,
  tags: ["array"],
  hints: ["h1"],
  editorial: null,
  function_signature: null,
  expected_time_complexity: "O(n)",
  expected_space_complexity: null,
  starter_code: { python: "pass\n" },
  test_cases: [
    { id: "t1", kind: "PUBLIC", input: "1\n", expected_output: "2\n", show_as_example: true, example_explanation: "why" },
    { id: "t2", kind: "HIDDEN", input: "3\n", expected_output: "4\n", show_as_example: false, example_explanation: null },
  ],
  status: "DRAFT",
  published_at: null,
  total_submissions: 0,
  accepted_submissions: 0,
  created_at: "2026-09-21T00:00:00Z",
  updated_at: "2026-09-21T00:00:00Z",
};

describe("slugify", () => {
  it.each([
    ["Two Sum", "two-sum"],
    ["  Harbor   Cranes!! ", "harbor-cranes"],
    ["C++ & Rust: a comparison", "c-rust-a-comparison"],
    ["---", ""],
    ["ÀÉ ünïcode", "n-code"],
  ])("%s → %s", (input, expected) => {
    expect(slugify(input)).toBe(expected);
  });

  it("produces slugs the API accepts", () => {
    for (const title of ["A", "Hello, World", "  a--b  ", "x".repeat(200)]) {
      const slug = slugify(title);
      if (slug) expect(slug).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
      expect(slug.length).toBeLessThanOrEqual(80);
    }
  });
});

describe("fromAdmin / toInput", () => {
  it("keeps server ids so a save updates test cases instead of recreating them", () => {
    const form = fromAdmin(serverProblem);
    expect(form.test_cases.map((c) => c.id)).toEqual(["t1", "t2"]);
    const body = toInput(form);
    expect(body.test_cases.map((c) => (c as { id?: string }).id)).toEqual(["t1", "t2"]);
  });

  it("does not send client-only keys or ids for new cases", () => {
    const form = { ...emptyForm(), test_cases: [emptyCase("HIDDEN")] };
    const [sent] = toInput(form).test_cases as Array<Record<string, unknown>>;
    expect(sent).not.toHaveProperty("id");
    expect(sent).not.toHaveProperty("key");
  });

  it("turns blank optional fields into null and drops blank hints and starter code", () => {
    const form = fromAdmin(serverProblem);
    form.editorial = "   ";
    form.function_signature = "";
    form.hints = ["  keep  ", "", "   "];
    form.starter_code = { python: "code", cpp: "   " };
    const body = toInput(form);
    expect(body.editorial).toBeNull();
    expect(body.function_signature).toBeNull();
    expect(body.hints).toEqual(["keep"]);
    expect(body.starter_code).toEqual({ python: "code" });
  });

  it("never marks a hidden test as an example, even if the form state says so", () => {
    const form = fromAdmin(serverProblem);
    form.test_cases[1]!.show_as_example = true;
    form.test_cases[1]!.example_explanation = "leak?";
    const hidden = toInput(form).test_cases[1]!;
    expect(hidden.show_as_example).toBe(false);
    expect(hidden.example_explanation).toBeNull();
  });

  it("only sends an explanation for examples", () => {
    const form = fromAdmin(serverProblem);
    form.test_cases[0]!.show_as_example = false;
    expect(toInput(form).test_cases[0]!.example_explanation).toBeNull();
  });
});

describe("localIssues", () => {
  it("accepts a complete form", () => {
    expect(localIssues(fromAdmin(serverProblem))).toEqual([]);
  });

  it("flags the fields the API would reject", () => {
    const issues = localIssues({ ...emptyForm(), title: "x", slug: "Bad Slug", time_limit_ms: 5, memory_limit_mb: 99999 });
    expect(issues.map((i) => i.field).sort()).toEqual(["memory_limit_mb", "slug", "time_limit_ms", "title"]);
  });
});

describe("caseCounts", () => {
  it("counts by kind and examples", () => {
    expect(caseCounts(fromAdmin(serverProblem))).toEqual({ total: 2, public: 1, hidden: 1, examples: 1 });
  });
});
