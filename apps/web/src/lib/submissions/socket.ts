"use client";

import { useEffect, useRef, useState } from "react";

import { getWsTicket } from "@/lib/submissions/api";

export interface JudgeEvent {
  type:
    | "submission.queued"
    | "submission.running"
    | "submission.completed"
    | "submission.failed"
    | "run.running"
    | "run.completed"
    | "run.failed";
  data: Record<string, unknown>;
  ts: string;
}

export type JudgeSocketState = "connecting" | "open" | "unavailable";

const MAX_RECONNECTS = 5;

/**
 * Live submission/run events over the authenticated WebSocket (see docs/judge.md). Every place that uses this also
 * polls the matching REST endpoint whenever something might still be judging, so a socket that never opens — a
 * proxy that doesn't forward the upgrade, a restrictive network — degrades to polling instead of losing updates;
 * `state` is exposed only so callers can show a small "live" indicator, never to gate correctness on.
 */
export function useJudgeSocket(onEvent: (event: JudgeEvent) => void, enabled = true): JudgeSocketState {
  const [state, setState] = useState<JudgeSocketState>("connecting");
  const handler = useRef(onEvent);
  useEffect(() => {
    handler.current = onEvent;
  });

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let cancelled = false;
    let everOpened = false;
    let retries = 0;

    function scheduleReconnect() {
      if (cancelled) return;
      if (everOpened && retries < MAX_RECONNECTS) {
        retries += 1;
        setTimeout(connect, Math.min(1000 * 2 ** retries, 15_000));
      } else {
        setState("unavailable");
      }
    }

    async function connect() {
      let ticket: string;
      try {
        ticket = (await getWsTicket()).ticket;
      } catch {
        if (!cancelled) setState("unavailable");
        return;
      }
      if (cancelled) return;

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${protocol}://${window.location.host}/api/ws?ticket=${encodeURIComponent(ticket)}`);
      socket.onopen = () => {
        everOpened = true;
        retries = 0;
        if (!cancelled) setState("open");
      };
      socket.onmessage = (event) => {
        try {
          handler.current(JSON.parse(event.data as string) as JudgeEvent);
        } catch {
          // a malformed frame is dropped; the REST poll behind every caller of this hook still catches up
        }
      };
      socket.onclose = scheduleReconnect;
      socket.onerror = () => socket?.close();
    }

    connect();
    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [enabled]);

  return enabled ? state : "connecting";
}
