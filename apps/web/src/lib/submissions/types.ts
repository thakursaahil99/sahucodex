/** Response shapes of the SahuJudge API (see apps/api/app/modules/submissions/schemas.py). */

export type SubmissionStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";

export type Verdict =
  | "ACCEPTED"
  | "WRONG_ANSWER"
  | "TIME_LIMIT_EXCEEDED"
  | "MEMORY_LIMIT_EXCEEDED"
  | "RUNTIME_ERROR"
  | "COMPILATION_ERROR"
  | "SYSTEM_ERROR";

export interface SubmissionQueued {
  id: string;
  status: SubmissionStatus;
}

export interface PublicTestResult {
  position: number;
  verdict: Verdict;
  runtime_ms: number | null;
  memory_kb: number | null;
}

export interface SubmissionSummary {
  id: string;
  problem_slug: string;
  problem_title: string;
  language: string;
  status: SubmissionStatus;
  verdict: Verdict | null;
  runtime_ms: number | null;
  memory_kb: number | null;
  passed_count: number;
  total_count: number;
  created_at: string;
  finished_at: string | null;
}

export interface SubmissionDetail extends SubmissionSummary {
  source_code: string;
  compile_output: string | null;
  message: string | null;
  time_limit_ms: number | null;
  memory_limit_mb: number | null;
  test_results: PublicTestResult[];
}

export type RunOutcome = "OK" | Verdict;

export interface RunQueued {
  id: string;
}

export interface RunCaseOut {
  position: number;
  verdict: Verdict;
  input: string;
  expected_output: string;
  stdout: string;
  stderr: string;
  message: string | null;
  runtime_ms: number | null;
  memory_kb: number | null;
}

export interface RunResultOut {
  outcome: RunOutcome;
  compile_output: string | null;
  stdout: string | null;
  stderr: string | null;
  message: string | null;
  runtime_ms: number | null;
  memory_kb: number | null;
  cases: RunCaseOut[] | null;
}

export interface RunOut {
  id: string;
  status: SubmissionStatus;
  mode: "samples" | "custom";
  result: RunResultOut | null;
  error: string | null;
}

/** Still being judged — everywhere this appears, it decides whether to keep polling or listening. */
export function isPending(status: SubmissionStatus | undefined | null): boolean {
  return status === "QUEUED" || status === "RUNNING";
}
