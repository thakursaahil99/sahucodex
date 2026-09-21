"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";
import { SiteHeader } from "@/components/layout/site-header";
import { useAuthStore } from "@/lib/auth/store";

/** The coding workspace fills the viewport instead of sitting in a padded column. */
const WORKSPACE = /^\/problems\/[^/]+\/?$/;

/**
 * Chrome for pages anyone may open (problem list, problem page). Signed-in users get the full app shell with
 * navigation; visitors get the public header. Which one shows is UX only — the data itself is public either way.
 */
export function PageChrome({ children }: { children: ReactNode }) {
  const authenticated = useAuthStore((s) => s.status === "authenticated");
  const bleed = WORKSPACE.test(usePathname());

  if (authenticated) return <AppShell bleed={bleed}>{children}</AppShell>;
  return (
    <>
      <SiteHeader />
      <main id="main" className={bleed ? "" : "mx-auto w-full max-w-7xl px-4 py-8 sm:px-6"}>
        {children}
      </main>
    </>
  );
}
