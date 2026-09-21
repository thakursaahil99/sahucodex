"use client";

import { FilePlus2, FileText, Archive, CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminCount } from "@/lib/admin/api";
import type { ProblemStatus } from "@/lib/admin/problem-form";

const TILES: Array<{ status: ProblemStatus; label: string; hint: string; Icon: typeof FileText }> = [
  { status: "PUBLISHED", label: "Published", hint: "Visible to learners", Icon: CheckCircle2 },
  { status: "DRAFT", label: "Drafts", hint: "Work in progress", Icon: FileText },
  { status: "ARCHIVED", label: "Archived", hint: "Hidden, restorable", Icon: Archive },
];

export function AdminOverview() {
  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Admin</h1>
          <p className="mt-1 text-muted-foreground">Manage the problem set. More tools arrive in later phases.</p>
        </div>
        <Button asChild variant="gradient">
          <Link href="/admin/problems/new">
            <FilePlus2 aria-hidden /> New problem
          </Link>
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {TILES.map((tile) => (
          <StatusTile key={tile.status} {...tile} />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Coming with later phases</CardTitle>
          <CardDescription>These sections need features that are not built yet.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          User management, submissions, contests, discussion moderation, analytics, audit logs and system health.
        </CardContent>
      </Card>
    </div>
  );
}

function StatusTile({ status, label, hint, Icon }: (typeof TILES)[number]) {
  const { data, isPending, isError } = useAdminCount(status);
  return (
    <Link href={`/admin/problems?status=${status}`} className="group">
      <Card className="transition-colors group-hover:border-brand-blue/50">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{label}</CardTitle>
          <Icon className="size-4 text-muted-foreground" aria-hidden />
        </CardHeader>
        <CardContent>
          {isPending ? <Skeleton className="h-9 w-16" /> : <p className="text-3xl font-bold">{isError ? "—" : data}</p>}
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </CardContent>
      </Card>
    </Link>
  );
}
