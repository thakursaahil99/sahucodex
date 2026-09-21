import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubmissionDetailView } from "@/components/submissions/submission-detail";
import { ApiError } from "@/lib/api/http";
import type { SubmissionDetail } from "@/lib/submissions/types";

const invalidateQueries = vi.fn();
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => ({ invalidateQueries }) }));

const useJudgeSocket = vi.fn();
vi.mock("@/lib/submissions/socket", () => ({ useJudgeSocket: (...args: unknown[]) => useJudgeSocket(...args) }));

let submissionResult: { data?: SubmissionDetail; isPending: boolean; isError: boolean; error?: unknown };
const useSubmission = vi.fn((): typeof submissionResult => submissionResult);
vi.mock("@/lib/submissions/api", () => ({ useSubmission: () => useSubmission() }));

const detail = (over: Partial<SubmissionDetail> = {}): SubmissionDetail => ({
  id: "11111111-1111-1111-1111-111111111111",
  problem_slug: "two-sum",
  problem_title: "Two Sum",
  language: "python",
  status: "COMPLETED",
  verdict: "WRONG_ANSWER",
  runtime_ms: 12,
  memory_kb: 3400,
  passed_count: 1,
  total_count: 2,
  created_at: "2026-09-21T10:00:00Z",
  finished_at: "2026-09-21T10:00:01Z",
  source_code: "print('mine')\n",
  compile_output: null,
  message: "Exited with code 1",
  time_limit_ms: 2000,
  memory_limit_mb: 256,
  test_results: [{ position: 1, verdict: "ACCEPTED", runtime_ms: 5, memory_kb: 3000 }],
  ...over,
});

beforeEach(() => {
  invalidateQueries.mockReset();
  useJudgeSocket.mockReset();
  submissionResult = { isPending: false, isError: false, data: detail() };
});

describe("SubmissionDetailView", () => {
  it("shows the verdict, stats, message and per-test results", () => {
    render(<SubmissionDetailView id="11111111-1111-1111-1111-111111111111" />);
    expect(screen.getByRole("heading", { name: "Two Sum" })).toBeInTheDocument();
    expect(screen.getByText("Wrong Answer")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("Exited with code 1")).toBeInTheDocument();
    expect(screen.getByText("print('mine')")).toBeInTheDocument();
    expect(screen.getByText("Accepted")).toBeInTheDocument(); // the one public test row
  });

  it("links the problem title to the problem workspace", () => {
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByRole("link", { name: "Two Sum" })).toHaveAttribute("href", "/problems/two-sum");
  });

  it("mentions hidden tests ran without showing their data", () => {
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByText(/1 additional hidden test ran/)).toBeInTheDocument();
    expect(document.body.innerHTML).not.toMatch(/expected_output|hidden.*input/i);
  });

  it("says nothing about hidden tests when every test shown is the whole story", () => {
    submissionResult.data = detail({
      total_count: 1,
      test_results: [{ position: 1, verdict: "ACCEPTED", runtime_ms: 5, memory_kb: 3000 }],
    });
    render(<SubmissionDetailView id="x" />);
    expect(screen.queryByText(/hidden test/)).not.toBeInTheDocument();
  });

  it("shows compiler output when present", () => {
    submissionResult.data = detail({ verdict: "COMPILATION_ERROR", compile_output: "main.cpp:1: error: boom" });
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByText("main.cpp:1: error: boom")).toBeInTheDocument();
  });

  it("shows a live status while still judging, and keeps polling via the socket", () => {
    submissionResult.data = detail({ status: "RUNNING", verdict: null, test_results: [] });
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByRole("status")).toHaveTextContent("Running…");
    expect(useJudgeSocket).toHaveBeenCalledWith(expect.any(Function), true);
  });

  it("stops watching the socket once judging has settled", () => {
    render(<SubmissionDetailView id="x" />); // detail() defaults to COMPLETED
    expect(useJudgeSocket).toHaveBeenCalledWith(expect.any(Function), false);
  });

  it("invalidates its own query when a matching event arrives, and ignores others", () => {
    render(<SubmissionDetailView id="target-id" />);
    const handler = useJudgeSocket.mock.calls[0]![0] as (event: { data: Record<string, unknown> }) => void;

    handler({ data: { submission_id: "someone-elses-id" } });
    expect(invalidateQueries).not.toHaveBeenCalled();

    handler({ data: { submission_id: "target-id" } });
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ["submission", "target-id"] });
  });

  it("shows a loading skeleton", () => {
    submissionResult = { isPending: true, isError: false };
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByRole("status", { name: "Loading submission" })).toBeInTheDocument();
  });

  it("distinguishes 'not found' from a generic failure", () => {
    submissionResult = { isPending: false, isError: true, error: new ApiError(404, "SUBMISSION_NOT_FOUND", "nope") };
    const { unmount } = render(<SubmissionDetailView id="x" />);
    expect(screen.getByText("Submission not found")).toBeInTheDocument();
    unmount();

    submissionResult = { isPending: false, isError: true, error: new ApiError(500, "SERVER_ERROR", "boom") };
    render(<SubmissionDetailView id="x" />);
    expect(screen.getByText("Couldn't load this submission")).toBeInTheDocument();
  });
});
