import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Only allow same-site relative redirects (`?next=/dashboard`). Anything that could leave the
 * site — absolute URLs, protocol-relative `//evil.com`, backslash tricks — falls back.
 */
export function safeRedirect(target: string | null | undefined, fallback = "/dashboard"): string {
  if (!target || !target.startsWith("/") || target.startsWith("//") || target.includes("\\")) return fallback;
  return target;
}

export function formatDate(iso: string, options: Intl.DateTimeFormatOptions = { dateStyle: "medium" }): string {
  return new Intl.DateTimeFormat(undefined, options).format(new Date(iso));
}
