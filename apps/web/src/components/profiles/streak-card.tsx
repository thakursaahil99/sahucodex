import { Flame } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { StreakInfo } from "@/lib/profiles/types";

/** Streaks reset at UTC midnight — see docs/database.md. */
export function StreakCard({ streak }: { streak: StreakInfo }) {
  const active = streak.current > 0;
  return (
    <Card>
      <CardContent className="flex items-center gap-4 py-5">
        <Flame
          className={active ? "size-9 text-warning" : "size-9 text-muted-foreground/40"}
          aria-hidden
          fill={active ? "currentColor" : "none"}
        />
        <div>
          <p className="text-2xl font-bold tabular-nums">
            {streak.current} <span className="text-sm font-normal text-muted-foreground">day{streak.current === 1 ? "" : "s"}</span>
          </p>
          <p className="text-xs text-muted-foreground">
            Current streak · Longest {streak.longest} day{streak.longest === 1 ? "" : "s"}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
