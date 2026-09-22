import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StandingsTable } from "@/components/contests/standings-table";
import type { StandingsOut } from "@/lib/contests/types";

const useStandings = vi.fn();
vi.mock("@/lib/contests/api", () => ({ useStandings: (...args: unknown[]) => useStandings(...args) }));

const standings: StandingsOut = {
  generated_at: "2026-01-01T01:00:00Z",
  problems: [
    { label: "A", points: 100, title: null },
    { label: "B", points: 200, title: null },
  ],
  rows: [
    {
      rank: 1,
      username: "cleo",
      total_points: 300,
      total_penalty_minutes: 25,
      cells: {
        A: { solved: true, attempts: 0, penalty_minutes: 5 },
        B: { solved: true, attempts: 1, penalty_minutes: 20 },
      },
    },
    {
      rank: 2,
      username: "ada",
      total_points: 100,
      total_penalty_minutes: 30,
      cells: {
        A: { solved: true, attempts: 1, penalty_minutes: 30 },
        B: { solved: false, attempts: 2, penalty_minutes: 0 },
      },
    },
  ],
};

function renderTable(live = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <StandingsTable slug="spring-cup" live={live} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useStandings.mockReset();
});

describe("StandingsTable", () => {
  it("passes `live` straight through to useStandings", () => {
    useStandings.mockReturnValue({ isPending: true });
    renderTable(true);
    expect(useStandings).toHaveBeenCalledWith("spring-cup", { live: true });
  });

  it("shows a skeleton while loading", () => {
    useStandings.mockReturnValue({ isPending: true });
    const { container } = renderTable();
    expect(container.querySelector('[data-slot="skeleton"]')).toBeInTheDocument();
  });

  it("shows an error message on failure", () => {
    useStandings.mockReturnValue({ isPending: false, isError: true });
    renderTable();
    expect(screen.getByText(/Couldn't load standings/)).toBeInTheDocument();
  });

  it("says so when nobody has registered yet", () => {
    useStandings.mockReturnValue({ isPending: false, isError: false, data: { ...standings, rows: [] } });
    renderTable();
    expect(screen.getByText(/No one has registered yet/)).toBeInTheDocument();
  });

  it("ranks rows, shows totals, and marks solved/attempted/untouched cells distinctly", () => {
    useStandings.mockReturnValue({ isPending: false, isError: false, data: standings });
    renderTable();

    const rows = screen.getAllByRole("row");
    const cleo = within(rows[1]!);
    expect(cleo.getByText("1")).toBeInTheDocument(); // rank
    expect(cleo.getByText("cleo")).toBeInTheDocument();
    expect(cleo.getByText("300")).toBeInTheDocument();
    expect(cleo.getByText("25")).toBeInTheDocument();
    expect(cleo.getByTitle("Solved · penalty 5m")).toBeInTheDocument();

    const ada = within(rows[2]!);
    expect(ada.getByTitle("2 attempt(s)")).toBeInTheDocument(); // unsolved B, 2 non-accepted attempts

    // Column headers show the problem labels the contest actually has.
    expect(screen.getByRole("columnheader", { name: "A" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "B" })).toBeInTheDocument();
  });

  it("shows a dash for a problem nobody has touched", () => {
    const untouched: StandingsOut = {
      ...standings,
      rows: [{ rank: 1, username: "ada", total_points: 0, total_penalty_minutes: 0, cells: {} }],
    };
    useStandings.mockReturnValue({ isPending: false, isError: false, data: untouched });
    renderTable();
    const row = within(screen.getAllByRole("row")[1]!);
    expect(row.getAllByText("—")).toHaveLength(2); // one per problem column
  });
});
