import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConsolePanel } from "@/components/problems/console-panel";
import type { Example } from "@/lib/problems/types";
import type { RunOut, SubmissionDetail } from "@/lib/submissions/types";

const examples: Example[] = [{ input: "1 2\n", output: "3\n", explanation: "1 + 2 = 3" }];

function setup(props: Partial<Parameters<typeof ConsolePanel>[0]> = {}) {
  const onInputChange = vi.fn();
  const onTabChange = vi.fn();
  render(
    <ConsolePanel
      examples={examples}
      input=""
      onInputChange={onInputChange}
      tab="input"
      onTabChange={onTabChange}
      run={null}
      submission={null}
      {...props}
    />,
  );
  return { onInputChange, onTabChange };
}

describe("ConsolePanel — input tab", () => {
  it("loads an example into the input box", async () => {
    const { onInputChange } = setup();
    await userEvent.click(screen.getByRole("button", { name: "1" }));
    expect(onInputChange).toHaveBeenCalledWith("1 2\n");
  });
});

describe("ConsolePanel — output tab", () => {
  const okRun = (over: Partial<RunOut> = {}): RunOut => ({
    id: "run-1",
    status: "COMPLETED",
    mode: "custom",
    result: {
      outcome: "OK",
      compile_output: null,
      stdout: "42\n",
      stderr: "",
      message: null,
      runtime_ms: 8,
      memory_kb: 2200,
      cases: null,
    },
    error: null,
    ...over,
  });

  it("shows nothing-yet before a run", () => {
    setup({ tab: "output" });
    expect(screen.getByText("Nothing has run yet")).toBeInTheDocument();
  });

  it("shows a live indicator while queued or running", () => {
    setup({ tab: "output", run: { id: "r", status: "RUNNING", mode: "custom", result: null, error: null } });
    expect(screen.getByRole("status")).toHaveTextContent("Running…");
  });

  it("shows stdout, runtime and memory for a plain run", () => {
    setup({ tab: "output", run: okRun() });
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Runtime: 8 ms")).toBeInTheDocument();
    expect(screen.getByText("Memory: 2.1 MB")).toBeInTheDocument();
  });

  it("shows the verdict and message for a failed run", () => {
    setup({
      tab: "output",
      run: okRun({
        result: {
          outcome: "RUNTIME_ERROR",
          compile_output: null,
          stdout: "",
          stderr: "Traceback...",
          message: "Exited with code 1",
          runtime_ms: 4,
          memory_kb: 1000,
          cases: null,
        },
      }),
    });
    expect(screen.getByText("Runtime Error")).toBeInTheDocument();
    expect(screen.getByText("Exited with code 1")).toBeInTheDocument();
    expect(screen.getByText("Traceback...")).toBeInTheDocument();
  });

  it("shows compiler output for a compilation error without a runtime/memory line", () => {
    setup({
      tab: "output",
      run: okRun({
        result: {
          outcome: "COMPILATION_ERROR",
          compile_output: "main.cpp:2: error",
          stdout: null,
          stderr: null,
          message: null,
          runtime_ms: null,
          memory_kb: null,
          cases: null,
        },
      }),
    });
    expect(screen.getByText("Compilation Error")).toBeInTheDocument();
    expect(screen.getByText("main.cpp:2: error")).toBeInTheDocument();
    expect(screen.queryByText(/Runtime:/)).not.toBeInTheDocument();
  });

  it("shows the judge's own failure separately from a program failure", () => {
    setup({ tab: "output", run: { id: "r", status: "FAILED", mode: "custom", result: null, error: "boom" } });
    expect(screen.getByText("The judge couldn't run this")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});

describe("ConsolePanel — results tab", () => {
  const submission = (over: Partial<SubmissionDetail> = {}): SubmissionDetail => ({
    id: "sub-1",
    problem_slug: "two-sum",
    problem_title: "Two Sum",
    language: "python",
    status: "COMPLETED",
    verdict: "ACCEPTED",
    runtime_ms: 5,
    memory_kb: 3000,
    passed_count: 2,
    total_count: 2,
    created_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:00:01Z",
    source_code: "x",
    compile_output: null,
    message: null,
    time_limit_ms: 2000,
    memory_limit_mb: 256,
    test_results: [
      { position: 1, verdict: "ACCEPTED", runtime_ms: 4, memory_kb: 2900 },
      { position: 2, verdict: "ACCEPTED", runtime_ms: 5, memory_kb: 3000 },
    ],
    ...over,
  });

  it("explains that hidden tests keep their data private, before any submission", () => {
    setup({ tab: "results" });
    expect(screen.getByText(/Hidden tests only ever report a verdict/)).toBeInTheDocument();
  });

  it("shows a per-test table for public tests only, with a note about the rest", () => {
    setup({
      tab: "results",
      submission: submission({ passed_count: 1, total_count: 5, test_results: [submission().test_results[0]!] }),
    });
    expect(screen.getAllByRole("row")).toHaveLength(2); // header + 1 public test
    expect(screen.getByText(/4 additional hidden tests ran/)).toBeInTheDocument();
  });

  it("never renders a hidden test's input or expected output", () => {
    setup({ tab: "results", submission: submission() });
    expect(document.body.innerHTML).not.toMatch(/expected_output/i);
  });
});

describe("ConsolePanel — showAi", () => {
  it("shows the SahuCodeX AI tab by default", () => {
    setup();
    expect(screen.getByRole("tab", { name: "SahuCodeX AI" })).toBeInTheDocument();
  });

  it("hides the SahuCodeX AI tab entirely when showAi is false, as in a contest", () => {
    setup({ showAi: false, tab: "input" });
    expect(screen.queryByRole("tab", { name: "SahuCodeX AI" })).not.toBeInTheDocument();
    expect(screen.queryByText(/No AI suggestion yet/)).not.toBeInTheDocument();
  });
});
