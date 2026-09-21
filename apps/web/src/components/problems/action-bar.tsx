"use client";

import { Bot, FileSearch, Lightbulb, Loader2, Play, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { AiFeature } from "@/lib/ai/types";

const AI_ACTIONS: Array<{ feature: AiFeature; label: string; Icon: typeof Lightbulb; hint: string }> = [
  { feature: "hint", label: "AI Hint", Icon: Lightbulb, hint: "A progressive hint — a nudge, never the solution" },
  { feature: "review", label: "AI Review", Icon: FileSearch, hint: "A review of your code (an opinion, not a verdict)" },
  { feature: "explain", label: "Explain", Icon: Bot, hint: "Explains what your code does and its complexity" },
];

interface ActionBarProps {
  onRun: () => void;
  onSubmit: () => void;
  running: boolean;
  submitting: boolean;
  onAi: (feature: AiFeature) => void;
  /** The AI request currently in flight, if any — its button spins and the others wait. */
  aiBusy: AiFeature | null;
  /** Set when the server has no model configured; the AI buttons then explain why instead of failing on click. */
  aiUnavailable?: string;
}

/** Run · Submit · AI Hint · AI Review · Explain. */
export function ActionBar({ onRun, onSubmit, running, submitting, onAi, aiBusy, aiUnavailable }: ActionBarProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-2 border-t bg-card px-3 py-2"
      role="toolbar"
      aria-label="Problem actions"
    >
      <Button variant="outline" size="sm" onClick={onRun} disabled={running || submitting}>
        {running ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />} Run
      </Button>
      <Button variant="default" size="sm" onClick={onSubmit} disabled={running || submitting}>
        {submitting ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />} Submit
      </Button>

      {AI_ACTIONS.map(({ feature, label, Icon, hint }) => {
        const busy = aiBusy === feature;
        return (
          <Button
            key={feature}
            variant="outline"
            size="sm"
            aria-disabled={aiUnavailable ? "true" : undefined}
            disabled={aiBusy !== null}
            title={aiUnavailable ?? hint}
            className={aiUnavailable ? "opacity-60" : undefined}
            onClick={() => {
              if (aiUnavailable) {
                toast.info(`${label} isn't set up yet`, { description: aiUnavailable });
                return;
              }
              onAi(feature);
            }}
          >
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Icon aria-hidden />} {label}
          </Button>
        );
      })}
      <p className="ml-auto hidden text-xs text-muted-foreground lg:block">
        <kbd className="rounded border bg-muted px-1 font-mono">Ctrl</kbd>+<kbd className="rounded border bg-muted px-1 font-mono">Enter</kbd> runs ·{" "}
        <kbd className="rounded border bg-muted px-1 font-mono">Ctrl</kbd>+<kbd className="rounded border bg-muted px-1 font-mono">S</kbd> saves a draft
      </p>
    </div>
  );
}
