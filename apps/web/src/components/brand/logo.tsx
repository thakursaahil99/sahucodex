import Link from "next/link";
import { useId } from "react";

import { BRAND } from "@sahucodex/shared";

import { cn } from "@/lib/utils";

/**
 * The SahuCodeX mark: a rounded tile holding an "S" whose terminals are the chevrons of `</>`.
 * Original artwork, drawn as inline SVG so it inherits crispness at any size.
 */
export function LogoMark({ className }: { className?: string }) {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8", className)} role="img" aria-label={`${BRAND.name} logo`}>
      <defs>
        <linearGradient id={gradientId} x1="3" y1="2" x2="29" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3b7bff" />
          <stop offset="1" stopColor="#8b5cf6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradientId})`} />
      {/* S body */}
      <path
        d="M20.5 10.6c-.9-1.5-2.6-2.2-4.5-2.2-2.5 0-4.3 1.2-4.3 3.1 0 4.1 8.8 2.3 8.8 7 0 2-1.9 3.4-4.5 3.4-2 0-3.8-.8-4.7-2.3"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      {/* </> terminals in cyan */}
      <path d="M8.2 6.8 5.6 9.4l2.6 2.6" fill="none" stroke="#67e8f9" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M23.8 20 26.4 22.6l-2.6 2.6" fill="none" stroke="#67e8f9" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ className, href = "/" }: { className?: string; href?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2.5 rounded-lg", className)} aria-label={`${BRAND.name} home`}>
      <LogoMark />
      <span className="text-lg font-semibold tracking-tight">
        Sahu<span className="text-gradient">CodeX</span>
      </span>
    </Link>
  );
}
