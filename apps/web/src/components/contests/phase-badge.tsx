import { Badge } from "@/components/ui/badge";
import type { ContestPhase } from "@/lib/contests/types";

const LABEL: Record<ContestPhase, string> = { upcoming: "Upcoming", running: "Running", ended: "Ended" };
const VARIANT: Record<ContestPhase, "accent" | "success" | "secondary"> = {
  upcoming: "accent",
  running: "success",
  ended: "secondary",
};

export function PhaseBadge({ phase }: { phase: ContestPhase }) {
  return <Badge variant={VARIANT[phase]}>{LABEL[phase]}</Badge>;
}
