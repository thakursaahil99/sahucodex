import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ActivityDay } from "@/lib/profiles/types";
import { cn } from "@/lib/utils";

const DAY_MS = 86_400_000;
const WEEKS_SHOWN = 53;
const LEVEL_CLASS = ["bg-muted", "bg-brand-cyan/25", "bg-brand-cyan/50", "bg-brand-cyan/75", "bg-brand-cyan"];

function levelFor(count: number): number {
  if (count <= 0) return 0;
  if (count === 1) return 1;
  if (count <= 3) return 2;
  if (count <= 6) return 3;
  return 4;
}

interface Cell {
  date: string;
  count: number;
  inRange: boolean;
}

/** The last ~53 weeks, Sunday-first, as a flat array ordered so `grid-auto-flow: column` lays out one column per
 * week (7 rows) — exactly GitHub's contribution-graph shape, without a charting library. */
function buildGrid(activity: ActivityDay[]): Cell[] {
  const counts = new Map(activity.map((d) => [d.date, d.count]));
  const now = new Date();
  const todayUTC = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const totalDays = WEEKS_SHOWN * 7;
  const start = todayUTC - (totalDays - 1) * DAY_MS;
  const gridStart = start - new Date(start).getUTCDay() * DAY_MS; // back up to the preceding Sunday

  const cells: Cell[] = [];
  for (let time = gridStart; time <= todayUTC; time += DAY_MS) {
    const iso = new Date(time).toISOString().slice(0, 10);
    cells.push({ date: iso, count: counts.get(iso) ?? 0, inRange: time >= start });
  }
  return cells;
}

export function ActivityCalendar({ activity }: { activity: ActivityDay[] }) {
  const cells = buildGrid(activity);
  const weeks = Math.ceil(cells.length / 7);
  const total = activity.reduce((sum, day) => sum + day.count, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-muted-foreground">
          {total} submission{total === 1 ? "" : "s"} in the last year
        </p>
        <div className="overflow-x-auto pb-1">
          <div
            className="grid w-fit grid-flow-col gap-[3px]"
            style={{ gridTemplateRows: "repeat(7, 0.65rem)", gridTemplateColumns: `repeat(${weeks}, 0.65rem)` }}
            role="img"
            aria-label={`Activity calendar: ${total} submission${total === 1 ? "" : "s"} in the last year`}
          >
            {cells.map((cell) => (
              <div
                key={cell.date}
                title={cell.inRange ? `${cell.count} submission${cell.count === 1 ? "" : "s"} on ${cell.date}` : undefined}
                className={cn("rounded-[2px]", cell.inRange ? LEVEL_CLASS[levelFor(cell.count)] : "bg-transparent")}
              />
            ))}
          </div>
        </div>
        <div className="mt-2 flex items-center justify-end gap-1 text-xs text-muted-foreground" aria-hidden>
          Less
          {LEVEL_CLASS.map((cls) => (
            <span key={cls} className={cn("size-2.5 rounded-[2px]", cls)} />
          ))}
          More
        </div>
      </CardContent>
    </Card>
  );
}
