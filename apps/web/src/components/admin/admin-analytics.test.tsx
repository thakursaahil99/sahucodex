import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AdminAnalytics } from "@/components/admin/admin-analytics";
import type { Analytics } from "@/lib/admin/api";

let result: { data?: Analytics; isPending: boolean; isError: boolean; refetch: () => void };
const useAnalytics = vi.fn(() => result);
vi.mock("@/lib/admin/api", () => ({ useAnalytics: () => useAnalytics() }));

const analytics = (over: Partial<Analytics> = {}): Analytics => ({
  platform: {
    users: 12,
    published_problems: 30,
    submissions: 500,
    submissions_last_30d: 40,
    published_contests: 2,
    discussions: 8,
  },
  ai_usage: {
    window_days: 30,
    total_requests: 10,
    failed_requests: 2,
    by_feature: [
      { feature: "chat", requests: 6, failed: 1, avg_duration_ms: 1200, avg_response_chars: 300 },
      { feature: "hint", requests: 4, failed: 1, avg_duration_ms: 800, avg_response_chars: 100 },
    ],
  },
  ...over,
});

describe("AdminAnalytics", () => {
  it("shows a loading state", () => {
    result = { data: undefined, isPending: true, isError: false, refetch: vi.fn() };
    const { container } = render(<AdminAnalytics />);
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it("shows an error state with a retry", () => {
    result = { data: undefined, isPending: false, isError: true, refetch: vi.fn() };
    render(<AdminAnalytics />);
    expect(screen.getByText("Couldn't load analytics.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows platform totals and AI usage by feature", () => {
    result = { data: analytics(), isPending: false, isError: false, refetch: vi.fn() };
    render(<AdminAnalytics />);
    expect(screen.getByText("30")).toBeInTheDocument(); // published_problems
    expect(screen.getByText("10", { exact: true })).toBeInTheDocument(); // total AI requests
    expect(screen.getByText("chat")).toBeInTheDocument();
    expect(screen.getByText("hint")).toBeInTheDocument();
  });

  it("shows a no-usage message when there are no AI requests in the window", () => {
    result = {
      data: analytics({ ai_usage: { window_days: 30, total_requests: 0, failed_requests: 0, by_feature: [] } }),
      isPending: false,
      isError: false,
      refetch: vi.fn(),
    };
    render(<AdminAnalytics />);
    expect(screen.getByText("No AI requests in this window.")).toBeInTheDocument();
  });
});
