import type { Difficulty, Page } from "@/lib/problems/types";

export type CaseKind = "PUBLIC" | "HIDDEN";
export type ProblemStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

// --- Server shapes ------------------------------------------------------------------------------

export interface AdminCase {
  id: string;
  kind: CaseKind;
  input: string;
  expected_output: string;
  show_as_example: boolean;
  example_explanation: string | null;
}

export interface AdminProblem {
  id: string;
  slug: string;
  title: string;
  description: string;
  difficulty: Difficulty;
  constraints: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  tags: string[];
  hints: string[];
  editorial: string | null;
  function_signature: string | null;
  expected_time_complexity: string | null;
  expected_space_complexity: string | null;
  starter_code: Record<string, string>;
  test_cases: AdminCase[];
  status: ProblemStatus;
  published_at: string | null;
  total_submissions: number;
  accepted_submissions: number;
  created_at: string;
  updated_at: string;
}

export interface AdminListItem {
  id: string;
  slug: string;
  title: string;
  difficulty: Difficulty;
  status: ProblemStatus;
  tags: string[];
  public_tests: number;
  hidden_tests: number;
  total_submissions: number;
  updated_at: string;
}

export type AdminPage = Page<AdminListItem>;

export interface ValidationIssue {
  field: string;
  code: string;
  message: string;
}

// --- Form model ---------------------------------------------------------------------------------

export interface CaseForm {
  /** Client-only identity so React keeps inputs stable while cases are added, moved and removed. */
  key: string;
  /** Present for cases that already exist on the server: sending it back updates instead of re-creating. */
  id?: string;
  kind: CaseKind;
  input: string;
  expected_output: string;
  show_as_example: boolean;
  example_explanation: string;
}

export interface ProblemForm {
  title: string;
  slug: string;
  description: string;
  difficulty: Difficulty;
  constraints: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  tags: string[];
  hints: string[];
  editorial: string;
  function_signature: string;
  expected_time_complexity: string;
  expected_space_complexity: string;
  starter_code: Record<string, string>;
  test_cases: CaseForm[];
}

let counter = 0;
export const newKey = (): string => `case-${Date.now().toString(36)}-${(counter++).toString(36)}`;

export function emptyCase(kind: CaseKind = "PUBLIC"): CaseForm {
  return { key: newKey(), kind, input: "", expected_output: "", show_as_example: kind === "PUBLIC", example_explanation: "" };
}

export function emptyForm(): ProblemForm {
  return {
    title: "",
    slug: "",
    description: "",
    difficulty: "EASY",
    constraints: "",
    input_format: "",
    output_format: "",
    time_limit_ms: 2000,
    memory_limit_mb: 256,
    tags: [],
    hints: [],
    editorial: "",
    function_signature: "",
    expected_time_complexity: "",
    expected_space_complexity: "",
    starter_code: {},
    test_cases: [emptyCase("PUBLIC")],
  };
}

/** `Two Sum!` → `two-sum`. Mirrors the API's slug pattern `^[a-z0-9]+(?:-[a-z0-9]+)*$`. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

export function fromAdmin(problem: AdminProblem): ProblemForm {
  return {
    title: problem.title,
    slug: problem.slug,
    description: problem.description,
    difficulty: problem.difficulty,
    constraints: problem.constraints,
    input_format: problem.input_format,
    output_format: problem.output_format,
    time_limit_ms: problem.time_limit_ms,
    memory_limit_mb: problem.memory_limit_mb,
    tags: [...problem.tags],
    hints: [...problem.hints],
    editorial: problem.editorial ?? "",
    function_signature: problem.function_signature ?? "",
    expected_time_complexity: problem.expected_time_complexity ?? "",
    expected_space_complexity: problem.expected_space_complexity ?? "",
    starter_code: { ...problem.starter_code },
    test_cases: problem.test_cases.map((c) => ({
      key: c.id,
      id: c.id,
      kind: c.kind,
      input: c.input,
      expected_output: c.expected_output,
      show_as_example: c.show_as_example,
      example_explanation: c.example_explanation ?? "",
    })),
  };
}

const blankToNull = (value: string): string | null => (value.trim() ? value : null);

/** The exact body for POST/PUT /api/admin/problems. */
export function toInput(form: ProblemForm) {
  return {
    title: form.title.trim(),
    slug: form.slug.trim(),
    description: form.description,
    difficulty: form.difficulty,
    constraints: form.constraints,
    input_format: form.input_format,
    output_format: form.output_format,
    time_limit_ms: form.time_limit_ms,
    memory_limit_mb: form.memory_limit_mb,
    tags: form.tags,
    hints: form.hints.map((h) => h.trim()).filter(Boolean),
    editorial: blankToNull(form.editorial),
    function_signature: blankToNull(form.function_signature),
    expected_time_complexity: blankToNull(form.expected_time_complexity),
    expected_space_complexity: blankToNull(form.expected_space_complexity),
    starter_code: Object.fromEntries(Object.entries(form.starter_code).filter(([, code]) => code.trim())),
    test_cases: form.test_cases.map((c) => ({
      ...(c.id ? { id: c.id } : {}),
      kind: c.kind,
      input: c.input,
      expected_output: c.expected_output,
      show_as_example: c.kind === "PUBLIC" && c.show_as_example,
      example_explanation: c.kind === "PUBLIC" && c.show_as_example ? blankToNull(c.example_explanation) : null,
    })),
  };
}

export interface LocalIssue {
  field: string;
  message: string;
}

/** Fast checks that need no server round trip. The server's `validation` endpoint remains the authority. */
export function localIssues(form: ProblemForm): LocalIssue[] {
  const issues: LocalIssue[] = [];
  if (form.title.trim().length < 3) issues.push({ field: "title", message: "Title needs at least 3 characters." });
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(form.slug) || form.slug.length < 3)
    issues.push({ field: "slug", message: "Slug: lowercase letters, digits and single hyphens, at least 3 characters." });
  if (form.time_limit_ms < 100 || form.time_limit_ms > 10_000)
    issues.push({ field: "time_limit_ms", message: "Time limit must be between 100 and 10 000 ms." });
  if (form.memory_limit_mb < 16 || form.memory_limit_mb > 1024)
    issues.push({ field: "memory_limit_mb", message: "Memory limit must be between 16 and 1024 MB." });
  if (form.tags.length > 10) issues.push({ field: "tags", message: "At most 10 tags." });
  return issues;
}

/** Counts shown in the editor's tab labels. */
export function caseCounts(form: ProblemForm) {
  return {
    total: form.test_cases.length,
    public: form.test_cases.filter((c) => c.kind === "PUBLIC").length,
    hidden: form.test_cases.filter((c) => c.kind === "HIDDEN").length,
    examples: form.test_cases.filter((c) => c.kind === "PUBLIC" && c.show_as_example).length,
  };
}
