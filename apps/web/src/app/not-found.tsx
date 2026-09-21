import Link from "next/link";

import { SiteHeader } from "@/components/layout/site-header";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="mx-auto flex max-w-xl flex-col items-center px-4 py-28 text-center">
        <p className="font-mono text-sm text-brand-cyan">404</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Page not found</h1>
        <p className="mt-3 text-muted-foreground">That page doesn&apos;t exist, or it moved.</p>
        <Button asChild variant="gradient" className="mt-8">
          <Link href="/">Back to home</Link>
        </Button>
      </main>
    </>
  );
}
