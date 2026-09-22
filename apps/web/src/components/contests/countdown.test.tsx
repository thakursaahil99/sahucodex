import { render, screen } from "@testing-library/react";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Countdown } from "@/components/contests/countdown";

describe("Countdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a placeholder until the first tick, then counts down hh:mm:ss", () => {
    render(<Countdown target="2026-01-01T01:02:03Z" />);
    expect(screen.getByText("—:—:—")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1000)); // one second has now genuinely elapsed
    expect(screen.getByText("01:02:02")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByText("01:01:59")).toBeInTheDocument();
  });

  it("switches to a day-based format beyond 24 hours", () => {
    render(<Countdown target="2026-01-03T05:00:00Z" />);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("2d 04h 59m")).toBeInTheDocument();
  });

  it("never shows negative time once the target has passed", () => {
    render(<Countdown target="2025-12-31T23:59:59Z" />);
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("00:00:00")).toBeInTheDocument();
  });

  it("calls onReach exactly once, on the tick the target is crossed", () => {
    const onReach = vi.fn();
    render(<Countdown target="2026-01-01T00:00:02Z" onReach={onReach} />);

    act(() => vi.advanceTimersByTime(1000)); // t=1s, not there yet
    expect(onReach).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1000)); // t=2s, target reached
    expect(onReach).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(2000)); // still reached, must not fire again
    expect(onReach).toHaveBeenCalledTimes(1);
  });
});
