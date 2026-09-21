import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DifficultyCounts } from "@/lib/profiles/types";
import { cn } from "@/lib/utils";

const ROWS: Array<{ key: keyof Omit<DifficultyCounts, "total">; label: string; bar: string; text: string }> = [
  { key: "easy", label: "Easy", bar: "bg-success", text: "text-success" },
  { key: "medium", label: "Medium", bar: "bg-warning", text: "text-warning" },
  { key: "hard", label: "Hard", bar: "bg-destructive", text: "text-destructive" },
];

export function SolvedBreakdown({
  solved,
  totalSubmissions,
  acceptanceRate,
}: {
  solved: DifficultyCounts;
  totalSubmissions: number;
  acceptanceRate: number | null;
}) {
  const max = Math.max(solved.easy, solved.medium, solved.hard, 1);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Solved problems</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-3xl font-bold tabular-nums">{solved.total}</p>
        <div className="space-y-2.5">
          {ROWS.map(({ key, label, bar, text }) => (
            <div key={key} className="flex items-center gap-2.5 text-sm">
              <span className={cn("w-16 shrink-0 font-medium", text)}>{label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted" role="presentation">
                <div className={cn("h-full rounded-full", bar)} style={{ width: `${(solved[key] / max) * 100}%` }} />
              </div>
              <span className="w-8 shrink-0 text-right tabular-nums text-muted-foreground">{solved[key]}</span>
            </div>
          ))}
        </div>
        <dl className="grid grid-cols-2 gap-3 border-t pt-4 text-sm">
          <div>
            <dt className="text-muted-foreground">Submissions</dt>
            <dd className="font-medium tabular-nums">{totalSubmissions}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Acceptance</dt>
            <dd className="font-medium tabular-nums">{acceptanceRate === null ? "—" : `${acceptanceRate}%`}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
