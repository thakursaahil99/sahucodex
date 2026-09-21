"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, CheckCircle2, Copy, ExternalLink, EyeOff, Plus, Trash2, XCircle } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { toast } from "sonner";

import { Field } from "@/components/auth/field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/markdown";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { createTag } from "@/lib/admin/api";
import { STARTER_TEMPLATES } from "@/lib/admin/templates";
import {
  caseCounts,
  emptyCase,
  newKey,
  type AdminProblem,
  type CaseForm,
  type ProblemForm,
  type ValidationIssue,
} from "@/lib/admin/problem-form";
import { isApiError } from "@/lib/api/http";
import { useLanguages, useTags } from "@/lib/problems/api";
import type { Difficulty } from "@/lib/problems/types";
import { cn } from "@/lib/utils";

export interface TabProps {
  form: ProblemForm;
  patch: (changes: Partial<ProblemForm>) => void;
  /** Field-level messages keyed by API field name (`title`, `slug`, `time_limit_ms`, …). */
  errors: Record<string, string>;
}

function TextArea({
  label,
  value,
  onChange,
  rows = 5,
  hint,
  mono = false,
  error,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: number;
  hint?: string;
  mono?: boolean;
  error?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Textarea
        id={id}
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={error ? true : undefined}
        spellCheck={!mono}
        className={cn(mono && "font-mono text-[13px]")}
      />
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs font-medium text-destructive">{error}</p>}
    </div>
  );
}

// --- Basics -------------------------------------------------------------------------------------

export function BasicsTab({
  form,
  patch,
  errors,
  onTitleChange,
  onSlugChange,
}: TabProps & { onTitleChange: (title: string) => void; onSlugChange: (slug: string) => void }) {
  const { data: tags } = useTags();
  const queryClient = useQueryClient();
  const [newTag, setNewTag] = useState("");
  const [adding, setAdding] = useState(false);

  async function addTag() {
    if (!newTag.trim()) return;
    setAdding(true);
    try {
      const created = await createTag(newTag.trim());
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
      patch({ tags: [...new Set([...form.tags, created.slug])] });
      setNewTag("");
      toast.success(`Tag “${created.name}” created`);
    } catch (error) {
      toast.error("Couldn't create the tag", { description: isApiError(error) ? error.message : undefined });
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Title" value={form.title} onChange={(e) => onTitleChange(e.target.value)} error={errors.title} maxLength={120} />
        <Field
          label="Slug"
          value={form.slug}
          onChange={(e) => onSlugChange(e.target.value)}
          error={errors.slug}
          hint={form.slug ? `Public URL: /problems/${form.slug}` : "Used in the URL. Filled from the title."}
          className="font-mono"
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="difficulty">Difficulty</Label>
          <Select id="difficulty" value={form.difficulty} onChange={(e) => patch({ difficulty: e.target.value as Difficulty })}>
            <option value="EASY">Easy</option>
            <option value="MEDIUM">Medium</option>
            <option value="HARD">Hard</option>
          </Select>
        </div>
        <Field
          label="Time limit (ms)"
          type="number"
          min={100}
          max={10000}
          step={100}
          value={form.time_limit_ms}
          onChange={(e) => patch({ time_limit_ms: Number(e.target.value) })}
          error={errors.time_limit_ms}
        />
        <Field
          label="Memory limit (MB)"
          type="number"
          min={16}
          max={1024}
          step={16}
          value={form.memory_limit_mb}
          onChange={(e) => patch({ memory_limit_mb: Number(e.target.value) })}
          error={errors.memory_limit_mb}
        />
      </div>

      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">Topics</legend>
        <div className="flex flex-wrap gap-2">
          {!tags && <p className="text-sm text-muted-foreground">Loading tags…</p>}
          {tags?.map((tag) => {
            const selected = form.tags.includes(tag.slug);
            return (
              <button
                key={tag.slug}
                type="button"
                aria-pressed={selected}
                onClick={() => patch({ tags: selected ? form.tags.filter((t) => t !== tag.slug) : [...form.tags, tag.slug] })}
                className={cn(
                  "rounded-full border px-3 py-1.5 text-sm transition-colors",
                  selected ? "border-brand-blue bg-brand-blue/15" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {tag.name}
              </button>
            );
          })}
        </div>
        {errors.tags && <p className="text-xs font-medium text-destructive">{errors.tags}</p>}
        <div className="flex max-w-sm gap-2">
          <label className="sr-only" htmlFor="new-tag">
            New tag name
          </label>
          <input
            id="new-tag"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void addTag();
              }
            }}
            placeholder="New tag…"
            maxLength={40}
            className="h-9 flex-1 rounded-lg border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:outline-none"
          />
          <Button type="button" variant="outline" size="sm" className="h-9" loading={adding} onClick={addTag}>
            <Plus aria-hidden /> Add
          </Button>
        </div>
      </fieldset>
    </div>
  );
}

// --- Statement ----------------------------------------------------------------------------------

export function StatementTab({ form, patch, errors }: TabProps) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="description">Description (Markdown)</Label>
          <Button type="button" variant="ghost" size="sm" aria-pressed={preview} onClick={() => setPreview((v) => !v)}>
            {preview ? "Edit" : "Preview"}
          </Button>
        </div>
        {preview ? (
          <div className="min-h-40 rounded-lg border bg-card p-4">
            {form.description.trim() ? <Markdown>{form.description}</Markdown> : <p className="text-sm text-muted-foreground">Nothing to preview yet.</p>}
          </div>
        ) : (
          <Textarea
            id="description"
            rows={12}
            value={form.description}
            onChange={(e) => patch({ description: e.target.value })}
            aria-invalid={errors.description ? true : undefined}
          />
        )}
        {errors.description && <p className="text-xs font-medium text-destructive">{errors.description}</p>}
        <p className="text-xs text-muted-foreground">
          Markdown with tables and code blocks. Raw HTML and images are not rendered.
        </p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <TextArea label="Input format" value={form.input_format} onChange={(v) => patch({ input_format: v })} rows={4} error={errors.input_format} />
        <TextArea label="Output format" value={form.output_format} onChange={(v) => patch({ output_format: v })} rows={4} error={errors.output_format} />
      </div>
      <TextArea label="Constraints (Markdown)" value={form.constraints} onChange={(v) => patch({ constraints: v })} rows={4} error={errors.constraints} />
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="Function signature (optional)" value={form.function_signature} onChange={(e) => patch({ function_signature: e.target.value })} maxLength={300} className="sm:col-span-3" />
        <Field label="Expected time complexity" value={form.expected_time_complexity} onChange={(e) => patch({ expected_time_complexity: e.target.value })} placeholder="O(n log n)" maxLength={60} />
        <Field label="Expected space complexity" value={form.expected_space_complexity} onChange={(e) => patch({ expected_space_complexity: e.target.value })} placeholder="O(n)" maxLength={60} />
      </div>
    </div>
  );
}

// --- Tests --------------------------------------------------------------------------------------

export function TestsTab({ form, patch, errors }: TabProps) {
  const counts = caseCounts(form);
  const update = (key: string, changes: Partial<CaseForm>) =>
    patch({ test_cases: form.test_cases.map((c) => (c.key === key ? { ...c, ...changes } : c)) });
  const move = (index: number, delta: number) => {
    const next = [...form.test_cases];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target]!, next[index]!];
    patch({ test_cases: next });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge variant="outline">{counts.public} public</Badge>
          <Badge variant="outline">{counts.hidden} hidden</Badge>
          <Badge variant="outline">{counts.examples} shown as examples</Badge>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => patch({ test_cases: [...form.test_cases, emptyCase("PUBLIC")] })}>
            <Plus aria-hidden /> Public test
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => patch({ test_cases: [...form.test_cases, emptyCase("HIDDEN")] })}>
            <Plus aria-hidden /> Hidden test
          </Button>
        </div>
      </div>
      <p className="flex items-start gap-2 rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
        <EyeOff className="mt-0.5 size-4 shrink-0" aria-hidden />
        <span>
          <strong className="text-foreground">Hidden</strong> tests never leave the server: learners only ever see
          verdicts and counts. <strong className="text-foreground">Public</strong> tests are shown to learners, and any
          you mark as an example also appear in the statement. Publishing needs at least one example and three hidden
          tests.
        </span>
      </p>
      {errors.test_cases && <p className="text-sm font-medium text-destructive">{errors.test_cases}</p>}

      {form.test_cases.length === 0 && (
        <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">No test cases yet.</div>
      )}

      <ol className="space-y-4">
        {form.test_cases.map((testCase, index) => (
          <li key={testCase.key} className="space-y-3 rounded-xl border bg-card p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">Test {index + 1}</span>
              <div className="w-32">
                <label className="sr-only" htmlFor={`kind-${testCase.key}`}>
                  Test {index + 1} visibility
                </label>
                <Select
                  id={`kind-${testCase.key}`}
                  className="h-8 text-xs"
                  value={testCase.kind}
                  onChange={(e) => {
                    const kind = e.target.value as CaseForm["kind"];
                    update(testCase.key, { kind, show_as_example: kind === "PUBLIC" && testCase.show_as_example });
                  }}
                >
                  <option value="PUBLIC">Public</option>
                  <option value="HIDDEN">Hidden</option>
                </Select>
              </div>
              {testCase.kind === "PUBLIC" && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={testCase.show_as_example}
                    onChange={(e) => update(testCase.key, { show_as_example: e.target.checked })}
                    className="size-4 accent-[var(--brand-blue)]"
                  />
                  Show as example
                </label>
              )}
              <div className="ml-auto flex gap-0.5">
                <Button type="button" variant="ghost" size="icon" className="size-8" aria-label={`Move test ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}>
                  <ArrowUp aria-hidden />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="size-8" aria-label={`Move test ${index + 1} down`} disabled={index === form.test_cases.length - 1} onClick={() => move(index, 1)}>
                  <ArrowDown aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8"
                  aria-label={`Duplicate test ${index + 1}`}
                  onClick={() => {
                    const copy = { ...testCase, key: newKey(), id: undefined };
                    const next = [...form.test_cases];
                    next.splice(index + 1, 0, copy);
                    patch({ test_cases: next });
                  }}
                >
                  <Copy aria-hidden />
                </Button>
                <ConfirmDialog
                  trigger={
                    <Button type="button" variant="ghost" size="icon" className="size-8 text-destructive" aria-label={`Delete test ${index + 1}`}>
                      <Trash2 aria-hidden />
                    </Button>
                  }
                  title={`Delete test ${index + 1}?`}
                  description="It is removed when you save."
                  confirmLabel="Delete test"
                  destructive
                  onConfirm={() => patch({ test_cases: form.test_cases.filter((c) => c.key !== testCase.key) })}
                />
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <TextArea label="Input (stdin)" value={testCase.input} onChange={(v) => update(testCase.key, { input: v })} rows={5} mono hint={`${testCase.input.length.toLocaleString()} characters`} />
              <TextArea label="Expected output (stdout)" value={testCase.expected_output} onChange={(v) => update(testCase.key, { expected_output: v })} rows={5} mono hint={`${testCase.expected_output.length.toLocaleString()} characters`} />
            </div>
            {testCase.kind === "PUBLIC" && testCase.show_as_example && (
              <TextArea label="Explanation shown under the example (optional)" value={testCase.example_explanation} onChange={(v) => update(testCase.key, { example_explanation: v })} rows={2} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

// --- Starter code -------------------------------------------------------------------------------

export function StarterTab({ form, patch }: TabProps) {
  const { data: languages } = useLanguages();
  if (!languages) return <p className="text-sm text-muted-foreground">Loading languages…</p>;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Code learners start from. It should read standard input and write standard output, matching the tests. Provide at
        least one language; learners can only pick languages that have starter code.
      </p>
      <Tabs defaultValue={languages[0]?.key}>
        <TabsList>
          {languages.map((language) => (
            <TabsTrigger key={language.key} value={language.key}>
              {language.display_name}
              {form.starter_code[language.key]?.trim() && <CheckCircle2 className="size-3.5 text-success" aria-label="has code" />}
            </TabsTrigger>
          ))}
        </TabsList>
        {languages.map((language) => (
          <TabsContent key={language.key} value={language.key} className="mt-4 space-y-2">
            <TextArea
              label={`${language.display_name} starter code`}
              value={form.starter_code[language.key] ?? ""}
              onChange={(v) => patch({ starter_code: { ...form.starter_code, [language.key]: v } })}
              rows={14}
              mono
            />
            <Button type="button" variant="outline" size="sm" onClick={() => patch({ starter_code: { ...form.starter_code, [language.key]: STARTER_TEMPLATES[language.key] ?? "" } })}>
              Use the generic template
            </Button>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

// --- Hints & editorial --------------------------------------------------------------------------

export function HintsTab({ form, patch }: TabProps) {
  const [preview, setPreview] = useState(false);
  return (
    <div className="space-y-6">
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium">Hints (revealed one at a time, easiest first)</legend>
        {form.hints.map((hint, index) => (
          <div key={index} className="flex gap-2">
            <div className="flex-1">
              <TextArea
                label={`Hint ${index + 1}`}
                value={hint}
                onChange={(v) => patch({ hints: form.hints.map((h, i) => (i === index ? v : h)) })}
                rows={2}
              />
            </div>
            <Button type="button" variant="ghost" size="icon" className="mt-6 size-8 text-destructive" aria-label={`Remove hint ${index + 1}`} onClick={() => patch({ hints: form.hints.filter((_, i) => i !== index) })}>
              <Trash2 aria-hidden />
            </Button>
          </div>
        ))}
        {form.hints.length < 10 && (
          <Button type="button" variant="outline" size="sm" onClick={() => patch({ hints: [...form.hints, ""] })}>
            <Plus aria-hidden /> Add hint
          </Button>
        )}
      </fieldset>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="editorial">Editorial (Markdown, unlocked when a learner solves the problem)</Label>
          <Button type="button" variant="ghost" size="sm" aria-pressed={preview} onClick={() => setPreview((v) => !v)}>
            {preview ? "Edit" : "Preview"}
          </Button>
        </div>
        {preview ? (
          <div className="min-h-32 rounded-lg border bg-card p-4">
            {form.editorial.trim() ? <Markdown>{form.editorial}</Markdown> : <p className="text-sm text-muted-foreground">Nothing to preview yet.</p>}
          </div>
        ) : (
          <Textarea id="editorial" rows={10} value={form.editorial} onChange={(e) => patch({ editorial: e.target.value })} />
        )}
      </div>
    </div>
  );
}

// --- Publish ------------------------------------------------------------------------------------

export function PublishTab({
  problem,
  dirty,
  issues,
  busy,
  onCheck,
  onAction,
}: {
  problem: AdminProblem | null;
  dirty: boolean;
  issues: ValidationIssue[] | null;
  busy: boolean;
  onCheck: () => void;
  onAction: (action: "publish" | "unpublish" | "archive" | "restore") => void;
}) {
  if (!problem) {
    return (
      <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
        Save the problem first. It is stored as a <strong>draft</strong> until you publish it.
      </div>
    );
  }
  const archived = problem.status === "ARCHIVED";
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">Status</span>
        <Badge variant={problem.status === "PUBLISHED" ? "success" : problem.status === "DRAFT" ? "warning" : "outline"}>
          {problem.status.toLowerCase()}
        </Badge>
        {problem.status === "PUBLISHED" && (
          <Button asChild variant="ghost" size="sm">
            <Link href={`/problems/${problem.slug}`} target="_blank">
              View as learner <ExternalLink aria-hidden />
            </Link>
          </Button>
        )}
      </div>

      {dirty && (
        <p role="status" className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
          You have unsaved changes. Readiness checks and publishing use the <strong>saved</strong> version, so save first.
        </p>
      )}

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <Button type="button" variant="outline" onClick={onCheck} loading={busy} disabled={dirty}>
            Check readiness
          </Button>
        </div>
        {issues && issues.length === 0 && (
          <p role="status" className="flex items-center gap-2 text-sm text-success">
            <CheckCircle2 className="size-4" aria-hidden /> Everything required to publish is in place.
          </p>
        )}
        {issues && issues.length > 0 && (
          <ul aria-label="Publishing blockers" className="space-y-2">
            {issues.map((issue, index) => (
              <li key={index} className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
                <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
                <span>{issue.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap gap-3 border-t pt-6">
        {problem.status === "DRAFT" && (
          <Button type="button" variant="gradient" disabled={dirty || busy} onClick={() => onAction("publish")}>
            Publish
          </Button>
        )}
        {problem.status === "PUBLISHED" && (
          <ConfirmDialog
            trigger={<Button type="button" variant="outline" disabled={busy}>Unpublish</Button>}
            title="Unpublish this problem?"
            description="It disappears from the problem list immediately. Learners' history is kept."
            confirmLabel="Unpublish"
            onConfirm={() => onAction("unpublish")}
          />
        )}
        {!archived && (
          <ConfirmDialog
            trigger={<Button type="button" variant="outline" className="text-destructive" disabled={busy}>Archive</Button>}
            title="Archive this problem?"
            description="Archiving hides it from everyone but admins. You can restore it later."
            confirmLabel="Archive"
            destructive
            onConfirm={() => onAction("archive")}
          />
        )}
        {archived && (
          <Button type="button" variant="outline" onClick={() => onAction("restore")} loading={busy}>
            Restore
          </Button>
        )}
      </div>
    </div>
  );
}
