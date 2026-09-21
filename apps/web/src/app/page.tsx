import { ArrowRight, BrainCircuit, Flame, Gauge, LockKeyhole, ShieldCheck, Swords, Trophy } from "lucide-react";
import Link from "next/link";

import { BRAND } from "@sahucodex/shared";

import { LogoMark } from "@/components/brand/logo";
import { SiteHeader } from "@/components/layout/site-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const PILLARS = [
  {
    icon: Swords,
    title: "Solve problems",
    body: `${BRAND.judge} runs your code in an isolated, resource-limited sandbox and returns a deterministic verdict — the same code always earns the same result.`,
    tone: "text-brand-blue",
  },
  {
    icon: Trophy,
    title: "Compete in contests",
    body: "Timed contests with penalties, live standings and final rankings. Every score is calculated on the server, never trusted from the client.",
    tone: "text-brand-violet",
  },
  {
    icon: BrainCircuit,
    title: "Learn with AI",
    body: `${BRAND.ai} runs on your own hardware through Ollama. It gives progressive hints that teach the idea instead of spoiling the answer.`,
    tone: "text-brand-cyan",
  },
] as const;

const FEATURES = [
  { icon: ShieldCheck, title: "Sandboxed by design", body: "No network, no host access, hard CPU, memory and time limits." },
  { icon: Gauge, title: "Real-time verdicts", body: "Watch a submission move from queued to running to judged, live." },
  { icon: LockKeyhole, title: "Private by default", body: "Local open-source models. No paid API required, no code sent away." },
  { icon: Flame, title: "Streaks and progress", body: "XP, streaks and achievements computed from your real activity." },
] as const;

export default function LandingPage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        {/* Hero */}
        <section className="relative isolate overflow-hidden">
          <div className="bg-grid pointer-events-none absolute inset-0 -z-10" aria-hidden />
          <div className="glow-blue pointer-events-none absolute -top-40 left-1/2 -z-10 h-[520px] w-[720px] -translate-x-[85%] opacity-60" aria-hidden />
          <div className="glow-violet pointer-events-none absolute -top-24 left-1/2 -z-10 h-[460px] w-[640px] -translate-x-[10%] opacity-60" aria-hidden />

          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-16 pb-20 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:pt-24 lg:pb-28">
            <div>
              <Badge variant="accent" className="mb-6">
                <span className="size-1.5 rounded-full bg-brand-cyan" aria-hidden />
                Early access · foundation build
              </Badge>
              <p className="flex items-center gap-3 text-2xl font-semibold tracking-tight sm:text-3xl">
                <LogoMark className="size-9 sm:size-10" />
                {BRAND.name}
              </p>
              <h1 className="mt-5 text-5xl leading-[1.05] font-bold tracking-tight text-balance sm:text-6xl lg:text-7xl">
                <span className="text-gradient">Code. Compete. Learn.</span>
              </h1>
              <div className="mt-6 space-y-1 text-lg text-muted-foreground sm:text-xl">
                {BRAND.pitch.map((line) => (
                  <p key={line}>{line}</p>
                ))}
              </div>
              <div className="mt-9 flex flex-wrap gap-3">
                <Button asChild variant="gradient" size="lg">
                  <Link href="/register">
                    Start Coding <ArrowRight aria-hidden />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/problems">Explore Problems</Link>
                </Button>
              </div>
            </div>

            <CodeWindow />
          </div>
        </section>

        {/* Pillars */}
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6" aria-labelledby="pillars-heading">
          <h2 id="pillars-heading" className="sr-only">
            What you can do on {BRAND.name}
          </h2>
          <div className="grid gap-5 md:grid-cols-3">
            {PILLARS.map(({ icon: Icon, title, body, tone }) => (
              <article key={title} className="rounded-2xl border bg-card p-6 shadow-sm transition-colors hover:border-brand-blue/50">
                <div className={`mb-4 inline-flex size-11 items-center justify-center rounded-xl bg-muted ${tone}`}>
                  <Icon className="size-5" aria-hidden />
                </div>
                <h3 className="text-lg font-semibold">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </article>
            ))}
          </div>
        </section>

        {/* Features */}
        <section className="border-y bg-muted/40">
          <div className="mx-auto grid max-w-6xl gap-x-8 gap-y-10 px-4 py-14 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <div key={title}>
                <Icon className="mb-3 size-5 text-brand-cyan" aria-hidden />
                <h3 className="font-medium">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Closing CTA */}
        <section className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">Ready for your first accepted solution?</h2>
          <p className="mt-3 text-muted-foreground">Create a free account. Everything runs on open-source software.</p>
          <Button asChild variant="gradient" size="lg" className="mt-8">
            <Link href="/register">Create your account</Link>
          </Button>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:px-6">
          <p>
            © {new Date().getFullYear()} {BRAND.name}. {BRAND.tagline}
          </p>
          <p>Built with Next.js, FastAPI, PostgreSQL, Redis and Ollama.</p>
        </div>
      </footer>
    </>
  );
}

/** Decorative editor mock-up. The snippet is illustrative source text, not a real judge result. */
function CodeWindow() {
  return (
    <div className="relative">
      <div className="glow-violet pointer-events-none absolute -inset-6 -z-10 opacity-40 blur-2xl" aria-hidden />
      <figure className="overflow-hidden rounded-2xl border bg-card shadow-2xl shadow-brand-blue/10">
        <div className="flex items-center gap-2 border-b bg-muted/60 px-4 py-3">
          <span className="size-3 rounded-full bg-[#ff5f57]" aria-hidden />
          <span className="size-3 rounded-full bg-[#febc2e]" aria-hidden />
          <span className="size-3 rounded-full bg-[#28c840]" aria-hidden />
          <figcaption className="ml-3 font-mono text-xs text-muted-foreground">two_sum.py</figcaption>
        </div>
        <pre
          className="overflow-x-auto p-5 font-mono text-[13px] leading-7 sm:text-sm"
          aria-label="Example Python solution"
        >
          <code>
            <span className="text-brand-violet">def</span> <span className="text-brand-blue">two_sum</span>(nums, target):{"\n"}
            {"    "}seen = {"{}"}
            {"\n"}
            {"    "}
            <span className="text-brand-violet">for</span> i, n <span className="text-brand-violet">in</span>{" "}
            <span className="text-brand-blue">enumerate</span>(nums):{"\n"}
            {"        "}
            <span className="text-brand-violet">if</span> target - n <span className="text-brand-violet">in</span> seen:{"\n"}
            {"            "}
            <span className="text-brand-violet">return</span> [seen[target - n], i]{"\n"}
            {"        "}seen[n] = i{"\n"}
            {"    "}
            <span className="text-brand-violet">return</span> []
          </code>
        </pre>
        <div className="flex items-center justify-between border-t bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
          <span>Python · isolated sandbox</span>
          <span className="font-mono">{BRAND.judge}</span>
        </div>
      </figure>
    </div>
  );
}
