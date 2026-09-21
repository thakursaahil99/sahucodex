import { Badge, type badgeVariants } from "@/components/ui/badge";
import type { Verdict } from "@/lib/submissions/types";

type BadgeVariant = NonNullable<Parameters<typeof badgeVariants>[0]>["variant"];

export const VERDICT_LABEL: Record<Verdict, string> = {
  ACCEPTED: "Accepted",
  WRONG_ANSWER: "Wrong Answer",
  TIME_LIMIT_EXCEEDED: "Time Limit Exceeded",
  MEMORY_LIMIT_EXCEEDED: "Memory Limit Exceeded",
  RUNTIME_ERROR: "Runtime Error",
  COMPILATION_ERROR: "Compilation Error",
  SYSTEM_ERROR: "Judge Error",
};

const VERDICT_VARIANT: Record<Verdict, BadgeVariant> = {
  ACCEPTED: "success",
  WRONG_ANSWER: "warning",
  TIME_LIMIT_EXCEEDED: "warning",
  MEMORY_LIMIT_EXCEEDED: "warning",
  RUNTIME_ERROR: "warning",
  COMPILATION_ERROR: "secondary",
  SYSTEM_ERROR: "outline",
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return <Badge variant={VERDICT_VARIANT[verdict]}>{VERDICT_LABEL[verdict]}</Badge>;
}

export function StatusLabel({ status }: { status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" }) {
  if (status === "QUEUED") return <Badge variant="outline">Queued</Badge>;
  if (status === "RUNNING") return <Badge variant="accent">Running…</Badge>;
  if (status === "FAILED") return <Badge variant="outline">Judge Error</Badge>;
  return null; // COMPLETED: the caller shows the verdict badge instead
}

export function formatMs(ms: number | null): string {
  return ms === null ? "—" : `${ms} ms`;
}

export function formatKb(kb: number | null): string {
  if (kb === null) return "—";
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`;
}
