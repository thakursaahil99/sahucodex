"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { Markdown } from "@/components/ui/markdown";
import { Skeleton } from "@/components/ui/skeleton";
import type { AiFeature } from "@/lib/ai/types";

export type AiOutput =
  | { status: "loading"; feature: AiFeature }
  | { status: "ready"; feature: AiFeature; content: string; model: string; hintNumber?: number }
  | { status: "error"; feature: AiFeature; message: string };

const LABEL: Record<AiFeature, string> = { hint: "Hint", explain: "Explanation", review: "Review" };

/** The "SahuCodeX AI" tab: one generation, always visibly labelled as an AI suggestion and never as a verdict. */
export function AiResultTab({ output, problemSlug }: { output: AiOutput | null; problemSlug?: string }) {
  if (!output) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-sm">
        <p className="font-medium">No AI suggestion yet</p>
        <p className="mt-1 text-muted-foreground">
          Use <strong>AI Hint</strong>, <strong>AI Review</strong> or <strong>Explain</strong> below. SahuCodeX AI only
          sees the public problem statement and your code — never hidden tests.
        </p>
      </div>
    );
  }

  if (output.status === "loading") {
    return (
      <div className="space-y-3" role="status" aria-live="polite">
        <p className="text-sm text-muted-foreground">
          SahuCodeX AI is working on your {LABEL[output.feature].toLowerCase()}… a local model can take a little while.
        </p>
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (output.status === "error") {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm" role="alert">
        <p className="font-medium">Couldn&apos;t get an AI {LABEL[output.feature].toLowerCase()}</p>
        <p className="mt-1 text-muted-foreground">{output.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        <Sparkles className="size-3.5 text-brand-violet" aria-hidden />
        <span>
          <strong className="text-foreground">
            AI {LABEL[output.feature].toLowerCase()}
            {output.hintNumber ? ` #${output.hintNumber}` : ""}
          </strong>{" "}
          from {output.model} — a suggestion, not a verdict. Only <strong>Submit</strong> tells you whether your code is
          correct.
        </span>
      </div>
      <Markdown>{output.content}</Markdown>
      {problemSlug && (
        <p className="text-xs">
          <Link href={`/ai?problem=${encodeURIComponent(problemSlug)}`} className="text-link underline underline-offset-2">
            Continue in chat about this problem →
          </Link>
        </p>
      )}
    </div>
  );
}
