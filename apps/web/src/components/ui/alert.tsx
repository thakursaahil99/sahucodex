import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

const icons = { error: AlertCircle, success: CheckCircle2, info: Info } as const;
const tones = {
  error: "border-destructive/40 bg-destructive/10",
  success: "border-success/40 bg-success/10",
  info: "border-brand-cyan/40 bg-accent",
} as const;
const iconTones = { error: "text-destructive", success: "text-success", info: "text-accent-foreground" } as const;

interface AlertProps extends Omit<React.ComponentProps<"div">, "title"> {
  tone?: keyof typeof tones;
  title?: React.ReactNode;
}

/** Errors use role="alert" (announced immediately); other tones use role="status" (polite). */
function Alert({ tone = "info", title, className, children, ...props }: AlertProps) {
  const Icon = icons[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-lg border p-3 text-sm", tones[tone], className)}
      {...props}
    >
      <Icon className={cn("mt-0.5 size-4 shrink-0", iconTones[tone])} aria-hidden />
      <div className="space-y-0.5">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-foreground/90">{children}</div>}
      </div>
    </div>
  );
}

export { Alert };
