"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Laptop, MailCheck, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";


import { describeAuthError } from "@/components/auth/errors";
import { SolvedBreakdown } from "@/components/profiles/solved-breakdown";
import { StreakCard } from "@/components/profiles/streak-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { useMe, useSessions } from "@/lib/api/hooks";
import type { MessageResponse, SessionInfo } from "@/lib/api/types";
import { useAuthStore } from "@/lib/auth/store";
import { describeUserAgent, timeAgo } from "@/lib/format";
import { useProfileStats } from "@/lib/profiles/api";
import { formatDate } from "@/lib/utils";

const UPCOMING = [
  { phase: 6, title: "Contests", body: "Timed contests with penalties and a live leaderboard." },
] as const;

export function DashboardView() {
  const storeUser = useAuthStore((s) => s.user);
  const { data: fetched } = useMe();
  const user = fetched ?? storeUser;
  const stats = useProfileStats(user?.username ?? "");

  if (!user) return <DashboardSkeleton />;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">
            Welcome back, <span className="text-gradient">{user.username}</span>
          </h1>
          <p className="text-muted-foreground">Your workspace is live. Here&apos;s where your account stands.</p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/profile/${user.username}`}>View public profile</Link>
        </Button>
      </div>

      {stats.data && (
        <div className="grid gap-6 lg:grid-cols-3">
          <SolvedBreakdown
            solved={stats.data.solved}
            totalSubmissions={stats.data.total_submissions}
            acceptanceRate={stats.data.acceptance_rate}
          />
          <StreakCard streak={stats.data.streak} />
          <div className="lg:col-span-1">
            <Card className="h-full">
              <CardHeader>
                <CardTitle>Achievements</CardTitle>
                <CardDescription>
                  {stats.data.achievements.filter((a) => a.earned).length} of {stats.data.achievements.length} earned
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline" size="sm">
                  <Link href={`/profile/${user.username}`}>See all achievements</Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <GettingStarted emailVerified={user.email_verified} solved={stats.data?.solved.total ?? 0} />
          <SessionsCard />
        </div>
        <div className="space-y-6">
          <AccountCard email={user.email} roles={user.roles} joined={user.created_at} verified={user.email_verified} />
          <Roadmap />
        </div>
      </div>
    </div>
  );
}

function GettingStarted({ emailVerified, solved }: { emailVerified: boolean; solved: number }) {
  const resend = useMutation({
    mutationFn: () => api<MessageResponse>("/auth/verify-email/request", { method: "POST" }),
    onSuccess: () => toast.success("Verification email sent", { description: "Check your inbox for the link." }),
    onError: (error) => toast.error("Couldn't send the email", { description: describeAuthError(error) }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Getting started</CardTitle>
        <CardDescription>Steps to get the most out of SahuCodeX.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          <Step done title="Create your account" />
          <Step
            done={emailVerified}
            title="Verify your email"
            detail={emailVerified ? "Your address is confirmed." : "Confirm your address so you can recover your account."}
            action={
              !emailVerified && (
                <Button size="sm" variant="outline" loading={resend.isPending} onClick={() => resend.mutate()}>
                  <MailCheck aria-hidden /> Resend email
                </Button>
              )
            }
          />
          <Step
            done={solved > 0}
            title="Solve your first problem"
            detail={solved > 0 ? `You've solved ${solved} problem${solved === 1 ? "" : "s"}.` : "Pick one from the problem list and submit a solution."}
            action={
              solved === 0 && (
                <Button asChild size="sm" variant="outline">
                  <Link href="/problems">Browse problems</Link>
                </Button>
              )
            }
          />
        </ul>
      </CardContent>
    </Card>
  );
}

function Step({
  done,
  title,
  detail,
  action,
}: {
  done: boolean;
  title: string;
  detail?: string;
  action?: React.ReactNode;
}) {
  const Icon = done ? CheckCircle2 : Circle;
  return (
    <li className="flex items-center gap-3 py-3.5 first:pt-0 last:pb-0">
      <Icon className={done ? "size-5 shrink-0 text-success" : "size-5 shrink-0 text-muted-foreground"} aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-medium">
          {title}
          <span className="sr-only">{done ? " — completed" : " — not completed"}</span>
        </p>
        {detail && <p className="text-sm text-muted-foreground">{detail}</p>}
      </div>
      {action}
    </li>
  );
}

function AccountCard({
  email,
  roles,
  joined,
  verified,
}: {
  email: string;
  roles: string[];
  joined: string;
  verified: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="flex flex-wrap items-center gap-2 font-medium break-all">
              {email}
              <Badge variant={verified ? "success" : "warning"}>{verified ? "Verified" : "Unverified"}</Badge>
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Role</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {roles.map((role) => (
                <Badge key={role} variant={role === "USER" ? "outline" : "secondary"}>
                  {role}
                </Badge>
              ))}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Member since</dt>
            <dd className="font-medium">{formatDate(joined, { dateStyle: "long" })}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

function SessionsCard() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, refetch } = useSessions();
  const revoke = useMutation({
    mutationFn: (id: string) => api<void>(`/auth/sessions/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      toast.success("Session signed out");
      await queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => toast.error("Couldn't sign that session out", { description: describeAuthError(error) }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-5 text-brand-cyan" aria-hidden /> Active sessions
        </CardTitle>
        <CardDescription>Devices currently signed in to your account. Sign out any you don&apos;t recognise.</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending && (
          <div className="space-y-3" role="status" aria-label="Loading sessions">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        )}
        {isError && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
            <span>Couldn&apos;t load your sessions.</span>
            <Button size="sm" variant="outline" onClick={() => refetch()}>
              Retry
            </Button>
          </div>
        )}
        {data && data.length === 0 && <p className="text-sm text-muted-foreground">No other sessions.</p>}
        {data && data.length > 0 && (
          <ul className="space-y-3">
            {data.map((session) => (
              <SessionRow key={session.id} session={session} onRevoke={() => revoke.mutate(session.id)} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function SessionRow({ session, onRevoke }: { session: SessionInfo; onRevoke: () => void }) {
  const device = describeUserAgent(session.user_agent);
  return (
    <li className="flex items-center gap-3 rounded-lg border p-3">
      <Laptop className="size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
          {device}
          {session.current && <Badge variant="success">This device</Badge>}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {session.ip_address ?? "Unknown IP"} · active {timeAgo(session.last_active_at)}
        </p>
      </div>
      {!session.current && (
        <ConfirmDialog
          trigger={
            <Button size="sm" variant="outline">
              Sign out
            </Button>
          }
          title="Sign out this device?"
          description={`${device} will be signed out immediately and will need to log in again.`}
          confirmLabel="Sign out device"
          destructive
          onConfirm={onRevoke}
        />
      )}
    </li>
  );
}

function Roadmap() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>What&apos;s coming</CardTitle>
        <CardDescription>SahuCodeX is being built in phases.</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="space-y-3.5">
          {UPCOMING.map((item) => (
            <li key={item.phase} className="flex gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                {item.phase}
              </span>
              <div>
                <p className="text-sm font-medium">{item.title}</p>
                <p className="text-xs text-muted-foreground">{item.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8" role="status" aria-label="Loading dashboard">
      <Skeleton className="h-10 w-80" />
      <div className="grid gap-6 lg:grid-cols-3">
        <Skeleton className="h-64 lg:col-span-2" />
        <Skeleton className="h-64" />
      </div>
    </div>
  );
}
