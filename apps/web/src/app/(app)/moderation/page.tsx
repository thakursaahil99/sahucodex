import type { Metadata } from "next";

import { ModerationGuard } from "@/components/moderation/moderation-guard";
import { ReportsQueue } from "@/components/moderation/reports-queue";

export const metadata: Metadata = { title: "Moderation" };

export default function ModerationPage() {
  return (
    <ModerationGuard>
      <div className="mx-auto max-w-3xl">
        <h1 className="text-2xl font-bold tracking-tight">Moderation</h1>
        <p className="mt-1 text-muted-foreground">Reports filed against discussions and comments.</p>
        <div className="mt-6">
          <ReportsQueue />
        </div>
      </div>
    </ModerationGuard>
  );
}
