"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { fieldErrors, isApiError } from "@/lib/api/http";
import { createContest, setContestPublished, updateContest, useAdminContest } from "@/lib/contests/api";
import type { ContestAdminInput, ContestAdminOut } from "@/lib/contests/types";

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromAdmin(contest: ContestAdminOut): ContestAdminInput {
  return {
    slug: contest.slug,
    title: contest.title,
    description: contest.description,
    start_time: contest.start_time,
    end_time: contest.end_time,
    penalty_minutes: contest.penalty_minutes,
    problems: contest.problems.map((p) => ({ problem_slug: p.problem_slug, label: p.label, points: p.points })),
  };
}

function emptyForm(): ContestAdminInput {
  const in1h = new Date(Date.now() + 3_600_000).toISOString();
  const in3h = new Date(Date.now() + 3 * 3_600_000).toISOString();
  return { slug: "", title: "", description: "", start_time: in1h, end_time: in3h, penalty_minutes: 20, problems: [] };
}

export function ContestEditorPage({ contestId }: { contestId?: string }) {
  const existing = useAdminContest(contestId);
  if (contestId && existing.isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading contest">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  return <EditorForm key={existing.data?.id ?? "new"} initial={existing.data ?? null} />;
}

function EditorForm({ initial }: { initial: ContestAdminOut | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [contest, setContest] = useState(initial);
  const [form, setForm] = useState<ContestAdminInput>(() => (initial ? fromAdmin(initial) : emptyForm()));
  const [errors, setErrors] = useState<Record<string, string>>({});

  function patch(changes: Partial<ContestAdminInput>) {
    setForm((current) => ({ ...current, ...changes }));
  }

  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin-contests"] }),
      queryClient.invalidateQueries({ queryKey: ["contests"] }),
    ]);

  const save = useMutation({
    mutationFn: () => (contest ? updateContest(contest.id, form) : createContest(form)),
    onSuccess: async (saved) => {
      const wasNew = !contest;
      setContest(saved);
      setForm(fromAdmin(saved));
      setErrors({});
      await refresh();
      toast.success(wasNew ? "Contest created as a draft" : "Changes saved");
      if (wasNew) router.replace(`/admin/contests/${saved.id}/edit`);
    },
    onError: (error) => {
      if (isApiError(error) && error.details) setErrors(fieldErrors(error));
      toast.error("Couldn't save the contest", { description: isApiError(error) ? error.message : undefined });
    },
  });

  const publish = useMutation({
    mutationFn: (published: boolean) => {
      if (!contest) throw new Error("save the contest first");
      return setContestPublished(contest.id, published);
    },
    onSuccess: async (saved) => {
      setContest(saved);
      await refresh();
      toast.success(saved.published ? "Published" : "Unpublished");
    },
    onError: (error) => toast.error("Couldn't change publish state", { description: isApiError(error) ? error.message : undefined }),
  });

  function addProblemRow() {
    patch({ problems: [...form.problems, { problem_slug: "", label: nextLabel(form.problems.length), points: 100 }] });
  }
  function updateRow(index: number, changes: Partial<ContestAdminInput["problems"][number]>) {
    patch({ problems: form.problems.map((row, i) => (i === index ? { ...row, ...changes } : row)) });
  }
  function removeRow(index: number) {
    patch({ problems: form.problems.filter((_, i) => i !== index) });
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{contest ? `Edit: ${contest.title}` : "New contest"}</h1>
        {contest && (
          <Button
            variant="outline"
            onClick={() => publish.mutate(!contest.published)}
            disabled={publish.isPending}
          >
            {contest.published ? "Unpublish" : "Publish"}
          </Button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="c-slug">Slug</Label>
          <Input id="c-slug" value={form.slug} onChange={(e) => patch({ slug: e.target.value.toLowerCase() })} aria-invalid={Boolean(errors.slug)} />
          {errors.slug && <p className="text-xs text-destructive">{errors.slug}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="c-title">Title</Label>
          <Input id="c-title" value={form.title} onChange={(e) => patch({ title: e.target.value })} aria-invalid={Boolean(errors.title)} />
          {errors.title && <p className="text-xs text-destructive">{errors.title}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="c-start">Starts</Label>
          <Input
            id="c-start"
            type="datetime-local"
            value={toLocalInput(form.start_time)}
            onChange={(e) => patch({ start_time: new Date(e.target.value).toISOString() })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="c-end">Ends</Label>
          <Input
            id="c-end"
            type="datetime-local"
            value={toLocalInput(form.end_time)}
            onChange={(e) => patch({ end_time: new Date(e.target.value).toISOString() })}
          />
          {errors.end_time && <p className="text-xs text-destructive">{errors.end_time}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="c-penalty">Penalty (minutes per wrong attempt)</Label>
          <Input
            id="c-penalty"
            type="number"
            min={0}
            value={form.penalty_minutes}
            onChange={(e) => patch({ penalty_minutes: Number(e.target.value) })}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="c-desc">Description (Markdown)</Label>
        <Textarea id="c-desc" rows={5} value={form.description} onChange={(e) => patch({ description: e.target.value })} />
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Problems</Label>
          <Button type="button" variant="outline" size="sm" onClick={addProblemRow}>
            <Plus aria-hidden /> Add problem
          </Button>
        </div>
        {form.problems.length === 0 && <p className="text-sm text-muted-foreground">No problems yet — add at least one before publishing.</p>}
        <div className="space-y-2">
          {form.problems.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                aria-label="Label"
                className="w-16"
                value={row.label}
                onChange={(e) => updateRow(index, { label: e.target.value.toUpperCase() })}
              />
              <Input
                aria-label="Problem slug"
                className="flex-1"
                placeholder="problem-slug"
                value={row.problem_slug}
                onChange={(e) => updateRow(index, { problem_slug: e.target.value.toLowerCase() })}
              />
              <Input
                aria-label="Points"
                type="number"
                className="w-24"
                min={0}
                value={row.points}
                onChange={(e) => updateRow(index, { points: Number(e.target.value) })}
              />
              <Button type="button" variant="ghost" size="icon" aria-label={`Remove ${row.label || "row"}`} onClick={() => removeRow(index)}>
                <Trash2 aria-hidden />
              </Button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {contest ? "Save changes" : "Create draft"}
        </Button>
      </div>
    </div>
  );
}

function nextLabel(count: number): string {
  return String.fromCharCode(65 + count); // A, B, C, ...
}
