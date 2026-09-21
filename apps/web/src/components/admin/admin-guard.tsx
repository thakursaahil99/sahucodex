"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { hasRole } from "@sahucodex/shared";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/admin", label: "Overview", exact: true },
  { href: "/admin/problems", label: "Problems", exact: false },
];

/**
 * Hides the admin area from people who are not admins. This is a courtesy: every admin API call is authorised on the
 * server, so a non-admin who bypasses this component simply receives 403s and sees no data.
 */
export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  const pathname = usePathname();

  if (!hasRole(user?.roles, "ADMIN")) {
    return (
      <div className="mx-auto flex max-w-md flex-col items-center py-20 text-center">
        <ShieldAlert className="mb-4 size-10 text-warning" aria-hidden />
        <h1 className="text-2xl font-bold">Administrators only</h1>
        <p className="mt-2 text-muted-foreground">Your account doesn&apos;t have permission to open this area.</p>
        <Button asChild className="mt-6">
          <Link href="/dashboard">Back to dashboard</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <nav aria-label="Admin sections" className="flex gap-1 border-b">
        {LINKS.map((link) => {
          const active = link.exact ? pathname === link.href : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
                active ? "border-brand-blue text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
