import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AchievementsGrid } from "@/components/profiles/achievements-grid";
import type { AchievementInfo } from "@/lib/profiles/types";

const achievements: AchievementInfo[] = [
  { key: "first_solve", name: "First Blood", description: "Solve your first problem.", icon: "Sparkles", earned: true, earned_at: "2026-01-01T00:00:00Z" },
  { key: "ten_solved", name: "Problem Solver", description: "Solve 10 problems.", icon: "Trophy", earned: false, earned_at: null },
];

describe("AchievementsGrid", () => {
  it("shows the earned count and every achievement's name and description", () => {
    render(<AchievementsGrid achievements={achievements} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Achievements (1/2)");
    expect(screen.getByText("First Blood")).toBeInTheDocument();
    expect(screen.getByText("Solve 10 problems.")).toBeInTheDocument();
  });

  it("gives an earned achievement its earned date as a tooltip, and a locked one none", () => {
    render(<AchievementsGrid achievements={achievements} />);
    const earned = screen.getByText("First Blood").closest("li");
    const locked = screen.getByText("Problem Solver").closest("li");
    expect(earned).toHaveAttribute("title");
    expect(locked).not.toHaveAttribute("title");
  });

  it("shows a lock icon in place of the achievement's own icon while locked", () => {
    const { container } = render(<AchievementsGrid achievements={achievements} />);
    const locked = screen.getByText("Problem Solver").closest("li")!;
    expect(locked.querySelector(".lucide-lock")).not.toBeNull();
    const earned = screen.getByText("First Blood").closest("li")!;
    expect(earned.querySelector(".lucide-lock")).toBeNull();
    expect(container.querySelectorAll("svg")).toHaveLength(2);
  });
});
