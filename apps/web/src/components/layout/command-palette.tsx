"use client";

import { Command } from "cmdk";
import { Bot, LayoutDashboard, LogOut, Monitor, Moon, Search, Sun, Trophy, User as UserIcon, Users } from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ComponentType } from "react";

import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/lib/auth/store";
import { logout } from "@/lib/auth/session";

interface Action {
  id: string;
  label: string;
  Icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  group: "Navigate" | "Search" | "Preferences" | "Account";
  run?: () => void;
  /** Set for features that ship in a later build phase; shown but not selectable. */
  phase?: number;
}

/** Ctrl/⌘ + K. Actions for unbuilt features are listed but disabled, so nothing links to a 404. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const { setTheme } = useTheme();
  const username = useAuthStore((s) => s.user?.username);

  const go = useCallback(
    (href: string) => () => {
      router.push(href);
    },
    [router],
  );

  const actions: Action[] = [
    { id: "dashboard", label: "Open dashboard", Icon: LayoutDashboard, group: "Navigate", run: go("/dashboard") },
    { id: "problems", label: "Search problems", Icon: Search, group: "Search", run: go("/problems") },
    { id: "users", label: "Search users", Icon: Users, group: "Search", phase: 7 },
    { id: "contests", label: "Open contests", Icon: Trophy, group: "Navigate", run: go("/contests") },
    {
      id: "profile",
      label: username ? `Open profile (${username})` : "Open profile",
      Icon: UserIcon,
      group: "Navigate",
      run: username ? go(`/profile/${username}`) : undefined,
    },
    { id: "ai", label: "Open AI Assistant", Icon: Bot, group: "Navigate", run: go("/ai") },
    { id: "theme-light", label: "Theme: Light", Icon: Sun, group: "Preferences", run: () => setTheme("light") },
    { id: "theme-dark", label: "Theme: Dark", Icon: Moon, group: "Preferences", run: () => setTheme("dark") },
    { id: "theme-system", label: "Theme: System", Icon: Monitor, group: "Preferences", run: () => setTheme("system") },
    {
      id: "logout",
      label: "Log out",
      Icon: LogOut,
      group: "Account",
      run: () => {
        void logout();
      },
    },
  ];
  const groups = ["Navigate", "Search", "Preferences", "Account"] as const;

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      overlayClassName="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0"
      contentClassName="fixed top-[18%] left-1/2 z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border bg-popover text-popover-foreground shadow-2xl"
    >
      <div className="flex items-center gap-3 border-b px-4">
        <Search className="size-4 text-muted-foreground" aria-hidden />
        <Command.Input
          placeholder="Type a command or search…"
          className="h-14 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="px-3 py-8 text-center text-sm text-muted-foreground">No results.</Command.Empty>
        {groups.map((group) => (
          <Command.Group
            key={group}
            heading={group}
            className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
          >
            {actions
              .filter((action) => action.group === group)
              .map(({ id, label, Icon, run, phase }) => (
                <Command.Item
                  key={id}
                  value={label}
                  disabled={!run}
                  onSelect={() => {
                    if (!run) return;
                    onOpenChange(false);
                    run();
                  }}
                  className="flex cursor-default items-center gap-3 rounded-lg px-3 py-2.5 text-sm select-none data-[disabled=true]:opacity-50 data-[selected=true]:bg-muted"
                >
                  <Icon className="size-4 text-muted-foreground" aria-hidden />
                  {label}
                  {phase && (
                    <Badge variant="outline" className="ml-auto">
                      Soon
                    </Badge>
                  )}
                </Command.Item>
              ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}

/** Registers the global Ctrl/⌘+K shortcut. */
export function useCommandPaletteShortcut(toggle: () => void) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);
}

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useCommandPaletteShortcut(useCallback(() => setOpen((v) => !v), []));
  return { open, setOpen };
}
