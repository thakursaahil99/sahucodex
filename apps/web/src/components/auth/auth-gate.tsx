"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Logo } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { refreshSession } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";

/**
 * Client-side guard for signed-in pages. It is a UX layer only: every API call is authorised by
 * the server, so bypassing this component reveals no data.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status === "authenticated") return <>{children}</>;

  if (status === "unavailable") {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-5 px-4 text-center">
        <Logo />
        <div className="space-y-1.5">
          <h1 className="text-xl font-semibold">Can&apos;t reach SahuCodeX right now</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            The server isn&apos;t responding. Your session is still safe — try again in a moment.
          </p>
        </div>
        <Button
          onClick={() => {
            useAuthStore.getState().setStatus("loading");
            refreshSession().catch(() => useAuthStore.getState().setStatus("unavailable"));
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  // loading, or anonymous while the redirect is in flight
  return (
    <div className="min-h-dvh" role="status" aria-label="Loading your workspace">
      <div className="flex h-16 items-center gap-6 border-b px-6">
        <Skeleton className="size-8 rounded-lg" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="mx-auto max-w-6xl space-y-6 px-6 py-10">
        <Skeleton className="h-9 w-72" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  );
}
