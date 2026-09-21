"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Only the digest is surfaced to users; the full error is in the server log.
    console.error("Unhandled UI error", error.digest ?? "");
  }, [error]);

  return (
    <main id="main" className="mx-auto flex min-h-dvh max-w-xl flex-col items-center justify-center px-4 text-center">
      <h1 className="text-2xl font-bold tracking-tight">Something went wrong</h1>
      <p className="mt-3 text-muted-foreground">An unexpected error occurred. You can try again.</p>
      {error.digest && <p className="mt-2 font-mono text-xs text-muted-foreground">Reference: {error.digest}</p>}
      <Button className="mt-8" onClick={reset}>
        Try again
      </Button>
    </main>
  );
}
