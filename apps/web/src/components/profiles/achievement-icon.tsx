import {
  CalendarCheck,
  Compass,
  Flame,
  Languages,
  Layers,
  Sparkles,
  Target,
  Trophy,
  type LucideIcon,
} from "lucide-react";

/** Maps the icon name the API sends (see app/modules/profiles/achievements.py's CATALOG) to a component. Unknown
 * names fall back to Trophy rather than crashing — new achievements can ship on the API before the web app knows
 * their exact icon. */
const ICONS: Record<string, LucideIcon> = {
  Sparkles,
  Trophy,
  Layers,
  Languages,
  Compass,
  Flame,
  CalendarCheck,
  Target,
};

export function AchievementIcon({ name, className }: { name: string; className?: string }) {
  const Icon = ICONS[name] ?? Trophy;
  return <Icon className={className} aria-hidden />;
}
