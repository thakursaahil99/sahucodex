import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProblemWorkspace } from "@/components/problems/problem-workspace";
import { ApiError } from "@/lib/api/http";
import type { Language, ProblemDetail } from "@/lib/problems/types";
import type { RunOut, SubmissionDetail } from "@/lib/submissions/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

// Real Monaco is heavy and irrelevant here; a plain textarea stands in and reports every keystroke, as the real
// EditorPane does through its own effect.
vi.mock("@/components/problems/editor-pane", () => ({
  EditorPane: ({ onCodeChange }: { onCodeChange?: (code: string) => void }) => (
    <textarea aria-label="Code" onChange={(e) => onCodeChange?.(e.target.value)} />
  ),
}));
vi.mock("@/components/problems/problem-statement", () => ({ ProblemStatement: () => <div>Statement</div> }));

const useProblem = vi.fn();
const useLanguages = vi.fn();
vi.mock("@/lib/problems/api", () => ({
  useProblem: (...args: unknown[]) => useProblem(...args),
  useLanguages: (...args: unknown[]) => useLanguages(...args),
}));

const runCode = vi.fn();
const submitCode = vi.fn();
const useRun = vi.fn();
const useSubmission = vi.fn();
vi.mock("@/lib/submissions/api", () => ({
  runCode: (...args: unknown[]) => runCode(...args),
  submitCode: (...args: unknown[]) => submitCode(...args),
  useRun: (...args: unknown[]) => useRun(...args),
  useSubmission: (...args: unknown[]) => useSubmission(...args),
}));

const generate = vi.fn();
const useAiStatus = vi.fn();
vi.mock("@/lib/ai/api", () => ({
  generate: (...args: unknown[]) => generate(...args),
  useAiStatus: () => useAiStatus(),
}));

const useJudgeSocket = vi.fn();
vi.mock("@/lib/submissions/socket", () => ({ useJudgeSocket: (...args: unknown[]) => useJudgeSocket(...args) }));

const problem = (over: Partial<ProblemDetail> = {}): ProblemDetail => ({
  id: "p1",
  slug: "two-sum",
  title: "Two Sum",
  difficulty: "EASY",
  description: "d",
  constraints: "c",
  input_format: "i",
  output_format: "o",
  time_limit_ms: 2000,
  memory_limit_mb: 256,
  function_signature: null,
  tags: [],
  examples: [{ input: "1 2\n", output: "3\n", explanation: null }],
  hint_count: 0,
  starter_code: { python: "print(0)\n" },
  acceptance_rate: null,
  total_submissions: 0,
  status: null,
  solution_unlocked: false,
  editorial: null,
  expected_time_complexity: null,
  expected_space_complexity: null,
  ...over,
});

const languages: Language[] = [{ key: "python", display_name: "Python 3", editor_language: "python", file_extension: "py" }];

let queryClient: QueryClient;

function renderWorkspace() {
  return render(
    <QueryClientProvider client={queryClient}>
      <ProblemWorkspace slug="two-sum" />
    </QueryClientProvider>,
  );
}

const idleRun = { data: undefined, isPending: false } as { data?: RunOut; isPending: boolean };
const idleSubmission = { data: undefined, isPending: false } as { data?: SubmissionDetail; isPending: boolean };

beforeEach(() => {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  useProblem.mockReturnValue({ isPending: false, isError: false, data: problem() });
  useLanguages.mockReturnValue({ isPending: false, data: languages });
  runCode.mockReset().mockResolvedValue({ id: "run-1" });
  submitCode.mockReset().mockResolvedValue({ id: "sub-1" });
  useRun.mockReset().mockReturnValue(idleRun);
  useSubmission.mockReset().mockReturnValue(idleSubmission);
  useJudgeSocket.mockReset();
  generate.mockReset();
  useAiStatus.mockReset().mockReturnValue({ data: { configured: true, model: "test-model" } });
});

describe("ProblemWorkspace", () => {
  it("shows a loading skeleton while the problem or languages are pending", () => {
    useProblem.mockReturnValue({ isPending: true });
    renderWorkspace();
    expect(screen.getByRole("status", { name: "Loading problem" })).toBeInTheDocument();
  });

  it("shows a 404 message for a missing problem", () => {
    useProblem.mockReturnValue({ isPending: false, isError: true, error: new ApiError(404, "PROBLEM_NOT_FOUND", "x") });
    renderWorkspace();
    expect(screen.getByText("Problem not found")).toBeInTheDocument();
  });

  it("runs the code currently in the editor and shows the output tab", async () => {
    useRun.mockImplementation((id: string | undefined) =>
      id === "run-1"
        ? {
            data: {
              id: "run-1",
              status: "COMPLETED",
              mode: "custom",
              result: {
                outcome: "OK",
                compile_output: null,
                stdout: "hello\n",
                stderr: "",
                message: null,
                runtime_ms: 3,
                memory_kb: 900,
                cases: null,
              },
              error: null,
            },
            isPending: false,
          }
        : idleRun,
    );

    renderWorkspace();
    await userEvent.type(screen.getByLabelText("Code"), "print('hi')");
    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));

    expect(runCode).toHaveBeenCalledWith(
      expect.objectContaining({ problem_slug: "two-sum", language: "python", source_code: "print('hi')", mode: "custom" }),
    );
    expect(await screen.findByText("hello")).toBeInTheDocument();
  });

  it("submits the code currently in the editor, shows results, and reports Accepted", async () => {
    const accepted: SubmissionDetail = {
      id: "sub-1",
      problem_slug: "two-sum",
      problem_title: "Two Sum",
      language: "python",
      status: "COMPLETED",
      verdict: "ACCEPTED",
      runtime_ms: 4,
      memory_kb: 1000,
      passed_count: 2,
      total_count: 2,
      created_at: "2026-01-01T00:00:00Z",
      finished_at: "2026-01-01T00:00:01Z",
      source_code: "x",
      compile_output: null,
      message: null,
      time_limit_ms: 2000,
      memory_limit_mb: 256,
      test_results: [{ position: 1, verdict: "ACCEPTED", runtime_ms: 4, memory_kb: 1000 }],
    };
    useSubmission.mockImplementation((id: string | undefined) => (id === "sub-1" ? { data: accepted, isPending: false } : idleSubmission));
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const { toast } = await import("sonner");

    renderWorkspace();
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));

    expect(submitCode).toHaveBeenCalledWith(
      expect.objectContaining({ problem_slug: "two-sum", language: "python", source_code: "print(0)\n" }),
    );
    // One badge for the overall verdict, one for the single (passing) public test row.
    expect(await screen.findAllByText("Accepted")).toHaveLength(2);
    expect(toast.success).toHaveBeenCalledWith("Accepted!", expect.anything());
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["problem"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["problems"] });
  });

  it("refuses to run or submit blank code, without calling the API", async () => {
    useProblem.mockReturnValue({ isPending: false, isError: false, data: problem({ starter_code: { python: "   " } }) });
    const { toast } = await import("sonner");
    renderWorkspace();

    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));

    expect(runCode).not.toHaveBeenCalled();
    expect(submitCode).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Write some code first");
  });

  it("disables both actions once a run is in flight", async () => {
    useRun.mockImplementation((id: string | undefined) =>
      id === "run-1"
        ? { data: { id: "run-1", status: "RUNNING", mode: "custom", result: null, error: null }, isPending: false }
        : idleRun,
    );
    renderWorkspace();
    expect(screen.getByRole("button", { name: /^Run/ })).not.toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));
    expect(screen.getByRole("button", { name: /^Run/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Submit/ })).toBeDisabled();
  });

  it("invalidates the matching query when the socket reports an event for the run or submission being watched", async () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderWorkspace();
    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));

    const handler = useJudgeSocket.mock.calls.at(-1)![0] as (event: { data: Record<string, unknown> }) => void;
    handler({ data: { run_id: "run-1" } });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["run", "run-1"] });

    handler({ data: { run_id: "someone-elses-run" } });
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ["run", "someone-elses-run"] });
  });

  it("never renders anything that looks like hidden test data", async () => {
    const submission: SubmissionDetail = {
      id: "sub-1",
      problem_slug: "two-sum",
      problem_title: "Two Sum",
      language: "python",
      status: "COMPLETED",
      verdict: "WRONG_ANSWER",
      runtime_ms: 4,
      memory_kb: 1000,
      passed_count: 1,
      total_count: 4,
      created_at: "2026-01-01T00:00:00Z",
      finished_at: "2026-01-01T00:00:01Z",
      source_code: "x",
      compile_output: null,
      message: null,
      time_limit_ms: 2000,
      memory_limit_mb: 256,
      test_results: [{ position: 1, verdict: "ACCEPTED", runtime_ms: 4, memory_kb: 1000 }],
    };
    useSubmission.mockImplementation((id: string | undefined) => (id === "sub-1" ? { data: submission, isPending: false } : idleSubmission));

    renderWorkspace();
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));
    await screen.findByText(/3 additional hidden tests ran/);
    expect(document.body.innerHTML).not.toMatch(/expected_output/i);
  });

  describe("SahuCodeX AI", () => {
    it("asks for a hint with the slug, language and current code, and shows it as a suggestion, not a verdict", async () => {
      generate.mockResolvedValue({ feature: "hint", content: "Think about complements.", model: "test-model" });
      renderWorkspace();
      await userEvent.type(screen.getByLabelText("Code"), "pass");
      await userEvent.click(screen.getByRole("button", { name: /AI Hint/ }));

      expect(generate).toHaveBeenCalledWith({
        feature: "hint",
        problemSlug: "two-sum",
        language: "python",
        code: "pass",
        previousHints: [],
      });
      expect(await screen.findByText("Think about complements.")).toBeInTheDocument();
      expect(screen.getByText(/a suggestion, not a verdict/)).toBeInTheDocument();
      expect(screen.getByText(/AI hint #1/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Continue in chat/ })).toHaveAttribute("href", "/ai?problem=two-sum");
    });

    it("sends earlier hints back so the next one goes further", async () => {
      generate
        .mockResolvedValueOnce({ feature: "hint", content: "First nudge.", model: "m" })
        .mockResolvedValueOnce({ feature: "hint", content: "Second nudge.", model: "m" });
      renderWorkspace();
      await userEvent.type(screen.getByLabelText("Code"), "x");
      await userEvent.click(screen.getByRole("button", { name: /AI Hint/ }));
      await screen.findByText("First nudge.");
      await userEvent.click(screen.getByRole("button", { name: /AI Hint/ }));

      expect(generate).toHaveBeenLastCalledWith(expect.objectContaining({ previousHints: ["First nudge."] }));
      expect(await screen.findByText(/AI hint #2/)).toBeInTheDocument();
    });

    it("runs Review and Explain through the same path", async () => {
      generate.mockResolvedValue({ feature: "review", content: "## Correctness\nLooks plausible.", model: "m" });
      renderWorkspace();
      await userEvent.type(screen.getByLabelText("Code"), "x");
      await userEvent.click(screen.getByRole("button", { name: /AI Review/ }));
      expect(await screen.findByRole("heading", { name: "Correctness" })).toBeInTheDocument();
      expect(generate).toHaveBeenLastCalledWith(expect.objectContaining({ feature: "review", previousHints: [] }));

      await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
      expect(generate).toHaveBeenLastCalledWith(expect.objectContaining({ feature: "explain" }));
    });

    it("shows the server's message when the AI is unavailable, and never invents an answer", async () => {
      generate.mockRejectedValue(new ApiError(503, "AI_UNAVAILABLE", "SahuCodeX AI could not answer right now."));
      renderWorkspace();
      await userEvent.type(screen.getByLabelText("Code"), "x");
      await userEvent.click(screen.getByRole("button", { name: /AI Review/ }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("SahuCodeX AI could not answer right now.");
      expect(screen.queryByText(/a suggestion, not a verdict/)).not.toBeInTheDocument();
    });

    it("tells the user how long to wait after a rate limit", async () => {
      generate.mockRejectedValue(new ApiError(429, "RATE_LIMITED", "Too many requests", undefined, 1800));
      renderWorkspace();
      await userEvent.type(screen.getByLabelText("Code"), "x");
      await userEvent.click(screen.getByRole("button", { name: /AI Hint/ }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Try again in about 30 minute(s)");
    });

    it("refuses blank code without calling the AI", async () => {
      useProblem.mockReturnValue({ isPending: false, isError: false, data: problem({ starter_code: { python: "  " } }) });
      const { toast } = await import("sonner");
      renderWorkspace();
      await userEvent.click(screen.getByRole("button", { name: /AI Hint/ }));
      expect(generate).not.toHaveBeenCalled();
      expect(toast.error).toHaveBeenCalledWith("Write some code first");
    });

    it("explains the missing model instead of calling the AI when the server has none configured", async () => {
      useAiStatus.mockReturnValue({ data: { configured: false, model: null } });
      renderWorkspace();
      const hint = screen.getByRole("button", { name: /AI Hint/ });
      expect(hint).toHaveAttribute("aria-disabled", "true");
      expect(hint).toHaveAttribute("title", expect.stringContaining("OLLAMA_MODEL"));
      await userEvent.click(hint);
      expect(generate).not.toHaveBeenCalled();
    });
  });
});
