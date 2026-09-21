"use client";

import { CalendarDays, Globe, Link2, MapPin } from "lucide-react";

import { AchievementsGrid } from "@/components/profiles/achievements-grid";
import { ActivityCalendar } from "@/components/profiles/activity-calendar";
import { ProfileAvatar } from "@/components/profiles/avatar";
import { SolvedBreakdown } from "@/components/profiles/solved-breakdown";
import { StreakCard } from "@/components/profiles/streak-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api/http";
import { useProfile, useProfileStats } from "@/lib/profiles/api";
import { formatDate } from "@/lib/utils";

export function ProfileView({ username }: { username: string }) {
  const profile = useProfile(username);
  const stats = useProfileStats(username);

  if (profile.isPending || stats.isPending) return <ProfileSkeleton />;

  if (profile.isError || stats.isError) {
    const error = profile.error ?? stats.error;
    const missing = isApiError(error) && error.status === 404;
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="text-2xl font-bold">{missing ? "User not found" : "Couldn't load this profile"}</h1>
        <p className="mt-2 text-muted-foreground">
          {missing ? "They may not exist, or the link is wrong." : "Check your connection and try again."}
        </p>
        {!missing && (
          <Button
            className="mt-6"
            onClick={() => {
              void profile.refetch();
              void stats.refetch();
            }}
          >
            Retry
          </Button>
        )}
      </div>
    );
  }

  const p = profile.data;
  const s = stats.data;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-start gap-4">
        <ProfileAvatar username={p.username} avatarUrl={p.avatar_url} />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{p.username}</h1>
          {p.bio && <p className="mt-1 max-w-2xl text-muted-foreground">{p.bio}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            {p.country && (
              <span className="flex items-center gap-1">
                <MapPin className="size-3.5" aria-hidden /> {p.country}
              </span>
            )}
            {p.website && (
              <a
                href={p.website}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 hover:text-foreground hover:underline"
              >
                <Globe className="size-3.5" aria-hidden /> Website
              </a>
            )}
            {p.github_url && (
              <a
                href={p.github_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 hover:text-foreground hover:underline"
              >
                <Link2 className="size-3.5" aria-hidden /> GitHub
              </a>
            )}
            <span className="flex items-center gap-1">
              <CalendarDays className="size-3.5" aria-hidden /> Joined {formatDate(p.joined_at, { dateStyle: "long" })}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <ActivityCalendar activity={s.activity} />
          <AchievementsGrid achievements={s.achievements} />
        </div>
        <div className="space-y-6">
          <StreakCard streak={s.streak} />
          <SolvedBreakdown solved={s.solved} totalSubmissions={s.total_submissions} acceptanceRate={s.acceptance_rate} />
        </div>
      </div>
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6" role="status" aria-label="Loading profile">
      <div className="flex gap-4">
        <Skeleton className="size-16 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-5 w-72" />
        </div>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="h-64 lg:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
