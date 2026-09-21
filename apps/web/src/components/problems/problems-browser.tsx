"use client";

import { CheckCircle2, ChevronLeft, ChevronRight, Circle, CircleDashed, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { DifficultyBadge, difficultyLabel } from "@/components/problems/difficulty-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/lib/auth/store";
import { useProblemList, useTags } from "@/lib/problems/api";
import {
  ACCEPTANCE_BUCKETS,
  DIFFICULTIES,
  effectiveSort,
  filtersToSearchParams,
  hasActiveFilters,
  parseFilters,
  type AcceptanceBucket,
  type ProblemFilters,
  type SortKey,
  type StatusFilter,
} from "@/lib/problems/filters";
import type { ProblemListItem } from "@/lib/problems/types";
import { cn } from "@/lib/utils";

const COLLAPSED_TAGS = 12;

export function ProblemsBrowser() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const signedIn = useAuthStore((s) => s.status === "authenticated");

  const { data, isPending, isError, isFetching, refetch } = useProblemList(filters);
  const { data: tags } = useTags();
  const [showAllTags, setShowAllTags] = useState(false);
  // "Clear all" remounts the search box, seeded empty (the URL still holds the old query for a moment).
  const [searchSeed, setSearchSeed] = useState<{ key: number; value: string | null }>({ key: 0, value: null });

  function clearAll() {
    setSearchSeed((seed) => ({ key: seed.key + 1, value: "" }));
    router.replace(pathname, { scroll: false });
  }

  function update(changes: Partial<ProblemFilters>, resetPage = true) {
    const next = { ...filters, ...changes, page: resetPage ? 1 : (changes.page ?? filters.page) };
    const query = filtersToSearchParams(next).toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  const toggle = <T extends string>(list: T[], value: T): T[] =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value];

  const visibleTags = useMemo(() => {
    if (!tags) return [];
    if (showAllTags) return tags;
    return tags.filter((tag, index) => index < COLLAPSED_TAGS || filters.tags.includes(tag.slug));
  }, [tags, showAllTags, filters.tags]);

  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Problems</h1>
          <p className="mt-1 text-muted-foreground" aria-live="polite">
            {isPending ? "Loading problems…" : `${total} ${total === 1 ? "problem" : "problems"}${hasActiveFilters(filters) ? " match your filters" : ""}`}
          </p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
        {/* Only remounted by "Clear all" (a key change would steal focus mid-typing). */}
        <SearchBox key={searchSeed.key} initial={searchSeed.value ?? filters.q} applied={filters.q} onCommit={(q) => update({ q })} />
        <div className="md:w-52">
          <label className="sr-only" htmlFor="sort">
            Sort by
          </label>
          <Select id="sort" value={effectiveSort(filters)} onChange={(e) => update({ sort: e.target.value as SortKey })}>
            {filters.q && <option value="relevance">Best match</option>}
            <option value="newest">Newest</option>
            <option value="title">Title (A–Z)</option>
            <option value="difficulty">Difficulty</option>
            <option value="acceptance">Acceptance rate</option>
          </Select>
        </div>
        <div className="md:w-56">
          <label className="sr-only" htmlFor="acceptance">
            Acceptance rate
          </label>
          <Select
            id="acceptance"
            value={filters.acceptance}
            onChange={(e) => update({ acceptance: e.target.value as AcceptanceBucket })}
          >
            <option value="">Any acceptance rate</option>
            {Object.entries(ACCEPTANCE_BUCKETS).map(([key, bucket]) => (
              <option key={key} value={key}>
                {bucket.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="space-y-4 rounded-xl border bg-card p-4">
        <fieldset>
          <legend className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Difficulty</legend>
          <div className="flex flex-wrap gap-2">
            {DIFFICULTIES.map((difficulty) => (
              <FilterChip
                key={difficulty}
                pressed={filters.difficulties.includes(difficulty)}
                onClick={() => update({ difficulties: toggle(filters.difficulties, difficulty) })}
              >
                {difficultyLabel(difficulty)}
              </FilterChip>
            ))}
            {signedIn && (
              <>
                <span className="mx-1 hidden w-px bg-border sm:block" aria-hidden />
                {(["solved", "unsolved", "attempted"] as const).map((status) => (
                  <FilterChip
                    key={status}
                    pressed={filters.status === status}
                    onClick={() => update({ status: (filters.status === status ? "" : status) as StatusFilter })}
                  >
                    {status[0]!.toUpperCase() + status.slice(1)}
                  </FilterChip>
                ))}
              </>
            )}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Topics</legend>
          <div className="flex flex-wrap gap-2">
            {!tags && Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-8 w-24 rounded-full" />)}
            {visibleTags.map((tag) => (
              <FilterChip
                key={tag.slug}
                pressed={filters.tags.includes(tag.slug)}
                onClick={() => update({ tags: toggle(filters.tags, tag.slug) })}
              >
                {tag.name}
                <span className="ml-1 text-xs opacity-60">{tag.problem_count}</span>
              </FilterChip>
            ))}
            {tags && tags.length > COLLAPSED_TAGS && (
              <Button variant="ghost" size="sm" onClick={() => setShowAllTags((v) => !v)}>
                {showAllTags ? "Show fewer" : `Show all ${tags.length} topics`}
              </Button>
            )}
          </div>
        </fieldset>

        {hasActiveFilters(filters) && (
          <Button variant="ghost" size="sm" onClick={clearAll}>
            <X aria-hidden /> Clear all filters
          </Button>
        )}
      </div>

      <div aria-busy={isFetching} className={cn("transition-opacity", isFetching && !isPending && "opacity-60")}>
        {isPending && <ListSkeleton />}
        {isError && (
          <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm">
            <span>Couldn&apos;t load problems. Check your connection and try again.</span>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}
        {data && data.items.length === 0 && (
          <EmptyState filtered={hasActiveFilters(filters)} onClear={clearAll} />
        )}
        {data && data.items.length > 0 && (
          <ul className="divide-y overflow-hidden rounded-xl border bg-card" aria-label="Problems">
            {data.items.map((problem) => (
              <ProblemRow key={problem.slug} problem={problem} />
            ))}
          </ul>
        )}
      </div>

      {data && data.pages > 1 && (
        <nav aria-label="Pagination" className="flex items-center justify-between gap-3">
          <Button variant="outline" disabled={filters.page <= 1} onClick={() => update({ page: filters.page - 1 }, false)}>
            <ChevronLeft aria-hidden /> Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {data.pages}
          </p>
          <Button variant="outline" disabled={filters.page >= data.pages} onClick={() => update({ page: filters.page + 1 }, false)}>
            Next <ChevronRight aria-hidden />
          </Button>
        </nav>
      )}
    </div>
  );
}

function SearchBox({ initial, applied, onCommit }: { initial: string; applied: string; onCommit: (q: string) => void }) {
  const [value, setValue] = useState(initial);
  const commit = useRef(onCommit);
  useEffect(() => {
    commit.current = onCommit;
  });

  // Debounce: wait for a pause in typing before touching the URL (and so the API).
  useEffect(() => {
    if (value.trim() === applied.trim()) return; // already what the URL says
    const timer = setTimeout(() => commit.current(value.trim()), 350);
    return () => clearTimeout(timer);
  }, [value, applied]);

  return (
    <div className="relative">
      <label className="sr-only" htmlFor="problem-search">
        Search problems
      </label>
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
      <input
        id="problem-search"
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search by title, description or topic…"
        maxLength={100}
        className="h-10 w-full rounded-lg border border-input bg-transparent pr-3 pl-9 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none"
      />
    </div>
  );
}

function FilterChip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex items-center rounded-full border px-3 py-1.5 text-sm transition-colors",
        pressed
          ? "border-brand-blue bg-brand-blue/15 text-foreground"
          : "text-muted-foreground hover:border-foreground/30 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function StatusIcon({ status }: { status: ProblemListItem["status"] }) {
  if (status === "SOLVED") return <CheckCircle2 className="size-5 text-success" aria-label="Solved" />;
  if (status === "ATTEMPTED") return <CircleDashed className="size-5 text-warning" aria-label="Attempted" />;
  return <Circle className="size-5 text-muted-foreground/40" aria-label="Not attempted" />;
}

function ProblemRow({ problem }: { problem: ProblemListItem }) {
  return (
    <li>
      <Link
        href={`/problems/${problem.slug}`}
        className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 p-4 transition-colors hover:bg-muted/50 sm:grid-cols-[auto_1fr_auto_5rem]"
      >
        <StatusIcon status={problem.status} />
        <div className="min-w-0">
          <p className="truncate font-medium">{problem.title}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {problem.tags.map((tag) => (
              <Badge key={tag.slug} variant="outline" className="font-normal">
                {tag.name}
              </Badge>
            ))}
          </div>
        </div>
        <div className="col-start-2 sm:col-start-auto">
          <DifficultyBadge difficulty={problem.difficulty} />
        </div>
        <p className="col-start-2 text-sm text-muted-foreground sm:col-start-auto sm:text-right" title="Acceptance rate">
          {problem.acceptance_rate === null ? "—" : `${problem.acceptance_rate}%`}
          <span className="sr-only"> acceptance</span>
        </p>
      </Link>
    </li>
  );
}

function ListSkeleton() {
  return (
    <div className="divide-y overflow-hidden rounded-xl border bg-card" role="status" aria-label="Loading problems">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="flex items-center gap-4 p-4">
          <Skeleton className="size-5 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-5 w-1/2" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ filtered, onClear }: { filtered: boolean; onClear: () => void }) {
  return (
    <div className="rounded-xl border border-dashed p-12 text-center">
      <p className="font-medium">{filtered ? "No problems match those filters" : "No problems have been published yet"}</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {filtered ? "Try removing a filter or searching for something broader." : "Check back soon."}
      </p>
      {filtered && (
        <Button variant="outline" className="mt-4" onClick={onClear}>
          Clear all filters
        </Button>
      )}
    </div>
  );
}
