/** Response shapes of the contest API (see apps/api/app/modules/contests/schemas.py). */

import type { Example, Tag } from "@/lib/problems/types";

export type ContestPhase = "upcoming" | "running" | "ended";

export interface ContestProblemRef {
  label: string;
  points: number;
  /** Withheld (null) until the contest starts. */
  title: string | null;
}

export interface ContestListItem {
  slug: string;
  title: string;
  start_time: string;
  end_time: string;
  phase: ContestPhase;
  problem_count: number;
}

export interface ContestDetail extends ContestListItem {
  description: string;
  penalty_minutes: number;
  problems: ContestProblemRef[];
  registered: boolean;
}

/** The public, contest-scoped shape of a problem — the same safe fields as the plain problem API, minus the
 * per-user extras (solved status, editorial) that don't make sense mid-contest. */
export interface ContestProblemDetail {
  id: string;
  slug: string;
  title: string;
  difficulty: "EASY" | "MEDIUM" | "HARD";
  description: string;
  constraints: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  function_signature: string | null;
  tags: Tag[];
  examples: Example[];
  starter_code: Record<string, string>;
}

export interface ContestProblemOut {
  label: string;
  points: number;
  problem: ContestProblemDetail;
}

export interface StandingsCell {
  solved: boolean;
  attempts: number;
  penalty_minutes: number;
}

export interface StandingsRow {
  rank: number;
  username: string;
  total_points: number;
  total_penalty_minutes: number;
  cells: Record<string, StandingsCell>;
}

export interface StandingsOut {
  generated_at: string;
  problems: ContestProblemRef[];
  rows: StandingsRow[];
}

// --- admin ---------------------------------------------------------------------------------------------------------

export interface ContestAdminProblemInput {
  problem_slug: string;
  label: string;
  points: number;
}

export interface ContestAdminInput {
  slug: string;
  title: string;
  description: string;
  start_time: string;
  end_time: string;
  penalty_minutes: number;
  problems: ContestAdminProblemInput[];
}

export interface ContestAdminProblemOut {
  label: string;
  points: number;
  problem_slug: string;
  problem_title: string;
}

export interface ContestAdminOut {
  id: string;
  slug: string;
  title: string;
  description: string;
  start_time: string;
  end_time: string;
  penalty_minutes: number;
  published: boolean;
  problems: ContestAdminProblemOut[];
  created_at: string;
  updated_at: string;
}
