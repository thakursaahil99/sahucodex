"use client";

import { Clock, Copy, Cpu } from "lucide-react";
import { toast } from "sonner";

import { DifficultyBadge } from "@/components/problems/difficulty-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import type { ContestProblemDetail } from "@/lib/contests/types";

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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-2 text-base font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** A contest problem's statement: the same content the plain problem page shows, minus everything that depends on
 * per-user progress or an editorial (neither applies mid-contest — there is no editorial to unlock and "solved" here
 * means "on the standings", shown on the Standings tab, not as a badge here). */
export function ContestProblemStatement({ label, points, problem }: { label: string; points: number; problem: ContestProblemDetail }) {
  return (
    <div className="p-5 sm:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-bold tracking-tight">
            {label}. {problem.title}
          </h1>
          <Badge variant="accent">{points} pts</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <DifficultyBadge difficulty={problem.difficulty} />
          <span className="inline-flex items-center gap-1" title="Time limit">
            <Clock className="size-3.5" aria-hidden /> {problem.time_limit_ms / 1000}s
          </span>
          <span className="inline-flex items-center gap-1" title="Memory limit">
            <Cpu className="size-3.5" aria-hidden /> {problem.memory_limit_mb} MB
          </span>
        </div>
      </header>

      <div className="mt-6 space-y-6">
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
                {example.explanation && <Markdown className="text-sm text-muted-foreground">{example.explanation}</Markdown>}
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
