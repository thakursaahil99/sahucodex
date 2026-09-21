import { Lock } from "lucide-react";

import { AchievementIcon } from "@/components/profiles/achievement-icon";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { AchievementInfo } from "@/lib/profiles/types";
import { formatDate } from "@/lib/utils";

export function AchievementsGrid({ achievements }: { achievements: AchievementInfo[] }) {
  const earnedCount = achievements.filter((a) => a.earned).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Achievements <span className="font-normal text-muted-foreground">({earnedCount}/{achievements.length})</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {achievements.map((achievement) => (
            <li
              key={achievement.key}
              className={
                achievement.earned
                  ? "flex flex-col items-center gap-1.5 rounded-xl border border-brand-cyan/30 bg-brand-cyan/5 p-3 text-center"
                  : "flex flex-col items-center gap-1.5 rounded-xl border border-dashed p-3 text-center opacity-60"
              }
              title={achievement.earned && achievement.earned_at ? `Earned ${formatDate(achievement.earned_at)}` : undefined}
            >
              {achievement.earned ? (
                <AchievementIcon name={achievement.icon} className="size-7 text-brand-cyan" />
              ) : (
                <Lock className="size-7 text-muted-foreground" aria-hidden />
              )}
              <p className="text-xs font-medium">{achievement.name}</p>
              <p className="text-[11px] text-muted-foreground">{achievement.description}</p>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
