import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardView } from "@/components/dashboard/dashboard-view";
import type { User } from "@/lib/api/types";
import { useAuthStore } from "@/lib/auth/store";
import type { ProfileStats } from "@/lib/profiles/types";
import { sampleUser } from "@/test-utils";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/client", () => ({ api: vi.fn().mockResolvedValue({}) }));

const useMe = vi.fn((): { data: User | undefined } => ({ data: sampleUser }));
const useSessions = vi.fn(() => ({ data: [], isPending: false, isError: false, refetch: vi.fn() }));
vi.mock("@/lib/api/hooks", () => ({
  useMe: () => useMe(),
  useSessions: () => useSessions(),
}));

let statsResult: { data?: ProfileStats; isPending: boolean };
const useProfileStats = vi.fn((): typeof statsResult => statsResult);
vi.mock("@/lib/profiles/api", () => ({ useProfileStats: () => useProfileStats() }));

const stats = (over: Partial<ProfileStats> = {}): ProfileStats => ({
  solved: { easy: 1, medium: 0, hard: 0, total: 1 },
  total_submissions: 3,
  accepted_submissions: 1,
  acceptance_rate: 33.3,
  streak: { current: 1, longest: 1, last_active_date: "2026-01-01" },
  achievements: [
    { key: "first_solve", name: "First Blood", description: "d", icon: "Sparkles", earned: true, earned_at: "2026-01-01T00:00:00Z" },
    { key: "ten_solved", name: "Problem Solver", description: "d", icon: "Trophy", earned: false, earned_at: null },
  ],
  activity: [],
  ...over,
});

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useMe.mockReturnValue({ data: sampleUser });
  useAuthStore.setState({ status: "authenticated", accessToken: "t", user: sampleUser, expiresAt: Date.now() + 900_000 });
  statsResult = { data: stats(), isPending: false };
});

describe("DashboardView", () => {
  it("shows a loading skeleton until the user is known", () => {
    useMe.mockReturnValue({ data: undefined });
    useAuthStore.setState({ status: "loading", accessToken: null, user: null, expiresAt: null });
    renderDashboard();
    expect(screen.getByRole("status", { name: "Loading dashboard" })).toBeInTheDocument();
  });

  it("links to the signed-in user's own public profile", () => {
    renderDashboard();
    expect(screen.getByRole("link", { name: "View public profile" })).toHaveAttribute("href", `/profile/${sampleUser.username}`);
  });

  it("marks 'solve your first problem' done once the user has solved something", () => {
    renderDashboard();
    const step = screen.getByText("Solve your first problem").closest("li")!;
    expect(step).toHaveTextContent("You've solved 1 problem.");
    expect(step.querySelector(".lucide-circle-check-big, .lucide-circle-check")).not.toBeNull();
  });

  it("still points new users at the problem list", () => {
    statsResult = { data: stats({ solved: { easy: 0, medium: 0, hard: 0, total: 0 } }), isPending: false };
    renderDashboard();
    const step = screen.getByText("Solve your first problem").closest("li")!;
    expect(step).toHaveTextContent("Pick one from the problem list");
    expect(step.querySelector("a[href='/problems']")).not.toBeNull();
  });

  it("shows solved, streak and achievement summaries once stats load", () => {
    renderDashboard();
    const solvedCard = screen.getByText("Solved problems").closest('[data-slot="card"]')!;
    expect(solvedCard).toHaveTextContent("1"); // solved total
    expect(screen.getByText("1 of 2 earned")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See all achievements" })).toHaveAttribute(
      "href",
      `/profile/${sampleUser.username}`,
    );
  });

  it("shows nothing stats-related while stats are still loading, without crashing", () => {
    statsResult = { data: undefined, isPending: true };
    renderDashboard();
    expect(screen.queryByText(/earned/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Welcome back/ })).toBeInTheDocument();
  });

  it("no longer lists progress/profile as upcoming, now that phase 4 has shipped", () => {
    renderDashboard();
    expect(screen.queryByText("Progress and profile")).not.toBeInTheDocument();
  });

  it("no longer lists SahuCodeX AI as upcoming, now that phase 5 has shipped", () => {
    renderDashboard();
    expect(screen.queryByText("SahuCodeX AI")).not.toBeInTheDocument();
    expect(screen.getByText("Contests")).toBeInTheDocument(); // what is genuinely still to come
  });
});
