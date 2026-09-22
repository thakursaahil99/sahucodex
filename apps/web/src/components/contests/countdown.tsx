"use client";

import { useEffect, useRef, useState } from "react";

function format(msLeft: number): string {
  const totalSeconds = Math.max(0, Math.floor(msLeft / 1000));
  const days = Math.floor(totalSeconds / 86_400);
  const hours = Math.floor((totalSeconds % 86_400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  if (days > 0) return `${days}d ${pad(hours)}h ${pad(minutes)}m`;
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

/** A live countdown to `target`. No server push involved: the contest's phase is derived purely from timestamps
 * already on the client, ticking every second; `onReach` fires once, the tick after the target passes. */
export function Countdown({ target, onReach }: { target: string; onReach?: () => void }) {
  // null until the first tick, so SSR and the first client render match; the placeholder below then shows for at
  // most ~1s. Only the interval callback calls setState — never the effect body itself.
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const targetMs = new Date(target).getTime();
  // `now` stays >= targetMs on every tick after the target passes, so the effect below re-runs each second forever
  // unless something remembers "already fired" — a ref survives re-renders without itself triggering one. Reset
  // when the target itself changes, so reusing one mounted instance for a new deadline can fire again.
  const reached = useRef(false);
  useEffect(() => {
    reached.current = false;
  }, [targetMs]);
  useEffect(() => {
    if (now !== null && now >= targetMs && !reached.current) {
      reached.current = true;
      onReach?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per target crossing, not per onReach identity
  }, [now, targetMs]);

  if (now === null) return <span aria-hidden>—:—:—</span>;
  return <span suppressHydrationWarning>{format(targetMs - now)}</span>;
}
