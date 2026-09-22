"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ContestActionBar } from "@/components/contests/contest-action-bar";
import { ContestProblemStatement } from "@/components/contests/contest-problem-statement";
import { ConsolePanel, type ConsoleTab } from "@/components/problems/console-panel";
import { EditorPane } from "@/components/problems/editor-pane";
import { VERDICT_LABEL } from "@/components/submissions/verdict-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api/http";
import { registerForContest, runContestCode, submitContestCode, useContest, useContestProblem } from "@/lib/contests/api";
import { useLanguages } from "@/lib/problems/api";
import { loadLanguage, saveLanguage } from "@/lib/problems/storage";
import { useRun, useSubmission } from "@/lib/submissions/api";
import { useJudgeSocket } from "@/lib/submissions/socket";
import { isPending as isJudgePending } from "@/lib/submissions/types";
import { cn } from "@/lib/utils";

type MobileTab = "problem" | "code" | "console";
const TABS: Array<{ id: MobileTab; label: string }> = [
  { id: "problem", label: "Problem" },
  { id: "code", label: "Code" },
  { id: "console", label: "Console" },
];
const FRAME = "flex h-[calc(100dvh-4.0625rem)] min-h-[32rem] flex-col";

export function ContestWorkspace({ slug, label }: { slug: string; label: string }) {
  const contest = useContest(slug);
  const problem = useContestProblem(slug, label);
  const languages = useLanguages();

  if (contest.isPending || problem.isPending || languages.isPending) return <WorkspaceSkeleton />;

  if (contest.isError || problem.isError) {
    const missing = isApiError(problem.error) && problem.error.status === 404;
    return (
      <div className="mx-auto flex max-w-md flex-col items-center px-4 py-24 text-center">
        <h1 className="text-2xl font-bold">{missing ? "Problem not found" : "Couldn't load this problem"}</h1>
        <p className="mt-2 text-muted-foreground">
          {missing
            ? "It may not exist in this contest, or the contest hasn't started yet."
            : "Check your connection and try again."}
        </p>
        <Button asChild variant="outline" className="mt-6">
          <Link href={`/contests/${slug}`}>Back to contest</Link>
        </Button>
      </div>
    );
  }

  const available = (languages.data ?? []).filter((l) => l.key in problem.data.problem.starter_code);
  if (available.length === 0) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <h1 className="text-2xl font-bold">{problem.data.problem.title}</h1>
        <p className="mt-2 text-muted-foreground">This problem has no starter code for any supported language yet.</p>
      </div>
    );
  }

  return (
    <Workspace
      slug={slug}
      label={label}
      registered={contest.data.registered}
      problemOut={problem.data}
      languages={available}
    />
  );
}

function Workspace({
  slug,
  label,
  registered,
  problemOut,
  languages,
}: {
  slug: string;
  label: string;
  registered: boolean;
  problemOut: NonNullable<ReturnType<typeof useContestProblem>["data"]>;
  languages: { key: string; display_name: string; editor_language: string; file_extension: string }[];
}) {
  const { problem, points } = problemOut;
  const draftKey = `contest:${slug}:${label}`;
  const [language, setLanguage] = useState(() => {
    const remembered = typeof window === "undefined" ? null : loadLanguage(draftKey);
    return languages.find((l) => l.key === remembered)?.key ?? languages[0]!.key;
  });
  const [customInput, setCustomInput] = useState(problem.examples[0]?.input ?? "");
  const [mobileTab, setMobileTab] = useState<MobileTab>("problem");
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("input");
  const [runId, setRunId] = useState<string | null>(null);
  const [submissionId, setSubmissionId] = useState<string | null>(null);
  const codeRef = useRef(problem.starter_code[language] ?? "");
  const queryClient = useQueryClient();

  const chooseLanguage = useCallback(
    (next: string) => {
      setLanguage(next);
      saveLanguage(draftKey, next);
    },
    [draftKey],
  );
  const handleCodeChange = useCallback((next: string) => {
    codeRef.current = next;
  }, []);

  const runQuery = useRun(runId ?? undefined);
  const submissionQuery = useSubmission(submissionId ?? undefined);

  const handleJudgeEvent = useCallback(
    (event: { type: string; data: Record<string, unknown> }) => {
      if (runId && event.data.run_id === runId) void queryClient.invalidateQueries({ queryKey: ["run", runId] });
      if (submissionId && event.data.submission_id === submissionId) {
        void queryClient.invalidateQueries({ queryKey: ["submission", submissionId] });
      }
    },
    [runId, submissionId, queryClient],
  );
  useJudgeSocket(handleJudgeEvent, Boolean(runId ?? submissionId));

  const handledSubmission = useRef<string | null>(null);
  useEffect(() => {
    const submission = submissionQuery.data;
    if (!submission || (submission.status !== "COMPLETED" && submission.status !== "FAILED")) return;
    const key = `${submission.id}:${submission.status}`;
    if (handledSubmission.current === key) return;
    handledSubmission.current = key;

    void queryClient.invalidateQueries({ queryKey: ["standings", slug] });

    if (submission.status === "FAILED") {
      toast.error("The judge couldn't finish this submission", { description: "Please try submitting again." });
    } else if (submission.verdict === "ACCEPTED") {
      toast.success("Accepted!", { description: `${submission.passed_count}/${submission.total_count} tests passed.` });
    } else if (submission.verdict) {
      toast.error(VERDICT_LABEL[submission.verdict], {
        description: `${submission.passed_count}/${submission.total_count} tests passed.`,
      });
    }
  }, [submissionQuery.data, queryClient, slug]);

  const register = useMutation({
    mutationFn: () => registerForContest(slug),
    onSuccess: () => {
      toast.success("You're registered");
      void queryClient.invalidateQueries({ queryKey: ["contest"] });
    },
    onError: (error) => toast.error("Couldn't register", { description: isApiError(error) ? error.message : undefined }),
  });

  const runMutation = useMutation({
    mutationFn: () =>
      runContestCode(slug, label, { language, source_code: codeRef.current, mode: "custom", input: customInput }),
    onSuccess: (queued) => {
      setRunId(queued.id);
      setConsoleTab("output");
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "NOT_REGISTERED") {
        toast.error("Register for this contest first", { description: "Use the button below to join, then try again." });
        return;
      }
      toast.error("Couldn't run your code", { description: isApiError(error) ? error.message : undefined });
    },
  });

  const submitMutation = useMutation({
    mutationFn: () => submitContestCode(slug, label, { language, source_code: codeRef.current }),
    onSuccess: (queued) => {
      setSubmissionId(queued.id);
      setConsoleTab("results");
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "NOT_REGISTERED") {
        toast.error("Register for this contest first", { description: "Use the button below to join, then try again." });
        return;
      }
      toast.error("Couldn't submit your code", { description: isApiError(error) ? error.message : undefined });
    },
  });

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
      {!registered && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-accent/40 px-4 py-2 text-sm">
          <span>You&apos;re viewing this problem as a spectator — register to submit and appear on the standings.</span>
          <Button size="sm" onClick={() => register.mutate()} disabled={register.isPending}>
            Register
          </Button>
        </div>
      )}
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

      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] md:grid-cols-[minmax(340px,42%)_1fr]">
        <section
          aria-label="Problem statement"
          className={cn("min-h-0 overflow-y-auto border-r", mobileTab !== "problem" && "hidden md:block")}
        >
          <ContestProblemStatement label={label} points={points} problem={problem} />
        </section>

        <div className={cn("flex min-h-0 min-w-0 flex-col", mobileTab === "problem" && "hidden md:flex")}>
          <div className={cn("min-h-0 flex-1", mobileTab === "console" && "hidden md:block")}>
            <EditorPane
              key={`${slug}:${label}:${language}`}
              slug={draftKey}
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
            showAi={false}
            className={cn(
              "md:max-h-[42%] md:shrink-0",
              mobileTab === "code" && "hidden md:flex",
              mobileTab === "console" && "flex-1",
            )}
          />
        </div>
      </div>

      <ContestActionBar onRun={handleRun} onSubmit={handleSubmit} running={running} submitting={submitting} />
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
