import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityCalendar } from "@/components/profiles/activity-calendar";

function todayIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())).toISOString().slice(0, 10);
}

describe("ActivityCalendar", () => {
  it("summarises the total and describes itself for screen readers", () => {
    render(<ActivityCalendar activity={[{ date: todayIso(), count: 3 }, { date: "2020-01-01", count: 2 }]} />);
    expect(screen.getByText("5 submissions in the last year")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /5 submissions in the last year/ })).toBeInTheDocument();
  });

  it("uses singular wording for exactly one submission", () => {
    render(<ActivityCalendar activity={[{ date: todayIso(), count: 1 }]} />);
    expect(screen.getByText("1 submission in the last year")).toBeInTheDocument();
  });

  it("shows an empty-but-present grid when there is no activity", () => {
    render(<ActivityCalendar activity={[]} />);
    expect(screen.getByText("0 submissions in the last year")).toBeInTheDocument();
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("labels today's cell with its count", () => {
    render(<ActivityCalendar activity={[{ date: todayIso(), count: 4 }]} />);
    const cell = document.querySelector(`[title*="${todayIso()}"]`);
    expect(cell).not.toBeNull();
    expect(cell).toHaveAttribute("title", `4 submissions on ${todayIso()}`);
  });

  it("does not render a titled cell for a day outside the one-year window", () => {
    render(<ActivityCalendar activity={[{ date: "2000-01-01", count: 9 }]} />);
    expect(document.querySelector('[title*="2000-01-01"]')).toBeNull();
  });
});
