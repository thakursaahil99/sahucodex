import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SubmissionsTable } from "@/components/submissions/submissions-table";
import type { Page } from "@/lib/problems/types";
import type { SubmissionSummary } from "@/lib/submissions/types";

const replace = vi.fn();
let query = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/submissions",
  useSearchParams: () => new URLSearchParams(query),
}));

const row = (over: Partial<SubmissionSummary> = {}): SubmissionSummary => ({
  id: "11111111-1111-1111-1111-111111111111",
  problem_slug: "two-sum",
  problem_title: "Two Sum",
  language: "python",
  status: "COMPLETED",
  verdict: "ACCEPTED",
  runtime_ms: 12,
  memory_kb: 3400,
  passed_count: 3,
  total_count: 3,
  created_at: "2026-09-21T10:00:00Z",
  finished_at: "2026-09-21T10:00:01Z",
  ...over,
});

let listResult: { data?: Page<SubmissionSummary>; isPending: boolean; isError: boolean } = {
  isPending: false,
  isError: false,
  data: { items: [row()], total: 1, page: 1, limit: 20, pages: 1 },
};
const lastFilters = vi.fn();

vi.mock("@/lib/submissions/api", () => ({
  useSubmissions: (filters: unknown) => {
    lastFilters(filters);
    return { ...listResult, refetch: vi.fn() };
  },
}));

beforeEach(() => {
  replace.mockReset();
  lastFilters.mockReset();
  query = "";
  listResult = { isPending: false, isError: false, data: { items: [row()], total: 1, page: 1, limit: 20, pages: 1 } };
});

describe("SubmissionsTable", () => {
  it("lists submissions with a link to their detail page", () => {
    render(<SubmissionsTable />);
    const link = screen.getByRole("link", { name: "Two Sum" });
    expect(link).toHaveAttribute("href", "/submissions/11111111-1111-1111-1111-111111111111");
    expect(screen.getByText("3/3 tests")).toBeInTheDocument();
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("shows a status badge instead of a verdict while still judging", () => {
    listResult.data = { items: [row({ status: "RUNNING", verdict: null })], total: 1, page: 1, limit: 20, pages: 1 };
    render(<SubmissionsTable />);
    expect(screen.getByText("Running…")).toBeInTheDocument();
  });

  it("filters by verdict and resets to page 1", async () => {
    query = "page=3";
    render(<SubmissionsTable />);
    await userEvent.selectOptions(screen.getByLabelText("Filter by verdict"), "WRONG_ANSWER");
    expect(replace).toHaveBeenCalledWith("/submissions?verdict=WRONG_ANSWER");
  });

  it("passes the parsed filters to the data hook", () => {
    query = "verdict=RUNTIME_ERROR&page=2";
    render(<SubmissionsTable />);
    expect(lastFilters).toHaveBeenLastCalledWith(expect.objectContaining({ verdict: "RUNTIME_ERROR", page: 2 }));
  });

  it("shows an empty state with a link to the problem list", () => {
    listResult.data = { items: [], total: 0, page: 1, limit: 20, pages: 0 };
    render(<SubmissionsTable />);
    expect(screen.getByText(/No submissions/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "problem" })).toHaveAttribute("href", "/problems");
  });

  it("shows a loading state and an error state with retry", () => {
    listResult = { isPending: true, isError: false };
    const { unmount } = render(<SubmissionsTable />);
    expect(screen.getByRole("status", { name: "Loading submissions" })).toBeInTheDocument();
    unmount();

    listResult = { isPending: false, isError: true };
    render(<SubmissionsTable />);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your submissions");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("paginates", async () => {
    query = "page=2";
    listResult.data = { items: [row()], total: 60, page: 2, limit: 20, pages: 3 };
    render(<SubmissionsTable />);
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(replace).toHaveBeenCalledWith("/submissions?page=3");
    await userEvent.click(screen.getByRole("button", { name: /Previous/ }));
    expect(replace).toHaveBeenLastCalledWith("/submissions");
  });

  it("never renders anything that looks like hidden test data", () => {
    render(<SubmissionsTable />);
    const html = document.body.innerHTML;
    expect(html).not.toMatch(/hidden.*input|expected_output/i);
    within(screen.getByRole("table")).getAllByRole("columnheader").forEach((header) => {
      expect(header.textContent).not.toMatch(/hidden/i);
    });
  });
});
