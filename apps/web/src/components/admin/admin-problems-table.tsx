"use client";

import { FilePlus2, Pencil, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { DifficultyBadge } from "@/components/problems/difficulty-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminProblems } from "@/lib/admin/api";
import type { ProblemStatus } from "@/lib/admin/problem-form";
import { formatDate } from "@/lib/utils";

const STATUS_VARIANT = { PUBLISHED: "success", DRAFT: "warning", ARCHIVED: "outline" } as const;

export function AdminProblemsTable() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const status = (["DRAFT", "PUBLISHED", "ARCHIVED"].includes(params.get("status") ?? "") ? params.get("status") : "") as
    | ProblemStatus
    | "";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const [search, setSearch] = useState(q);

  const { data, isPending, isError, refetch } = useAdminProblems({ page, q, status });

  function go(next: { status?: string; q?: string; page?: number }) {
    const merged = new URLSearchParams();
    const s = next.status ?? status;
    const query = next.q ?? q;
    const p = next.page ?? 1;
    if (s) merged.set("status", s);
    if (query) merged.set("q", query);
    if (p > 1) merged.set("page", String(p));
    router.replace(merged.size ? `${pathname}?${merged}` : pathname);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Problems</h1>
          <p className="mt-1 text-muted-foreground">Create, edit, publish and archive problems.</p>
        </div>
        <Button asChild variant="gradient">
          <Link href="/admin/problems/new">
            <FilePlus2 aria-hidden /> New problem
          </Link>
        </Button>
      </div>

      <form
        className="flex flex-col gap-3 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          go({ q: search.trim() });
        }}
        role="search"
      >
        <div className="relative flex-1">
          <label htmlFor="admin-search" className="sr-only">
            Search by title or slug
          </label>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            id="admin-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by title or slug…"
            className="h-10 w-full rounded-lg border border-input bg-transparent pr-3 pl-9 text-sm focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none"
          />
        </div>
        <div className="sm:w-48">
          <label htmlFor="admin-status" className="sr-only">
            Status
          </label>
          <Select id="admin-status" value={status} onChange={(e) => go({ status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="PUBLISHED">Published</option>
            <option value="DRAFT">Drafts</option>
            <option value="ARCHIVED">Archived</option>
          </Select>
        </div>
        <Button type="submit" variant="outline">
          Search
        </Button>
      </form>

      {isPending && (
        <div className="space-y-2" role="status" aria-label="Loading problems">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      )}
      {isError && (
        <div role="alert" className="flex items-center justify-between rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm">
          Couldn&apos;t load problems.
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center">
          <p className="font-medium">No problems found</p>
          <p className="mt-1 text-sm text-muted-foreground">Try a different filter, or create the first one.</p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[42rem] text-sm">
            <caption className="sr-only">Problems</caption>
            <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">Title</th>
                <th scope="col" className="px-4 py-3 font-medium">Status</th>
                <th scope="col" className="px-4 py-3 font-medium">Difficulty</th>
                <th scope="col" className="px-4 py-3 font-medium">Tests</th>
                <th scope="col" className="px-4 py-3 font-medium">Updated</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((problem) => (
                <tr key={problem.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Link href={`/admin/problems/${problem.id}/edit`} className="font-medium hover:underline">
                      {problem.title}
                    </Link>
                    <p className="font-mono text-xs text-muted-foreground">{problem.slug}</p>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[problem.status]}>{problem.status.toLowerCase()}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <DifficultyBadge difficulty={problem.difficulty} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {problem.public_tests} public · {problem.hidden_tests} hidden
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(problem.updated_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <Button asChild variant="ghost" size="sm">
                      <Link href={`/admin/problems/${problem.id}/edit`} aria-label={`Edit ${problem.title}`}>
                        <Pencil aria-hidden /> Edit
                      </Link>
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.pages > 1 && (
        <nav aria-label="Pagination" className="flex items-center justify-between">
          <Button variant="outline" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>
            Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {data.pages}
          </p>
          <Button variant="outline" disabled={page >= data.pages} onClick={() => go({ page: page + 1 })}>
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
