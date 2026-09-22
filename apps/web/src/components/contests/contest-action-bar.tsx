"use client";

import { Loader2, Play, Send } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ContestActionBarProps {
  onRun: () => void;
  onSubmit: () => void;
  running: boolean;
  submitting: boolean;
}

/** Run · Submit only — deliberately no AI here: SahuCodeX AI is switched off for contest problems while a contest is
 * running, for fairness between participants. */
export function ContestActionBar({ onRun, onSubmit, running, submitting }: ContestActionBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-t bg-card px-3 py-2" role="toolbar" aria-label="Problem actions">
      <Button variant="outline" size="sm" onClick={onRun} disabled={running || submitting}>
        {running ? <Loader2 className="animate-spin" aria-hidden /> : <Play aria-hidden />} Run
      </Button>
      <Button variant="default" size="sm" onClick={onSubmit} disabled={running || submitting}>
        {submitting ? <Loader2 className="animate-spin" aria-hidden /> : <Send aria-hidden />} Submit
      </Button>
      <p className="ml-auto text-xs text-muted-foreground">AI assistance is off during the contest</p>
    </div>
  );
}
