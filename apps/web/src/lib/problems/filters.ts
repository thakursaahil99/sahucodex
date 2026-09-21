import type { Difficulty } from "@/lib/problems/types";

export const SORT_OPTIONS = ["newest", "title", "difficulty", "acceptance", "relevance"] as const;
export type SortKey = (typeof SORT_OPTIONS)[number];

export const STATUS_OPTIONS = ["solved", "unsolved", "attempted"] as const;
export type StatusFilter = (typeof STATUS_OPTIONS)[number] | "";

/** Acceptance-rate buckets shown in the UI; mapped to min/max percentages for the API. */
export const ACCEPTANCE_BUCKETS = {
  low: { label: "Hard to pass (under 30%)", max: 30 },
  mid: { label: "Typical (30–60%)", min: 30, max: 60 },
  high: { label: "Easy to pass (over 60%)", min: 60 },
} as const;
export type AcceptanceBucket = keyof typeof ACCEPTANCE_BUCKETS | "";

export const DIFFICULTIES: readonly Difficulty[] = ["EASY", "MEDIUM", "HARD"];
export const PAGE_SIZE = 20;

export interface ProblemFilters {
  q: string;
  difficulties: Difficulty[];
  tags: string[];
  status: StatusFilter;
  acceptance: AcceptanceBucket;
  sort: SortKey;
  page: number;
}

export const DEFAULT_FILTERS: ProblemFilters = {
  q: "",
  difficulties: [],
  tags: [],
  status: "",
  acceptance: "",
  sort: "newest",
  page: 1,
};

type ParamReader = { get(name: string): string | null; getAll(name: string): string[] };

function oneOf<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

/** Reads filters from the URL, discarding anything invalid so a hand-edited link can never break the page. */
export function parseFilters(params: ParamReader): ProblemFilters {
  const page = Number.parseInt(params.get("page") ?? "1", 10);
  const acceptance = params.get("acceptance");
  return {
    q: (params.get("q") ?? "").slice(0, 100),
    difficulties: params
      .getAll("difficulty")
      .filter((d): d is Difficulty => (DIFFICULTIES as readonly string[]).includes(d)),
    tags: [...new Set(params.getAll("tag").filter((t) => /^[a-z0-9-]{1,40}$/.test(t)))].slice(0, 10),
    status: oneOf(params.get("status"), STATUS_OPTIONS, "") as StatusFilter,
    acceptance: acceptance && acceptance in ACCEPTANCE_BUCKETS ? (acceptance as AcceptanceBucket) : "",
    sort: oneOf(params.get("sort"), SORT_OPTIONS, DEFAULT_FILTERS.sort),
    page: Number.isFinite(page) && page >= 1 && page <= 100_000 ? page : 1,
  };
}

/** Browser URL query for the filters; defaults are omitted to keep links short. */
export function filtersToSearchParams(filters: ProblemFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  filters.difficulties.forEach((d) => params.append("difficulty", d));
  filters.tags.forEach((t) => params.append("tag", t));
  if (filters.status) params.set("status", filters.status);
  if (filters.acceptance) params.set("acceptance", filters.acceptance);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

/** The effective sort: a text search is ranked by relevance unless the user chose another order. */
export function effectiveSort(filters: ProblemFilters): SortKey {
  if (filters.q && filters.sort === "newest") return "relevance";
  if (!filters.q && filters.sort === "relevance") return "newest";
  return filters.sort;
}

/** Query string for `GET /api/problems`. */
export function filtersToApiQuery(filters: ProblemFilters, limit = PAGE_SIZE): string {
  const params = new URLSearchParams();
  params.set("page", String(filters.page));
  params.set("limit", String(limit));
  if (filters.q) params.set("q", filters.q);
  filters.difficulties.forEach((d) => params.append("difficulty", d));
  filters.tags.forEach((t) => params.append("tag", t));
  if (filters.status) params.set("status", filters.status);
  if (filters.acceptance) {
    const bucket: { min?: number; max?: number } = ACCEPTANCE_BUCKETS[filters.acceptance];
    if (bucket.min !== undefined) params.set("min_acceptance", String(bucket.min));
    if (bucket.max !== undefined) params.set("max_acceptance", String(bucket.max));
  }
  params.set("sort", effectiveSort(filters));
  return params.toString();
}

export function hasActiveFilters(filters: ProblemFilters): boolean {
  return Boolean(
    filters.q || filters.difficulties.length || filters.tags.length || filters.status || filters.acceptance,
  );
}
