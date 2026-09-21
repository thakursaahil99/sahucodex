import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";

import { BRAND } from "@sahucodex/shared";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: `${BRAND.name} — ${BRAND.tagline}`, template: `%s · ${BRAND.name}` },
  description:
    "SahuCodeX is an AI-powered coding and competitive programming platform: solve problems, compete in contests, and learn with a local, open-source AI assistant.",
  applicationName: BRAND.name,
};

export const viewport: Viewport = {
  colorScheme: "dark light",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#090b13" },
    { media: "(prefers-color-scheme: light)", color: "#f6f7fb" },
  ],
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // The per-request CSP nonce is minted in src/proxy.ts.
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-dvh">
        <a
          href="#main"
          className="sr-only rounded-lg bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100]"
        >
          Skip to content
        </a>
        <Providers nonce={nonce}>{children}</Providers>
      </body>
    </html>
  );
}
