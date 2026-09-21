"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { AiOutput } from "@/components/ai/ai-result";
import { ActionBar } from "@/components/problems/action-bar";
import { ConsolePanel, type ConsoleTab } from "@/components/problems/console-panel";
import { EditorPane } from "@/components/problems/editor-pane";
import { ProblemStatement } from "@/components/problems/problem-statement";
import { VERDICT_LABEL } from "@/components/submissions/verdict-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { generate, useAiStatus } from "@/lib/ai/api";
import { aiErrorMessage } from "@/lib/ai/errors";
import type { AiFeature } from "@/lib/ai/types";
import { isApiError } from "@/lib/api/http";
import { useLanguages, useProblem } from "@/lib/problems/api";
import { loadLanguage, saveLanguage } from "@/lib/problems/storage";
import type { Language, ProblemDetail } from "@/lib/problems/types";
import { runCode, submitCode, useRun, useSubmission } from "@/lib/submissions/api";
import { useJudgeSocket } from "@/lib/submissions/socket";
import { isPending as isJudgePending } from "@/lib/submissions/types";
import { cn } from "@/lib/utils";

type MobileTab = "problem" | "code" | "console";

const TABS: Array<{ id: MobileTab; label: string }> = [
  { id: "problem", label: "Problem" },
  { id: "code", label: "Code" },
  { id: "console", label: "Console" },
];

// Fills the viewport under the 4rem site header (+1px border).
const FRAME = "flex h-[calc(100dvh-4.0625rem)] min-h-[32rem] flex-col";

export function ProblemWorkspace({ slug }: { slug: string }) {
  const problem = useProblem(slug);
  const languages = useLanguages();

  if (problem.isPending || languages.isPending) return <WorkspaceSkeleton />;

  if (problem.isError) {
    const missing = isApiError(problem.error) && problem.error.status === 404;
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <h1 className="text-2xl font-bold">{missing ? "Problem not found" : "Couldn't load this problem"}</h1>
        <p className="mt-2 text-muted-foreground">
          {missing ? "It may have been unpublished, or the link is wrong." : "Check your connection and try again."}
        </p>
        <div className="mt-6 flex gap-3">
          {!missing && <Button onClick={() => problem.refetch()}>Retry</Button>}
          <Button asChild variant="outline">
            <Link href="/problems">All problems</Link>
          </Button>
        </div>
      </div>
    );
  }

  const available = (languages.data ?? []).filter((l) => l.key in problem.data.starter_code);
  if (available.length === 0) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="text-2xl font-bold">{problem.data.title}</h1>
        <p className="mt-2 text-muted-foreground">This problem has no starter code for any supported language yet.</p>
      </div>
    );
  }
  return <Workspace problem={problem.data} languages={available} />;
}

function Workspace({ problem, languages }: { problem: ProblemDetail; languages: Language[] }) {
  const [language, setLanguage] = useState(() => {
    const remembered = typeof window === "undefined" ? null : loadLanguage(problem.slug);
    return languages.find((l) => l.key === remembered)?.key ?? languages[0]!.key;
  });
  const [customInput, setCustomInput] = useState(problem.examples[0]?.input ?? "");
  const [mobileTab, setMobileTab] = useState<MobileTab>("problem");
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("input");
  const [runId, setRunId] = useState<string | null>(null);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  // Read at click time instead of lifting the editor's per-keystroke state, so typing never re-renders this component.
  const codeRef = useRef(problem.starter_code[language] ?? "");
  // Hints already given this session, sent back so the next one goes further instead of repeating.
  const hintsRef = useRef<string[]>([]);
  const [aiOutput, setAiOutput] = useState<AiOutput | null>(null);
  const aiStatus = useAiStatus();
  const queryClient = useQueryClient();

  const chooseLanguage = useCallback(
    (next: string) => {
      setLanguage(next);
      saveLanguage(problem.slug, next);
    },
    [problem.slug],
  );

  const handleCodeChange = useCallback((next: string) => {
    codeRef.current = next;
  }, []);

  const runQuery = useRun(runId ?? undefined);
  const submissionQuery = useSubmission(submissionId ?? undefined);

  // The socket nudges the relevant query to refetch immediately; each query also polls on its own while pending,
  // so a socket that never connects (see lib/submissions/socket.ts) still catches up, just a little later.
  const handleJudgeEvent = useCallback(
    (event: { type: string; data: Record<string, unknown> }) => {
      if (runId && event.data.run_id === runId) void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      if (submissionId && event.data.submission_id === submissionId) {
        void queryClient.invalidateQueries({ queryKey: ["submission", submissionId] });
      }
      if (event.type === "achievement.earned") {
        toast.success(`Achievement unlocked: ${String(event.data.name)}`);
      }
    },
    [runId, submissionId, queryClient],
  );
  useJudgeSocket(handleJudgeEvent, Boolean(runId ?? submissionId));

  // Once per finished submission: refresh the problem's solved/acceptance data and tell the user the verdict.
  const handledSubmission = useRef<string | null>(null);
  useEffect(() => {
    const submission = submissionQuery.data;
    if (!submission || (submission.status !== "COMPLETED" && submission.status !== "FAILED")) return;
    const key = `${submission.id}:${submission.status}`;
    if (handledSubmission.current === key) return;
    handledSubmission.current = key;

    void queryClient.invalidateQueries({ queryKey: ["problem"] });
    void queryClient.invalidateQueries({ queryKey: ["problems"] });
    void queryClient.invalidateQueries({ queryKey: ["profile-stats"] }); // solved count, streak, achievements

    if (submission.status === "FAILED") {
      toast.error("The judge couldn't finish this submission", { description: "Please try submitting again." });
    } else if (submission.verdict === "ACCEPTED") {
      toast.success("Accepted!", { description: `${submission.passed_count}/${submission.total_count} tests passed.` });
    } else if (submission.verdict) {
      toast.error(VERDICT_LABEL[submission.verdict], {
        description: `${submission.passed_count}/${submission.total_count} tests passed.`,
      });
    }
  }, [submissionQuery.data, queryClient]);

  const runMutation = useMutation({
    mutationFn: () =>
      runCode({ problem_slug: problem.slug, language, source_code: codeRef.current, mode: "custom", input: customInput }),
    onSuccess: (queued) => {
      setRunId(queued.id);
      setConsoleTab("output");
    },
    onError: (error) => {
      toast.error("Couldn't run your code", { description: isApiError(error) ? error.message : undefined });
    },
  });

  const submitMutation = useMutation({
    mutationFn: () => submitCode({ problem_slug: problem.slug, language, source_code: codeRef.current }),
    onSuccess: (queued) => {
      setSubmissionId(queued.id);
      setConsoleTab("results");
    },
    onError: (error) => {
      toast.error("Couldn't submit your code", { description: isApiError(error) ? error.message : undefined });
    },
  });

  const aiMutation = useMutation({
    mutationFn: (feature: AiFeature) =>
      generate({
        feature,
        problemSlug: problem.slug,
        language,
        code: codeRef.current,
        previousHints: hintsRef.current,
      }),
    onMutate: (feature) => {
      setAiOutput({ status: "loading", feature });
      setConsoleTab("ai");
      setMobileTab("console");
    },
    onSuccess: (result, feature) => {
      if (feature === "hint") hintsRef.current = [...hintsRef.current, result.content];
      setAiOutput({
        status: "ready",
        feature,
        content: result.content,
        model: result.model,
        hintNumber: feature === "hint" ? hintsRef.current.length : undefined,
      });
    },
    onError: (error, feature) => {
      setAiOutput({ status: "error", feature, message: aiErrorMessage(error) });
    },
  });

  const handleAi = useCallback(
    (feature: AiFeature) => {
      if (!codeRef.current.trim()) {
        toast.error("Write some code first");
        return;
      }
      aiMutation.mutate(feature);
    },
    [aiMutation],
  );

  const handleRun = useCallback(() => {
    if (!codeRef.current.trim()) {
      toast.error("Write some code first");
      return;
    }
    runMutation.mutate();
  }, [runMutation]);

  const handleSubmit = useCallback(() => {
    if (!codeRef.current.trim()) {
      toast.error("Write some code first");
      return;
    }
    submitMutation.mutate();
  }, [submitMutation]);

  const running = runMutation.isPending || isJudgePending(runQuery.data?.status);
  const submitting = submitMutation.isPending || isJudgePending(submissionQuery.data?.status);

  return (
    <div className={FRAME}>
      {/* Small screens: one pane at a time. */}
      <div className="border-b bg-card p-2 md:hidden" role="tablist" aria-label="Workspace panes">
        <div className="grid grid-cols-3 gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={mobileTab === tab.id}
              onClick={() => setMobileTab(tab.id)}
              className={cn(
                "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                mobileTab === tab.id ? "bg-muted text-foreground" : "text-muted-foreground",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 md:grid-cols-[minmax(340px,42%)_1fr]">
        <section
          aria-label="Problem statement"
          className={cn("min-h-0 overflow-y-auto border-r", mobileTab !== "problem" && "hidden md:block")}
        >
          <ProblemStatement problem={problem} />
        </section>

        <div className={cn("flex min-h-0 flex-col", mobileTab === "problem" && "hidden md:flex")}>
          <div className={cn("min-h-0 flex-1", mobileTab === "console" && "hidden md:block")}>
            <EditorPane
              key={`${problem.slug}:${language}`}
              slug={problem.slug}
              language={language}
              languages={languages}
              starterCode={problem.starter_code[language] ?? ""}
              onLanguageChange={chooseLanguage}
              onRun={handleRun}
              onCodeChange={handleCodeChange}
            />
          </div>
          <ConsolePanel
            examples={problem.examples}
            input={customInput}
            onInputChange={setCustomInput}
            collapsible
            tab={consoleTab}
            onTabChange={setConsoleTab}
            run={runQuery.data ?? null}
            submission={submissionQuery.data ?? null}
            ai={aiOutput}
            problemSlug={problem.slug}
            className={cn(
              "md:max-h-[42%] md:shrink-0",
              mobileTab === "code" && "hidden md:flex",
              mobileTab === "console" && "flex-1",
            )}
          />
        </div>
      </div>

      <ActionBar
        onRun={handleRun}
        onSubmit={handleSubmit}
        running={running}
        submitting={submitting}
        onAi={handleAi}
        aiBusy={aiMutation.isPending ? (aiMutation.variables ?? null) : null}
        aiUnavailable={
          aiStatus.data && !aiStatus.data.configured
            ? "SahuCodeX AI isn't set up on this server yet — the operator has to choose a model (OLLAMA_MODEL)."
            : undefined
        }
      />
    </div>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className={cn(FRAME, "md:grid md:grid-cols-[minmax(340px,42%)_1fr]")} role="status" aria-label="Loading problem">
      <div className="space-y-4 border-r p-6">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-40" />
        <Skeleton className="h-24" />
      </div>
      <div className="hidden space-y-3 p-4 md:block">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-[60%]" />
        <Skeleton className="h-28" />
      </div>
    </div>
  );
}
