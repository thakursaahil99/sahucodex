import type { Metadata } from "next";

import { Assistant } from "@/components/ai/assistant";

export const metadata: Metadata = { title: "AI Assistant" };

const SLUG = /^[a-z0-9-]{1,80}$/;

export default async function AiPage({ searchParams }: { searchParams: Promise<{ problem?: string }> }) {
  const { problem } = await searchParams;
  return <Assistant problemSlug={problem && SLUG.test(problem) ? problem : undefined} />;
}
