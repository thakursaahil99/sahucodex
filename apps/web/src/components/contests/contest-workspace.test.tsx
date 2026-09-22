import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContestWorkspace } from "@/components/contests/contest-workspace";
import { ApiError } from "@/lib/api/http";
import type { ContestDetail, ContestProblemOut } from "@/lib/contests/types";
import type { Language } from "@/lib/problems/types";
import type { RunOut, SubmissionDetail } from "@/lib/submissions/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

vi.mock("@/components/problems/editor-pane", () => ({
  EditorPane: ({ onCodeChange }: { onCodeChange?: (code: string) => void }) => (
    <textarea aria-label="Code" onChange={(e) => onCodeChange?.(e.target.value)} />
  ),
}));

const useContest = vi.fn();
const useContestProblem = vi.fn();
const registerForContest = vi.fn();
const runContestCode = vi.fn();
const submitContestCode = vi.fn();
vi.mock("@/lib/contests/api", () => ({
  useContest: (...args: unknown[]) => useContest(...args),
  useContestProblem: (...args: unknown[]) => useContestProblem(...args),
  registerForContest: (...args: unknown[]) => registerForContest(...args),
  runContestCode: (...args: unknown[]) => runContestCode(...args),
  submitContestCode: (...args: unknown[]) => submitContestCode(...args),
}));

const useLanguages = vi.fn();
vi.mock("@/lib/problems/api", () => ({ useLanguages: (...args: unknown[]) => useLanguages(...args) }));

const useRun = vi.fn();
const useSubmission = vi.fn();
vi.mock("@/lib/submissions/api", () => ({
  useRun: (...args: unknown[]) => useRun(...args),
  useSubmission: (...args: unknown[]) => useSubmission(...args),
}));

const useJudgeSocket = vi.fn();
vi.mock("@/lib/submissions/socket", () => ({ useJudgeSocket: (...args: unknown[]) => useJudgeSocket(...args) }));

const contest = (over: Partial<ContestDetail> = {}): ContestDetail => ({
  slug: "spring-cup",
  title: "Spring Cup",
  start_time: "2026-01-01T00:00:00Z",
  end_time: "2026-01-01T03:00:00Z",
  phase: "running",
  problem_count: 1,
  description: "d",
  penalty_minutes: 20,
  problems: [{ label: "A", points: 100, title: "Two Sum" }],
  registered: true,
  ...over,
});

const problemOut = (over: Partial<ContestProblemOut> = {}): ContestProblemOut => ({
  label: "A",
  points: 100,
  problem: {
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
    starter_code: { python: "print(0)\n" },
  },
  ...over,
});

const languages: Language[] = [{ key: "python", display_name: "Python 3", editor_language: "python", file_extension: "py" }];

let queryClient: QueryClient;

function renderWorkspace() {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ContestWorkspace slug="spring-cup" label="A" />
    </QueryClientProvider>,
  );
}

const idleRun = { data: undefined, isPending: false } as { data?: RunOut; isPending: boolean };
const idleSubmission = { data: undefined, isPending: false } as { data?: SubmissionDetail; isPending: boolean };

beforeEach(() => {
  useContest.mockReturnValue({ isPending: false, isError: false, data: contest() });
  useContestProblem.mockReturnValue({ isPending: false, isError: false, data: problemOut() });
  useLanguages.mockReturnValue({ isPending: false, data: languages });
  registerForContest.mockReset().mockResolvedValue(undefined);
  runContestCode.mockReset().mockResolvedValue({ id: "run-1" });
  submitContestCode.mockReset().mockResolvedValue({ id: "sub-1" });
  useRun.mockReset().mockReturnValue(idleRun);
  useSubmission.mockReset().mockReturnValue(idleSubmission);
  useJudgeSocket.mockReset();
});

describe("ContestWorkspace", () => {
  it("shows a loading skeleton while the contest, problem or languages are pending", () => {
    useContest.mockReturnValue({ isPending: true });
    renderWorkspace();
    expect(screen.getByRole("status", { name: "Loading problem" })).toBeInTheDocument();
  });

  it("shows a 404 message for a problem not in this contest", () => {
    useContestProblem.mockReturnValue({ isPending: false, isError: true, error: new ApiError(404, "CONTEST_PROBLEM_NOT_FOUND", "x") });
    renderWorkspace();
    expect(screen.getByText("Problem not found")).toBeInTheDocument();
  });

  it("renders the problem's statement with its label and points", () => {
    renderWorkspace();
    expect(screen.getByRole("heading", { name: "A. Two Sum" })).toBeInTheDocument();
    expect(screen.getByText("100 pts")).toBeInTheDocument();
  });

  it("never shows the AI tab — assistance is off during a contest", () => {
    renderWorkspace();
    expect(screen.queryByRole("tab", { name: "SahuCodeX AI" })).not.toBeInTheDocument();
  });

  it("shows a spectator banner with a register button when not registered", async () => {
    useContest.mockReturnValue({ isPending: false, isError: false, data: contest({ registered: false }) });
    renderWorkspace();
    expect(screen.getByText(/viewing this problem as a spectator/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(registerForContest).toHaveBeenCalledWith("spring-cup");
  });

  it("does not show the spectator banner once registered", () => {
    renderWorkspace();
    expect(screen.queryByText(/viewing this problem as a spectator/)).not.toBeInTheDocument();
  });

  it("runs code against the contest-scoped run endpoint", async () => {
    renderWorkspace();
    await userEvent.type(screen.getByLabelText("Code"), "print('hi')");
    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));

    expect(runContestCode).toHaveBeenCalledWith(
      "spring-cup",
      "A",
      expect.objectContaining({ language: "python", source_code: "print('hi')", mode: "custom" }),
    );
  });

  it("submits code against the contest-scoped submit endpoint", async () => {
    renderWorkspace();
    await userEvent.type(screen.getByLabelText("Code"), "print('hi')");
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));

    expect(submitContestCode).toHaveBeenCalledWith("spring-cup", "A", { language: "python", source_code: "print('hi')" });
  });

  it("refuses to run or submit blank code, without calling the API", async () => {
    useContestProblem.mockReturnValue({
      isPending: false,
      isError: false,
      data: problemOut({ problem: { ...problemOut().problem, starter_code: { python: "   " } } }),
    });
    const { toast } = await import("sonner");
    renderWorkspace();
    await userEvent.click(screen.getByRole("button", { name: /^Run/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));
    expect(runContestCode).not.toHaveBeenCalled();
    expect(submitContestCode).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("Write some code first");
  });

  it("tells an unregistered submitter to register, instead of a raw error", async () => {
    submitContestCode.mockRejectedValue(new ApiError(403, "NOT_REGISTERED", "Register for this contest before submitting"));
    const { toast } = await import("sonner");
    renderWorkspace();
    await userEvent.type(screen.getByLabelText("Code"), "x");
    await userEvent.click(screen.getByRole("button", { name: /^Submit/ }));
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Register for this contest first", expect.anything()),
    );
  });

  it("has no starter code for any available language shows a clear message", () => {
    useContestProblem.mockReturnValue({
      isPending: false,
      isError: false,
      data: problemOut({ problem: { ...problemOut().problem, starter_code: {} } }),
    });
    renderWorkspace();
    expect(screen.getByText(/no starter code/)).toBeInTheDocument();
  });
});
