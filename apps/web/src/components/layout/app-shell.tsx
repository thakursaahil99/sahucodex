"use client";

import { LogOut, Menu, Search, Settings, User as UserIcon, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { hasRole, NAV_ITEMS, type NavItem } from "@sahucodex/shared";

import { Logo } from "@/components/brand/logo";
import { CommandPalette, useCommandPalette } from "@/components/layout/command-palette";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { logout } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

function useNavItems(): NavItem[] {
  const user = useAuthStore((s) => s.user);
  const isAdmin = hasRole(user?.roles, "ADMIN");
  const profile: NavItem = {
    label: "Profile",
    href: user ? `/profile/${user.username}` : "/profile",
    available: Boolean(user),
    phase: 4,
  };
  const regular = NAV_ITEMS.filter((item) => !item.adminOnly);
  const admin = NAV_ITEMS.filter((item) => item.adminOnly && isAdmin);
  return [...regular, profile, ...admin];
}

function NavLink({
  item,
  onNavigate,
  className,
  showSoon = false,
}: {
  item: NavItem;
  onNavigate?: () => void;
  className?: string;
  /** Label unavailable items visibly (used in the roomy mobile menu; the desktop bar stays compact). */
  showSoon?: boolean;
}) {
  const pathname = usePathname();
  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
  const base = "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors";

  if (!item.available) {
    // Not a link: the page ships in a later phase, so don't send people to a 404.
    return (
      <span
        aria-disabled="true"
        title={`Coming in build phase ${item.phase}`}
        className={cn(base, "cursor-not-allowed text-muted-foreground/60", className)}
      >
        {item.label}
        <span className="sr-only"> (coming in build phase {item.phase})</span>
        {showSoon && (
          <span aria-hidden className="rounded-full border px-1.5 py-px text-[10px] leading-none font-normal">
            Soon
          </span>
        )}
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(base, active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground", className)}
    >
      {item.label}
    </Link>
  );
}

function UserMenu() {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  const initial = user.username.slice(0, 1).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label={`Account menu for ${user.username}`}>
          <span className="bg-brand-gradient flex size-8 items-center justify-center rounded-full text-sm font-semibold text-white">
            {initial}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel>
          <span className="block truncate text-sm font-medium text-foreground">{user.username}</span>
          <span className="block truncate">{user.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href={`/profile/${user.username}`}>
            <UserIcon aria-hidden /> Profile
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings aria-hidden /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut aria-hidden /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children, bleed = false }: { children: ReactNode; bleed?: boolean }) {
  const items = useNavItems();
  const [mobileOpen, setMobileOpen] = useState(false);
  const palette = useCommandPalette();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="xl:hidden"
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
            onClick={() => setMobileOpen((v) => !v)}
          >
            {mobileOpen ? <X aria-hidden /> : <Menu aria-hidden />}
          </Button>
          <Logo href="/dashboard" />

          <nav aria-label="Primary" className="ml-2 hidden items-center gap-0.5 xl:flex">
            {items.map((item) => (
              <NavLink key={item.label} item={item} />
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="hidden h-9 w-44 justify-between text-muted-foreground sm:flex 2xl:w-56"
              onClick={() => palette.setOpen(true)}
              aria-label="Search and commands (Ctrl+K)"
            >
              <span className="flex items-center gap-2">
                <Search aria-hidden /> Search…
              </span>
              <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">Ctrl K</kbd>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="sm:hidden"
              aria-label="Search and commands"
              onClick={() => palette.setOpen(true)}
            >
              <Search aria-hidden />
            </Button>
            <ThemeToggle />
            <UserMenu />
          </div>
        </div>

        {mobileOpen && (
          <nav id="mobile-nav" aria-label="Primary" className="border-t px-3 py-3 xl:hidden">
            <ul className="grid gap-1">
              {items.map((item) => (
                <li key={item.label}>
                  <NavLink item={item} onNavigate={() => setMobileOpen(false)} className="w-full" showSoon />
                </li>
              ))}
            </ul>
          </nav>
        )}
      </header>

      <main
        id="main"
        className={cn("w-full flex-1", bleed ? "min-h-0" : "mx-auto max-w-7xl px-4 py-8 sm:px-6")}
      >
        {children}
      </main>

      <CommandPalette open={palette.open} onOpenChange={palette.setOpen} />
    </div>
  );
}
