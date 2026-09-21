import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProblemsBrowser } from "@/components/problems/problems-browser";
import { useAuthStore } from "@/lib/auth/store";
import type { Page, ProblemListItem, TagWithCount } from "@/lib/problems/types";
import { sampleUser } from "@/test-utils";

const replace = vi.fn();
let query = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/problems",
  useSearchParams: () => new URLSearchParams(query),
}));

const item = (over: Partial<ProblemListItem> = {}): ProblemListItem => ({
  slug: "harbor-cranes",
  title: "Harbor Cranes",
  difficulty: "EASY",
  tags: [{ name: "Array", slug: "array" }],
  acceptance_rate: 42.5,
  total_submissions: 10,
  status: null,
  ...over,
});

let listResult: { data?: Page<ProblemListItem>; isPending: boolean; isError: boolean; isFetching: boolean } = {
  isPending: false,
  isError: false,
  isFetching: false,
  data: { items: [item()], total: 1, page: 1, limit: 20, pages: 1 },
};
const tags: TagWithCount[] = Array.from({ length: 15 }, (_, i) => ({ name: `Topic ${i}`, slug: `topic-${i}`, problem_count: i }));
const lastFilters = vi.fn();

vi.mock("@/lib/problems/api", () => ({
  useProblemList: (filters: unknown) => {
    lastFilters(filters);
    return { ...listResult, refetch: vi.fn() };
  },
  useTags: () => ({ data: tags }),
}));

beforeEach(() => {
  replace.mockReset();
  lastFilters.mockReset();
  query = "";
  useAuthStore.setState({ status: "anonymous", accessToken: null, expiresAt: null, user: null });
  listResult = {
    isPending: false,
    isError: false,
    isFetching: false,
    data: { items: [item()], total: 1, page: 1, limit: 20, pages: 1 },
  };
});

describe("ProblemsBrowser", () => {
  it("lists problems with difficulty, topics and acceptance, linking to the workspace", () => {
    render(<ProblemsBrowser />);
    const row = screen.getByRole("link", { name: /Harbor Cranes/ });
    expect(row).toHaveAttribute("href", "/problems/harbor-cranes");
    expect(within(row).getByText("Easy")).toBeInTheDocument();
    expect(within(row).getByText("Array")).toBeInTheDocument();
    expect(within(row).getByText("42.5%")).toBeInTheDocument();
    expect(screen.getByText("1 problem")).toBeInTheDocument();
  });

  it("shows a dash when nobody has submitted yet", () => {
    listResult.data = { items: [item({ acceptance_rate: null })], total: 1, page: 1, limit: 20, pages: 1 };
    render(<ProblemsBrowser />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("puts the chosen difficulty in the URL and resets to page 1", async () => {
    query = "page=3";
    render(<ProblemsBrowser />);
    await userEvent.click(screen.getByRole("button", { name: "Hard" }));
    expect(replace).toHaveBeenCalledWith("/problems?difficulty=HARD", { scroll: false });
  });

  it("toggles a difficulty off again", async () => {
    query = "difficulty=EASY&difficulty=HARD";
    render(<ProblemsBrowser />);
    expect(screen.getByRole("button", { name: "Easy" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Easy" }));
    expect(replace).toHaveBeenCalledWith("/problems?difficulty=HARD", { scroll: false });
  });

  it("collapses the topic list and can show all of them", async () => {
    render(<ProblemsBrowser />);
    expect(screen.queryByRole("button", { name: /Topic 14/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all 15 topics" }));
    expect(screen.getByRole("button", { name: /Topic 14/ })).toBeInTheDocument();
  });

  it("keeps a selected topic visible even when the list is collapsed", () => {
    query = "tag=topic-14";
    render(<ProblemsBrowser />);
    expect(screen.getByRole("button", { name: /Topic 14/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("debounces the search box before touching the URL", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<ProblemsBrowser />);
    const box = screen.getByRole("searchbox", { name: "Search problems" });
    await userEvent.type(box, "graph", { advanceTimers: vi.advanceTimersByTime });
    expect(replace).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(400);
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/problems?q=graph", { scroll: false });
    vi.useRealTimers();
  });

  it("only offers progress filters to signed-in users", () => {
    const { unmount } = render(<ProblemsBrowser />);
    expect(screen.queryByRole("button", { name: "Solved" })).not.toBeInTheDocument();
    unmount();

    useAuthStore.setState({ status: "authenticated", accessToken: "t", user: sampleUser });
    render(<ProblemsBrowser />);
    expect(screen.getByRole("button", { name: "Solved" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unsolved" })).toBeInTheDocument();
  });

  it("offers 'clear all' only when filters are active, and clears them", async () => {
    const { unmount } = render(<ProblemsBrowser />);
    expect(screen.queryByRole("button", { name: /Clear all filters/ })).not.toBeInTheDocument();
    unmount();

    query = "difficulty=EASY";
    render(<ProblemsBrowser />);
    await userEvent.click(screen.getByRole("button", { name: /Clear all filters/ }));
    expect(replace).toHaveBeenCalledWith("/problems", { scroll: false });
  });

  it("explains an empty result and lets the user recover", async () => {
    query = "q=zzz";
    listResult.data = { items: [], total: 0, page: 1, limit: 20, pages: 0 };
    render(<ProblemsBrowser />);
    expect(screen.getByText("No problems match those filters")).toBeInTheDocument();
    await userEvent.click(within(screen.getByText("No problems match those filters").parentElement!).getByRole("button", { name: "Clear all filters" }));
    expect(replace).toHaveBeenCalledWith("/problems", { scroll: false });
  });

  it("shows a loading state and an error state with retry", () => {
    listResult = { isPending: true, isError: false, isFetching: true };
    const { unmount } = render(<ProblemsBrowser />);
    expect(screen.getByRole("status", { name: "Loading problems" })).toBeInTheDocument();
    unmount();

    listResult = { isPending: false, isError: true, isFetching: false };
    render(<ProblemsBrowser />);
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load problems");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("paginates", async () => {
    query = "page=2";
    listResult.data = { items: [item()], total: 60, page: 2, limit: 20, pages: 3 };
    render(<ProblemsBrowser />);
    expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(replace).toHaveBeenCalledWith("/problems?page=3", { scroll: false });
    await userEvent.click(screen.getByRole("button", { name: /Previous/ }));
    expect(replace).toHaveBeenLastCalledWith("/problems", { scroll: false });
  });

  it("passes the parsed filters to the data hook", () => {
    query = "q=trie&difficulty=HARD&acceptance=low";
    render(<ProblemsBrowser />);
    expect(lastFilters).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: "trie", difficulties: ["HARD"], acceptance: "low" }),
    );
  });
});
