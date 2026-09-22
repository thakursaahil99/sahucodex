import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContestOverview } from "@/components/contests/contest-overview";
import type { ContestDetail } from "@/lib/contests/types";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const useContest = vi.fn();
const registerForContest = vi.fn();
vi.mock("@/lib/contests/api", () => ({
  useContest: (...args: unknown[]) => useContest(...args),
  registerForContest: (...args: unknown[]) => registerForContest(...args),
  useStandings: () => ({ isPending: true }),
}));

const authState = { status: "authenticated" as string };
vi.mock("@/lib/auth/store", () => ({ useAuthStore: (selector: (s: typeof authState) => unknown) => selector(authState) }));

const contest = (over: Partial<ContestDetail> = {}): ContestDetail => ({
  slug: "spring-cup",
  title: "Spring Cup",
  start_time: "2026-01-01T00:00:00Z",
  end_time: "2026-01-01T03:00:00Z",
  phase: "running",
  problem_count: 1,
  description: "Welcome!",
  penalty_minutes: 20,
  problems: [{ label: "A", points: 100, title: "Two Sum" }],
  registered: false,
  ...over,
});

function renderOverview() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ContestOverview slug="spring-cup" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authState.status = "authenticated";
  useContest.mockReturnValue({ isPending: false, isError: false, data: contest() });
  registerForContest.mockReset().mockResolvedValue(undefined);
});

describe("ContestOverview", () => {
  it("shows the description, phase and problem list once running", () => {
    renderOverview();
    expect(screen.getByText("Welcome!")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Two Sum" })).toHaveAttribute("href", "/contests/spring-cup/A");
  });

  it("hides the problem list before the contest starts", () => {
    useContest.mockReturnValue({
      isPending: false,
      isError: false,
      data: contest({ phase: "upcoming", problems: [{ label: "A", points: 100, title: null }] }),
    });
    renderOverview();
    expect(screen.getByText(/hidden until the contest starts/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Two Sum" })).not.toBeInTheDocument();
  });

  it("registers a signed-in user", async () => {
    renderOverview();
    await userEvent.click(screen.getByRole("button", { name: "Register" }));
    expect(registerForContest).toHaveBeenCalledWith("spring-cup");
  });

  it("shows Registered once the server confirms it, instead of a button", () => {
    useContest.mockReturnValue({ isPending: false, isError: false, data: contest({ registered: true }) });
    renderOverview();
    expect(screen.getByText("Registered")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Register" })).not.toBeInTheDocument();
  });

  it("asks an anonymous visitor to sign in instead of offering to register", () => {
    authState.status = "anonymous";
    renderOverview();
    expect(screen.getByRole("link", { name: "Sign in to register" })).toHaveAttribute("href", "/login?next=/contests/spring-cup");
    expect(screen.queryByRole("button", { name: "Register" })).not.toBeInTheDocument();
  });

  it("never offers to register once the contest has ended", () => {
    useContest.mockReturnValue({ isPending: false, isError: false, data: contest({ phase: "ended", registered: false }) });
    renderOverview();
    expect(screen.queryByRole("button", { name: "Register" })).not.toBeInTheDocument();
  });
});
