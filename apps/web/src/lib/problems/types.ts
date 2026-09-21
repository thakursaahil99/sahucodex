/** Response shapes of the public problem API (see apps/api/app/modules/problems/schemas.py). */

export type Difficulty = "EASY" | "MEDIUM" | "HARD";
export type ProgressStatus = "SOLVED" | "ATTEMPTED";

export interface Tag {
  name: string;
  slug: string;
}

export interface TagWithCount extends Tag {
  problem_count: number;
}

export interface Language {
  key: string;
  display_name: string;
  editor_language: string;
  file_extension: string;
}

export interface ProblemListItem {
  slug: string;
  title: string;
  difficulty: Difficulty;
  tags: Tag[];
  acceptance_rate: number | null;
  total_submissions: number;
  status: ProgressStatus | null;
}

export interface Example {
  input: string;
  output: string;
  explanation: string | null;
}

export interface ProblemDetail {
  id: string;
  slug: string;
  title: string;
  difficulty: Difficulty;
  description: string;
  constraints: string;
  input_format: string;
  output_format: string;
  time_limit_ms: number;
  memory_limit_mb: number;
  function_signature: string | null;
  tags: Tag[];
  examples: Example[];
  hint_count: number;
  starter_code: Record<string, string>;
  acceptance_rate: number | null;
  total_submissions: number;
  status: ProgressStatus | null;
  solution_unlocked: boolean;
  editorial: string | null;
  expected_time_complexity: string | null;
  expected_space_complexity: string | null;
}

export interface Hint {
  index: number;
  total: number;
  hint: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}
