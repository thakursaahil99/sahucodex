import type { Metadata } from "next";

import { ContestWorkspace } from "@/components/contests/contest-workspace";

type Params = Promise<{ slug: string; label: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug, label } = await params;
  return { title: `${label} — ${slug.replace(/-/g, " ")}` };
}

export default async function ContestProblemPage({ params }: { params: Params }) {
  const { slug, label } = await params;
  return <ContestWorkspace slug={slug} label={label} />;
}
