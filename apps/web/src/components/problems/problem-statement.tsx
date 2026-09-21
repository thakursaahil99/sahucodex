"use client";

import { Check, Clock, Copy, Cpu, Lightbulb, Lock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { DifficultyBadge } from "@/components/problems/difficulty-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchHint } from "@/lib/problems/api";
import type { Hint, ProblemDetail } from "@/lib/problems/types";
import { isApiError } from "@/lib/api/http";

async function copy(text: string, label: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`${label} copied`);
  } catch {
    toast.error("Couldn't copy to the clipboard");
  }
}

function Block({ label, text }: { label: string; text: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</span>
        <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => copy(text, label)}>
          <Copy aria-hidden /> Copy
        </Button>
      </div>
      <pre className="overflow-x-auto rounded-lg border bg-muted/60 p-3 font-mono text-[13px] leading-6">{text}</pre>
    </div>
  );
}

export function ProblemStatement({ problem }: { problem: ProblemDetail }) {
  return (
    <div className="p-5 sm:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">{problem.title}</h1>
          {problem.status === "SOLVED" && <Badge variant="success">Solved</Badge>}
          {problem.status === "ATTEMPTED" && <Badge variant="warning">Attempted</Badge>}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <DifficultyBadge difficulty={problem.difficulty} />
          <span className="inline-flex items-center gap-1" title="Time limit">
            <Clock className="size-3.5" aria-hidden /> {problem.time_limit_ms / 1000}s
          </span>
          <span className="inline-flex items-center gap-1" title="Memory limit">
            <Cpu className="size-3.5" aria-hidden /> {problem.memory_limit_mb} MB
          </span>
          <span>
            Acceptance {problem.acceptance_rate === null ? "—" : `${problem.acceptance_rate}%`}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {problem.tags.map((tag) => (
            <Link key={tag.slug} href={`/problems?tag=${tag.slug}`}>
              <Badge variant="outline" className="font-normal hover:border-foreground/40">
                {tag.name}
              </Badge>
            </Link>
          ))}
        </div>
      </header>

      <Tabs defaultValue="description" className="mt-6">
        <TabsList>
          <TabsTrigger value="description">Description</TabsTrigger>
          <TabsTrigger value="hints">
            Hints{problem.hint_count > 0 && <span className="text-xs opacity-60">{problem.hint_count}</span>}
          </TabsTrigger>
          <TabsTrigger value="editorial">
            {!problem.solution_unlocked && <Lock className="size-3.5" aria-hidden />}
            Editorial
          </TabsTrigger>
        </TabsList>

        <TabsContent value="description" className="mt-5 space-y-6">
          <Markdown>{problem.description}</Markdown>

          <Section title="Input">
            <Markdown>{problem.input_format}</Markdown>
          </Section>
          <Section title="Output">
            <Markdown>{problem.output_format}</Markdown>
          </Section>
          <Section title="Constraints">
            <Markdown>{problem.constraints}</Markdown>
          </Section>

          <Section title="Examples">
            <div className="space-y-5">
              {problem.examples.map((example, index) => (
                <div key={index} className="space-y-3 rounded-xl border bg-card p-4">
                  <p className="text-sm font-medium">Example {index + 1}</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Block label="Input" text={example.input} />
                    <Block label="Output" text={example.output} />
                  </div>
                  {example.explanation && (
                    <p className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">Explanation. </span>
                      {example.explanation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </Section>
        </TabsContent>

        <TabsContent value="hints" className="mt-5">
          <HintList key={problem.slug} slug={problem.slug} count={problem.hint_count} />
        </TabsContent>

        <TabsContent value="editorial" className="mt-5">
          {problem.solution_unlocked && problem.editorial ? (
            <div className="space-y-4">
              <Markdown>{problem.editorial}</Markdown>
              {(problem.expected_time_complexity || problem.expected_space_complexity) && (
                <dl className="grid grid-cols-2 gap-3 rounded-xl border bg-card p-4 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Expected time</dt>
                    <dd className="font-mono">{problem.expected_time_complexity ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Expected space</dt>
                    <dd className="font-mono">{problem.expected_space_complexity ?? "—"}</dd>
                  </div>
                </dl>
              )}
            </div>
          ) : problem.solution_unlocked ? (
            <p className="text-sm text-muted-foreground">There is no editorial for this problem yet.</p>
          ) : (
            <div className="rounded-xl border border-dashed p-8 text-center">
              <Lock className="mx-auto mb-3 size-6 text-muted-foreground" aria-hidden />
              <p className="font-medium">The editorial unlocks when you solve this problem</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Try the hints first — they nudge you without giving the solution away.
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** Problem hints are fetched one at a time so opening the page never spoils them. */
function HintList({ slug, count }: { slug: string; count: number }) {
  const [revealed, setRevealed] = useState<Hint[]>([]);
  const [loading, setLoading] = useState(false);

  if (count === 0) return <p className="text-sm text-muted-foreground">This problem has no hints.</p>;

  async function revealNext() {
    setLoading(true);
    try {
      const next = await fetchHint(slug, revealed.length + 1);
      setRevealed((current) => [...current, next]);
    } catch (error) {
      toast.error("Couldn't load the hint", { description: isApiError(error) ? error.message : undefined });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        {revealed.length} of {count} hints revealed. Each one gives away a little more.
      </p>
      <ol className="space-y-3">
        {revealed.map((hint) => (
          <li key={hint.index} className="flex gap-3 rounded-xl border bg-card p-4 text-sm">
            <Lightbulb className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <div>
              <p className="mb-1 font-medium">Hint {hint.index}</p>
              <p className="leading-relaxed">{hint.hint}</p>
            </div>
          </li>
        ))}
      </ol>
      {revealed.length < count ? (
        <Button variant="outline" onClick={revealNext} loading={loading}>
          <Lightbulb aria-hidden /> Reveal hint {revealed.length + 1}
        </Button>
      ) : (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <Check className="size-4 text-success" aria-hidden /> That was the last hint.
        </p>
      )}
    </div>
  );
}
