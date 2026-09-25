"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, MessageSquareOff, MessageSquareReply } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { markAllNotificationsRead, markNotificationRead, useNotifications, useUnreadCount } from "@/lib/community/api";
import type { NotificationOut } from "@/lib/community/types";
import { timeAgo } from "@/lib/format";
import { useAuthStore } from "@/lib/auth/store";

function notificationText(n: NotificationOut): { text: string; href: string | null } {
  const actor = typeof n.data.actor_username === "string" ? n.data.actor_username : "Someone";
  const discussionId = typeof n.data.discussion_id === "string" ? n.data.discussion_id : null;
  const title = typeof n.data.discussion_title === "string" ? n.data.discussion_title : "your thread";

  if (n.type === "DISCUSSION_REPLY") {
    return { text: `${actor} replied to "${title}"`, href: discussionId ? `/discussions/${discussionId}` : null };
  }
  if (n.type === "CONTENT_REMOVED") {
    return { text: "A moderator removed one of your posts", href: null };
  }
  return { text: "New activity", href: discussionId ? `/discussions/${discussionId}` : null };
}

function NotificationRow({ notification }: { notification: NotificationOut }) {
  const queryClient = useQueryClient();
  const { text, href } = notificationText(notification);

  const markRead = useMutation({
    mutationFn: () => markNotificationRead(notification.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
    },
  });

  const Icon = notification.type === "CONTENT_REMOVED" ? MessageSquareOff : MessageSquareReply;

  const body = (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <p className={notification.read ? "text-muted-foreground" : "font-medium"}>{text}</p>
        <p className="text-xs text-muted-foreground">{timeAgo(notification.created_at)}</p>
      </div>
      {!notification.read && <span className="ml-auto mt-1 size-2 shrink-0 rounded-full bg-brand-violet" aria-hidden />}
    </div>
  );

  return (
    <DropdownMenuItem
      className="items-start whitespace-normal py-2.5"
      onSelect={() => {
        if (!notification.read) markRead.mutate();
      }}
      asChild={Boolean(href)}
    >
      {href ? <Link href={href}>{body}</Link> : body}
    </DropdownMenuItem>
  );
}

/** Bell icon in the app header. Only rendered for signed-in users (see AppShell). */
export function NotificationBell() {
  const authenticated = useAuthStore((s) => s.status === "authenticated");
  const { data: unread } = useUnreadCount(authenticated);
  const { data: notifications } = useNotifications();
  const queryClient = useQueryClient();

  const markAll = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["notifications"] });
      void queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
    },
  });

  if (!authenticated) return null;
  const count = unread?.count ?? 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`Notifications${count > 0 ? ` (${count} unread)` : ""}`}>
          <Bell aria-hidden />
          {count > 0 && (
            <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-brand-violet text-[10px] font-semibold text-white">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between px-2 py-1.5">
          <DropdownMenuLabel className="p-0">Notifications</DropdownMenuLabel>
          {count > 0 && (
            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => markAll.mutate()}>
              Mark all read
            </Button>
          )}
        </div>
        <DropdownMenuSeparator />
        {!notifications || notifications.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>
        ) : (
          <div className="max-h-96 overflow-y-auto">
            {notifications.map((n) => (
              <NotificationRow key={n.id} notification={n} />
            ))}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
