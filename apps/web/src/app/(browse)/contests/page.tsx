import type { Metadata } from "next";

import { ContestsList } from "@/components/contests/contests-list";

export const metadata: Metadata = {
  title: "Contests",
  description: "Timed contests with live standings.",
};

export default function ContestsPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">Contests</h1>
      <p className="mt-1 text-muted-foreground">Compete in timed contests and climb the live standings.</p>
      <div className="mt-6">
        <ContestsList />
      </div>
    </div>
  );
}
