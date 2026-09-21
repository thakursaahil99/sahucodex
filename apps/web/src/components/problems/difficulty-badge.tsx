import { Badge } from "@/components/ui/badge";
import type { Difficulty } from "@/lib/problems/types";

const LABELS: Record<Difficulty, string> = { EASY: "Easy", MEDIUM: "Medium", HARD: "Hard" };
const VARIANTS = { EASY: "success", MEDIUM: "warning", HARD: "secondary" } as const;

/** Text label plus colour, so difficulty never relies on colour alone. */
export function DifficultyBadge({ difficulty }: { difficulty: Difficulty }) {
  return <Badge variant={VARIANTS[difficulty]}>{LABELS[difficulty]}</Badge>;
}

export const difficultyLabel = (difficulty: Difficulty) => LABELS[difficulty];
