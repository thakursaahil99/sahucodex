"use client";

import { ChevronDown, ChevronUp, Terminal } from "lucide-react";
import { useState } from "react";

import { AiResultTab, type AiOutput } from "@/components/ai/ai-result";
import { StatusLabel, VerdictBadge, formatKb, formatMs } from "@/components/submissions/verdict-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { Example } from "@/lib/problems/types";
import type { RunOut, SubmissionDetail } from "@/lib/submissions/types";
import { cn } from "@/lib/utils";

export type ConsoleTab = "input" | "output" | "results" | "ai";

interface ConsolePanelProps {
  examples: Example[];
  input: string;
  onInputChange: (value: string) => void;
  /** Desktop only: lets the user fold the console away to give the editor more room. */
  collapsible?: boolean;
  className?: string;
  tab: ConsoleTab;
  onTabChange: (tab: ConsoleTab) => void;
  run: RunOut | null;
  submission: SubmissionDetail | null;
  /** The latest SahuCodeX AI suggestion — kept on its own tab so it is never mistaken for a judge result. */
  ai?: AiOutput | null;
  /** Lets the AI tab link to a chat about this problem. */
  problemSlug?: string;
}

/** Test input, program output, judge results — SahuJudge's three views of one attempt — plus the AI's suggestion. */
export function ConsolePanel({
  examples,
  input,
  onInputChange,
  collapsible = false,
  className,
  tab,
  onTabChange,
  run,
  submission,
  ai = null,
  problemSlug,
}: ConsolePanelProps) {
  const [open, setOpen] = useState(true);
  const expanded = !collapsible || open;

  return (
    <section aria-label="Console" className={cn("flex min-h-0 flex-col border-t bg-card", className)}>
      <div className="flex items-center gap-2 px-3 py-1.5">
        <Terminal className="size-4 text-muted-foreground" aria-hidden />
        <h2 className="text-sm font-medium">Console</h2>
        {collapsible && (
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto size-7"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Collapse console" : "Expand console"}
          >
            {open ? <ChevronDown aria-hidden /> : <ChevronUp aria-hidden />}
          </Button>
        )}
      </div>

      {expanded && (
        <Tabs value={tab} onValueChange={(v) => onTabChange(v as ConsoleTab)} className="flex min-h-0 flex-1 flex-col px-3 pb-3">
          <TabsList className="h-9 w-fit self-start">
            <TabsTrigger value="input">Test input</TabsTrigger>
            <TabsTrigger value="output">Output</TabsTrigger>
            <TabsTrigger value="results">Test results</TabsTrigger>
            <TabsTrigger value="ai">SahuCodeX AI</TabsTrigger>
          </TabsList>

          <TabsContent value="input" className="mt-2 flex min-h-0 flex-1 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Load example:</span>
              {examples.map((example, index) => (
                <Button
                  key={index}
                  variant="outline"
                  size="sm"
                  className="h-7 px-2.5 text-xs"
                  onClick={() => onInputChange(example.input)}
                >
                  {index + 1}
                </Button>
              ))}
            </div>
            <label className="sr-only" htmlFor="custom-input">
              Custom input
            </label>
            <Textarea
              id="custom-input"
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              spellCheck={false}
              placeholder="Type the input your program should read from standard input…"
              className="min-h-24 flex-1 resize-none font-mono text-[13px]"
            />
          </TabsContent>

          <TabsContent value="output" className="mt-2 min-h-0 flex-1 overflow-y-auto">
            <OutputTab run={run} />
          </TabsContent>

          <TabsContent value="results" className="mt-2 min-h-0 flex-1 overflow-y-auto">
            <ResultsTab submission={submission} />
          </TabsContent>

          <TabsContent value="ai" className="mt-2 min-h-0 flex-1 overflow-y-auto">
            <AiResultTab output={ai} problemSlug={problemSlug} />
          </TabsContent>
        </Tabs>
      )}
    </section>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed p-4 text-sm">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{body}</p>
    </div>
  );
}

function Stream({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <pre className="mt-1 max-h-48 overflow-auto rounded-lg border bg-muted/40 p-2 font-mono text-[13px] whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  );
}

function OutputTab({ run }: { run: RunOut | null }) {
  if (!run) {
    return (
      <Empty
        title="Nothing has run yet"
        body="Run executes your code on the input above in an isolated sandbox and shows stdout, stderr, runtime and memory here."
      />
    );
  }
  if (run.status === "QUEUED" || run.status === "RUNNING") {
    return (
      <div className="space-y-3" role="status" aria-live="polite">
        <p className="text-sm text-muted-foreground">{run.status === "QUEUED" ? "Queued…" : "Running…"}</p>
        <Skeleton className="h-24" />
      </div>
    );
  }
  if (run.status === "FAILED" || !run.result) {
    return (
      <Empty title="The judge couldn't run this" body={run.error ?? "Something went wrong. Please try again."} />
    );
  }
  const { result } = run;
  if (result.outcome === "COMPILATION_ERROR") {
    return (
      <div className="space-y-2">
        <VerdictBadge verdict="COMPILATION_ERROR" />
        <Stream label="Compiler output" text={result.compile_output ?? ""} />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {result.outcome !== "OK" && <VerdictBadge verdict={result.outcome} />}
        <span>Runtime: {formatMs(result.runtime_ms)}</span>
        <span>Memory: {formatKb(result.memory_kb)}</span>
      </div>
      {result.message && <p className="text-sm text-warning">{result.message}</p>}
      <Stream label="stdout" text={result.stdout ?? ""} />
      <Stream label="stderr" text={result.stderr ?? ""} />
      {!result.stdout && !result.stderr && <p className="text-sm text-muted-foreground">The program produced no output.</p>}
    </div>
  );
}

function ResultsTab({ submission }: { submission: SubmissionDetail | null }) {
  if (!submission) {
    return (
      <Empty
        title="No submissions yet"
        body="Submit judges your solution against every test, public and hidden, and shows each public test's verdict, runtime and memory here. Hidden tests only ever report a verdict and counts — never their data."
      />
    );
  }
  if (submission.status === "QUEUED" || submission.status === "RUNNING") {
    return (
      <div className="space-y-3" role="status" aria-live="polite">
        <StatusLabel status={submission.status} />
        <Skeleton className="h-24" />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        {submission.verdict ? <VerdictBadge verdict={submission.verdict} /> : <StatusLabel status={submission.status} />}
        <span className="text-sm text-muted-foreground">
          {submission.passed_count} / {submission.total_count} tests passed
        </span>
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span>Runtime: {formatMs(submission.runtime_ms)}</span>
        <span>Memory: {formatKb(submission.memory_kb)}</span>
      </div>
      {submission.message && <p className="text-sm text-warning">{submission.message}</p>}
      <Stream label="Compiler output" text={submission.compile_output ?? ""} />
      {submission.test_results.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">Public test results</caption>
            <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Test</th>
                <th scope="col" className="px-3 py-2 font-medium">Verdict</th>
                <th scope="col" className="px-3 py-2 font-medium">Runtime</th>
                <th scope="col" className="px-3 py-2 font-medium">Memory</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {submission.test_results.map((t) => (
                <tr key={t.position}>
                  <td className="px-3 py-2">#{t.position}</td>
                  <td className="px-3 py-2">
                    <VerdictBadge verdict={t.verdict} />
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">{formatMs(t.runtime_ms)}</td>
                  <td className="px-3 py-2 text-muted-foreground">{formatKb(t.memory_kb)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {submission.total_count > submission.test_results.length && (
        <p className="text-xs text-muted-foreground">
          {submission.total_count - submission.test_results.length} additional hidden test
          {submission.total_count - submission.test_results.length === 1 ? "" : "s"} ran — only their verdict counted
          above; their data is never shown.
        </p>
      )}
    </div>
  );
}
