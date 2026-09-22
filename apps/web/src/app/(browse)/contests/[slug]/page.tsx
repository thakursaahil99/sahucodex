import type { Metadata } from "next";

import { ContestOverview } from "@/components/contests/contest-overview";

type Params = Promise<{ slug: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  return { title: slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) };
}

export default async function ContestPage({ params }: { params: Params }) {
  const { slug } = await params;
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <ContestOverview slug={slug} />
    </div>
  );
}
