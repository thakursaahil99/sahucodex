import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecommendedProblems } from "@/components/dashboard/recommended-problems";
import type { ProblemListItem } from "@/lib/problems/types";

let result: { data?: ProblemListItem[]; isPending: boolean; isError: boolean };
const useRecommendations = vi.fn((_enabled: boolean) => result);
vi.mock("@/lib/problems/api", () => ({ useRecommendations: (enabled: boolean) => useRecommendations(enabled) }));

const problem = (over: Partial<ProblemListItem> = {}): ProblemListItem => ({
  slug: "two-sum",
  title: "Two Sum",
  difficulty: "EASY",
  tags: [{ name: "Array", slug: "array" }],
  acceptance_rate: 55.5,
  total_submissions: 10,
  status: null,
  ...over,
});

describe("RecommendedProblems", () => {
  it("renders nothing when not enabled (e.g. signed out)", () => {
    result = { data: undefined, isPending: false, isError: false };
    const { container } = render(<RecommendedProblems enabled={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a loading state", () => {
    result = { data: undefined, isPending: true, isError: false };
    render(<RecommendedProblems enabled />);
    expect(screen.getByRole("status", { name: "Loading recommendations" })).toBeInTheDocument();
  });

  it("shows an error state", () => {
    result = { data: undefined, isPending: false, isError: true };
    render(<RecommendedProblems enabled />);
    expect(screen.getByText("Couldn't load recommendations.")).toBeInTheDocument();
  });

  it("shows an all-caught-up message when there is nothing to recommend", () => {
    result = { data: [], isPending: false, isError: false };
    render(<RecommendedProblems enabled />);
    expect(screen.getByText(/all caught up/)).toBeInTheDocument();
  });

  it("lists recommended problems with a link to each", () => {
    result = { data: [problem()], isPending: false, isError: false };
    render(<RecommendedProblems enabled />);
    const link = screen.getByRole("link", { name: /Two Sum/ });
    expect(link).toHaveAttribute("href", "/problems/two-sum");
  });
});
