/**
 * Constants and types shared across SahuCodeX front-end code.
 * Keep this dependency-free so it can be imported anywhere (server, client, tests).
 */

export const BRAND = {
  name: "SahuCodeX",
  tagline: "Code. Compete. Learn.",
  pitch: ["Solve problems.", "Compete in contests.", "Learn with AI."],
  ai: "SahuCodeX AI",
  judge: "SahuJudge",
} as const;

export const ROLES = ["USER", "MODERATOR", "ADMIN"] as const;
export type Role = (typeof ROLES)[number];

/** Numeric rank so "at least MODERATOR" checks read naturally. Mirrors the API's role hierarchy. */
export const ROLE_RANK: Record<Role, number> = { USER: 1, MODERATOR: 2, ADMIN: 3 };

export function hasRole(roles: readonly string[] | undefined, minimum: Role): boolean {
  if (!roles) return false;
  return roles.some((role) => (ROLE_RANK[role as Role] ?? 0) >= ROLE_RANK[minimum]);
}

/** Shape of every error the API returns: {"success": false, "error": {"code", "message"}}. */
export interface ApiErrorBody {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Array<{ field: string; message: string; type: string }>;
  };
}

export interface NavItem {
  label: string;
  href: string;
  /** False until the page ships; the UI renders it disabled instead of linking to a 404. */
  available: boolean;
  /** Which build phase delivers it (see README). */
  phase: number;
  adminOnly?: boolean;
  /** Shown to this role and above (e.g. MODERATOR sees it, so does ADMIN). Ignored if `adminOnly` is set. */
  minimumRole?: Role;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Dashboard", href: "/dashboard", available: true, phase: 1 },
  { label: "Problems", href: "/problems", available: true, phase: 2 },
  { label: "Submissions", href: "/submissions", available: true, phase: 3 },
  { label: "Contests", href: "/contests", available: true, phase: 6 },
  { label: "Leaderboard", href: "/leaderboard", available: false, phase: 6 },
  { label: "Discussions", href: "/discussions", available: true, phase: 7 },
  { label: "AI Assistant", href: "/ai", available: true, phase: 5 },
  { label: "Moderation", href: "/moderation", available: true, phase: 7, minimumRole: "MODERATOR" },
  { label: "Admin", href: "/admin", available: true, phase: 2, adminOnly: true },
] as const;
