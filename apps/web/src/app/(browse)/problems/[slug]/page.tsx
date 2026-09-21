import type { Metadata } from "next";

import { ProblemWorkspace } from "@/components/problems/problem-workspace";

type Params = Promise<{ slug: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { slug } = await params;
  // The title is refined client-side once the problem loads; this keeps the tab meaningful for crawlers too.
  return { title: slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) };
}

export default async function ProblemPage({ params }: { params: Params }) {
  const { slug } = await params;
  return <ProblemWorkspace slug={slug} />;
}
