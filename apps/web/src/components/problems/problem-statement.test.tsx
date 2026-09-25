import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProblemStatement } from "@/components/problems/problem-statement";
import type { ProblemDetail, ProblemListItem } from "@/lib/problems/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/community/discussion-list", () => ({ DiscussionList: () => <div>Discussion</div> }));

let similarResult: { data?: ProblemListItem[]; isError: boolean };
const useSimilarProblems = vi.fn((_slug: string) => similarResult);
vi.mock("@/lib/problems/api", () => ({
  fetchHint: vi.fn(),
  useSimilarProblems: (slug: string) => useSimilarProblems(slug),
}));

const problem = (over: Partial<ProblemDetail> = {}): ProblemDetail => ({
  id: "11111111-1111-1111-1111-111111111111",
  slug: "two-sum",
  title: "Two Sum",
  difficulty: "EASY",
  description: "Find two numbers.",
  constraints: "n <= 10",
  input_format: "a",
  output_format: "b",
  time_limit_ms: 2000,
  memory_limit_mb: 256,
  function_signature: null,
  tags: [],
  examples: [],
  hint_count: 0,
  starter_code: {},
  acceptance_rate: 50,
  total_submissions: 10,
  status: null,
  solution_unlocked: false,
  editorial: null,
  expected_time_complexity: null,
  expected_space_complexity: null,
  ...over,
});

function renderStatement(over: Partial<ProblemDetail> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProblemStatement problem={problem(over)} />
    </QueryClientProvider>,
  );
}

describe("ProblemStatement — similar problems", () => {
  it("shows nothing when RAG returns an error (not configured)", () => {
    similarResult = { data: undefined, isError: true };
    renderStatement();
    expect(screen.queryByText("Similar problems")).not.toBeInTheDocument();
  });

  it("shows nothing when there are no similar problems", () => {
    similarResult = { data: [], isError: false };
    renderStatement();
    expect(screen.queryByText("Similar problems")).not.toBeInTheDocument();
  });

  it("lists similar problems with a link to each", () => {
    similarResult = {
      data: [
        {
          slug: "three-sum", title: "Three Sum", difficulty: "MEDIUM", tags: [], acceptance_rate: 40,
          total_submissions: 5, status: null,
        },
      ],
      isError: false,
    };
    renderStatement();
    expect(screen.getByText("Similar problems")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Three Sum/ });
    expect(link).toHaveAttribute("href", "/problems/three-sum");
  });
});
