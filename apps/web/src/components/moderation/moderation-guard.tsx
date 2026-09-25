"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { hasRole } from "@sahucodex/shared";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth/store";

/**
 * Hides the moderation queue from anyone below MODERATOR. Same courtesy-only role as AdminGuard — every
 * `/moderation/*` API call is authorised server-side via `require_role(MODERATOR)`, so bypassing this just gets a 403.
 */
export function ModerationGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (!hasRole(user?.roles, "MODERATOR")) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center py-20 text-center">
        <ShieldAlert className="mb-4 size-10 text-warning" aria-hidden />
        <h1 className="text-2xl font-bold">Moderators only</h1>
        <p className="mt-2 text-muted-foreground">Your account doesn&apos;t have permission to open this area.</p>
        <Button asChild className="mt-6">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    );
  }

  return <>{children}</>;
}
