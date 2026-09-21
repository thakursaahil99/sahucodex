import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileView } from "@/components/profiles/profile-view";
import { ApiError } from "@/lib/api/http";
import type { ProfileStats, PublicProfile } from "@/lib/profiles/types";

let profileResult: { data?: PublicProfile; isPending: boolean; isError: boolean; error?: unknown; refetch: () => void };
let statsResult: { data?: ProfileStats; isPending: boolean; isError: boolean; error?: unknown; refetch: () => void };
const useProfile = vi.fn(() => profileResult);
const useProfileStats = vi.fn(() => statsResult);
vi.mock("@/lib/profiles/api", () => ({
  useProfile: () => useProfile(),
  useProfileStats: () => useProfileStats(),
}));

const profile = (over: Partial<PublicProfile> = {}): PublicProfile => ({
  username: "ada",
  avatar_url: null,
  bio: "I like graphs.",
  country: "IN",
  website: "https://ada.dev",
  github_url: "https://github.com/ada",
  joined_at: "2026-01-01T00:00:00Z",
  ...over,
});

const stats = (over: Partial<ProfileStats> = {}): ProfileStats => ({
  solved: { easy: 3, medium: 2, hard: 1, total: 6 },
  total_submissions: 10,
  accepted_submissions: 6,
  acceptance_rate: 60,
  streak: { current: 2, longest: 5, last_active_date: "2026-01-05" },
  achievements: [
    { key: "first_solve", name: "First Blood", description: "Solve your first problem.", icon: "Sparkles", earned: true, earned_at: "2026-01-01T00:00:00Z" },
  ],
  activity: [{ date: "2026-01-05", count: 2 }],
  ...over,
});

beforeEach(() => {
  profileResult = { data: profile(), isPending: false, isError: false, refetch: vi.fn() };
  statsResult = { data: stats(), isPending: false, isError: false, refetch: vi.fn() };
});

describe("ProfileView", () => {
  it("shows the header: username, bio, country, links and join date", () => {
    render(<ProfileView username="ada" />);
    expect(screen.getByRole("heading", { name: "ada" })).toBeInTheDocument();
    expect(screen.getByText("I like graphs.")).toBeInTheDocument();
    expect(screen.getByText("IN")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Website/ })).toHaveAttribute("href", "https://ada.dev");
    expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute("href", "https://github.com/ada");
    expect(screen.getByText(/Joined/)).toBeInTheDocument();
  });

  it("omits optional links and fields that are not set", () => {
    profileResult.data = profile({ bio: null, country: null, website: null, github_url: null });
    render(<ProfileView username="ada" />);
    expect(screen.queryByRole("link", { name: /Website/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /GitHub/ })).not.toBeInTheDocument();
  });

  it("shows solved counts, streak and achievements", () => {
    render(<ProfileView username="ada" />);
    expect(screen.getByText("6")).toBeInTheDocument(); // solved total
    expect(screen.getByText(/Longest 5 days/)).toBeInTheDocument();
    expect(screen.getByText("First Blood")).toBeInTheDocument();
  });

  it("shows a loading skeleton while either query is pending", () => {
    statsResult = { ...statsResult, data: undefined, isPending: true };
    render(<ProfileView username="ada" />);
    expect(screen.getByRole("status", { name: "Loading profile" })).toBeInTheDocument();
  });

  it("shows a not-found message for a missing user", () => {
    profileResult = {
      ...profileResult,
      data: undefined,
      isError: true,
      error: new ApiError(404, "USER_NOT_FOUND", "not found"),
    };
    render(<ProfileView username="no-such-user" />);
    expect(screen.getByRole("heading", { name: "User not found" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("offers a retry for a generic failure, and refetches both queries", async () => {
    profileResult = { ...profileResult, data: undefined, isError: true, error: new ApiError(500, "SERVER_ERROR", "boom") };
    render(<ProfileView username="ada" />);
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(profileResult.refetch).toHaveBeenCalledTimes(1);
    expect(statsResult.refetch).toHaveBeenCalledTimes(1);
  });
});
