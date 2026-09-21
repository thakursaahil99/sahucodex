"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Save } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import {
  BasicsTab,
  HintsTab,
  PublishTab,
  StarterTab,
  StatementTab,
  TestsTab,
} from "@/components/admin/editor-tabs";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { createProblem, problemAction, updateProblem, useAdminProblem, validateProblem } from "@/lib/admin/api";
import {
  caseCounts,
  emptyForm,
  fromAdmin,
  localIssues,
  slugify,
  type AdminProblem,
  type ProblemForm,
  type ValidationIssue,
} from "@/lib/admin/problem-form";
import { ApiError, isApiError } from "@/lib/api/http";

const TAB_OF_FIELD: Record<string, string> = {
  title: "basics",
  slug: "basics",
  difficulty: "basics",
  time_limit_ms: "basics",
  memory_limit_mb: "basics",
  tags: "basics",
  description: "statement",
  constraints: "statement",
  input_format: "statement",
  output_format: "statement",
  function_signature: "statement",
  expected_time_complexity: "statement",
  expected_space_complexity: "statement",
  test_cases: "tests",
  starter_code: "starter",
  hints: "hints",
  editorial: "hints",
};

/** Collapses the API's nested field paths (`test_cases.2.kind`) onto the top-level field the user edits. */
export function topLevelErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (!isApiError(error)) return out;
  for (const detail of error.details ?? []) {
    const field = String((detail as { field?: string }).field ?? "").split(".")[0] ?? "";
    if (field && !(field in out)) out[field] = (detail as { message?: string }).message ?? "Invalid value";
  }
  if (error.code === "SLUG_TAKEN") out.slug = error.message;
  if (error.code === "UNKNOWN_TAG") out.tags = error.message;
  if (error.code === "UNKNOWN_LANGUAGE") out.starter_code = error.message;
  return out;
}

export function ProblemEditor({ problemId }: { problemId?: string }) {
  const existing = useAdminProblem(problemId);

  if (problemId && existing.isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading problem">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-96" />
      </div>
    );
  }
  if (problemId && existing.isError) {
    const missing = isApiError(existing.error) && existing.error.status === 404;
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <h1 className="text-2xl font-bold">{missing ? "Problem not found" : "Couldn't load the problem"}</h1>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/admin/problems">Back to problems</Link>
        </Button>
      </div>
    );
  }
  return <EditorForm key={existing.data?.id ?? "new"} initial={existing.data ?? null} />;
}

function EditorForm({ initial }: { initial: AdminProblem | null }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProblemForm>(() => (initial ? fromAdmin(initial) : emptyForm()));
  const [problem, setProblem] = useState<AdminProblem | null>(initial);
  const [slugTouched, setSlugTouched] = useState(Boolean(initial));
  const [dirty, setDirty] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<string | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[] | null>(null);
  const [tab, setTab] = useState("basics");

  // Warn before a tab close or reload throws unsaved edits away.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const patch = useCallback((changes: Partial<ProblemForm>) => {
    setForm((current) => ({ ...current, ...changes }));
    setDirty(true);
    setIssues(null);
  }, []);

  function onTitleChange(title: string) {
    patch(slugTouched ? { title } : { title, slug: slugify(title) });
  }
  function onSlugChange(slug: string) {
    setSlugTouched(true);
    patch({ slug: slug.toLowerCase() });
  }

  const refreshCaches = useCallback(async () => {
    // Public pages must reflect an edit immediately, so drop everything that could show stale data.
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["admin"] }),
      queryClient.invalidateQueries({ queryKey: ["problems"] }),
      queryClient.invalidateQueries({ queryKey: ["problem"] }),
      queryClient.invalidateQueries({ queryKey: ["tags"] }),
    ]);
  }, [queryClient]);

  const adopt = useCallback(
    (saved: AdminProblem) => {
      setProblem(saved);
      setForm(fromAdmin(saved)); // pick up the ids the server assigned to new test cases
      setDirty(false);
      setErrors({});
      setBanner(null);
      queryClient.setQueryData(["admin", "problem", saved.id], saved);
    },
    [queryClient],
  );

  const save = useMutation({
    mutationFn: () => (problem ? updateProblem(problem.id, form) : createProblem(form)),
    onSuccess: async (saved) => {
      const wasNew = !problem;
      adopt(saved);
      await refreshCaches();
      toast.success(wasNew ? "Problem created as a draft" : "Changes saved");
      if (wasNew) router.replace(`/admin/problems/${saved.id}/edit`);
    },
    onError: (error) => {
      const fields = topLevelErrors(error);
      setErrors(fields);
      const first = Object.keys(fields)[0];
      if (first && TAB_OF_FIELD[first]) setTab(TAB_OF_FIELD[first]);
      setBanner(
        isApiError(error) && error.status === 422 && Object.keys(fields).length
          ? "Some fields need attention — see the marked tabs."
          : isApiError(error)
            ? error.message
            : "Something went wrong while saving.",
      );
    },
  });

  const check = useMutation({
    mutationFn: () => validateProblem(problem!.id),
    onSuccess: (report) => setIssues(report.issues),
    onError: (error) => toast.error("Couldn't run the check", { description: isApiError(error) ? error.message : undefined }),
  });

  const act = useMutation({
    mutationFn: (action: "publish" | "unpublish" | "archive" | "restore") => problemAction(problem!.id, action),
    onSuccess: async (updated, action) => {
      adopt(updated);
      setIssues(null);
      await refreshCaches();
      toast.success(
        { publish: "Published — learners can see it now", unpublish: "Unpublished", archive: "Archived", restore: "Restored" }[action],
      );
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "PROBLEM_NOT_READY") {
        setIssues(((error.details ?? []) as unknown as ValidationIssue[]).map((d) => ({ field: d.field, code: d.code, message: d.message })));
        toast.error("Not ready to publish", { description: "See the blockers listed under Publish." });
        return;
      }
      toast.error("That didn't work", { description: isApiError(error) ? error.message : undefined });
    },
  });

  const blockers = localIssues(form);
  const counts = caseCounts(form);
  const tabHasError = (id: string) => Object.keys(errors).some((field) => TAB_OF_FIELD[field] === id);

  function trySave() {
    if (blockers.length) {
      setErrors(Object.fromEntries(blockers.map((b) => [b.field, b.message])));
      setTab(TAB_OF_FIELD[blockers[0]!.field] ?? "basics");
      setBanner("Fix the highlighted fields before saving.");
      return;
    }
    save.mutate();
  }

  const labelFor = (id: string, label: string, extra?: string) => (
    <>
      {label}
      {extra && <span className="text-xs opacity-60">{extra}</span>}
      {tabHasError(id) && <AlertTriangle className="size-3.5 text-destructive" aria-label="has errors" />}
    </>
  );

  return (
    <div className="space-y-6">
      <div className="sticky top-16 z-30 -mx-4 flex flex-wrap items-center gap-3 border-b bg-background/90 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-bold tracking-tight">{form.title.trim() || "New problem"}</h1>
          <p className="text-xs text-muted-foreground">
            {problem ? (
              <>
                <Badge variant={problem.status === "PUBLISHED" ? "success" : problem.status === "DRAFT" ? "warning" : "outline"}>
                  {problem.status.toLowerCase()}
                </Badge>{" "}
                <span className="ml-1">{dirty ? "Unsaved changes" : "All changes saved"}</span>
              </>
            ) : (
              "Not saved yet — created as a draft"
            )}
          </p>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href="/admin/problems">Back to list</Link>
        </Button>
        <Button onClick={trySave} loading={save.isPending} disabled={!dirty && Boolean(problem)} variant="gradient">
          <Save aria-hidden /> {problem ? "Save changes" : "Create draft"}
        </Button>
      </div>

      {banner && <Alert tone="error">{banner}</Alert>}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="basics">{labelFor("basics", "Basics")}</TabsTrigger>
          <TabsTrigger value="statement">{labelFor("statement", "Statement")}</TabsTrigger>
          <TabsTrigger value="tests">{labelFor("tests", "Test cases", ` ${counts.total}`)}</TabsTrigger>
          <TabsTrigger value="starter">{labelFor("starter", "Starter code")}</TabsTrigger>
          <TabsTrigger value="hints">{labelFor("hints", "Hints & editorial")}</TabsTrigger>
          <TabsTrigger value="publish">Publish</TabsTrigger>
        </TabsList>

        <div className="mt-6">
          <TabsContent value="basics">
            <BasicsTab form={form} patch={patch} errors={errors} onTitleChange={onTitleChange} onSlugChange={onSlugChange} />
          </TabsContent>
          <TabsContent value="statement">
            <StatementTab form={form} patch={patch} errors={errors} />
          </TabsContent>
          <TabsContent value="tests">
            <TestsTab form={form} patch={patch} errors={errors} />
          </TabsContent>
          <TabsContent value="starter">
            <StarterTab form={form} patch={patch} errors={errors} />
          </TabsContent>
          <TabsContent value="hints">
            <HintsTab form={form} patch={patch} errors={errors} />
          </TabsContent>
          <TabsContent value="publish">
            <PublishTab
              problem={problem}
              dirty={dirty}
              issues={issues}
              busy={check.isPending || act.isPending}
              onCheck={() => check.mutate()}
              onAction={(action) => act.mutate(action)}
            />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
