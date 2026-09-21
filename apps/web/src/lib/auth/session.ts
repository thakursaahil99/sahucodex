import { http, isApiError } from "@/lib/api/http";
import type { RegisterResponse, TokenResponse } from "@/lib/api/types";
import { useAuthStore } from "@/lib/auth/store";

const LOCK_NAME = "sahucodex-auth-refresh";
export const AUTH_CHANNEL = "sahucodex-auth";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Refresh tokens rotate, so two simultaneous refreshes with one cookie would look like theft. */
let inflight: Promise<boolean> | null = null;

async function withCrossTabLock<T>(task: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && navigator.locks) {
    return navigator.locks.request(LOCK_NAME, task);
  }
  return task();
}

async function attemptRefresh(): Promise<boolean> {
  const store = useAuthStore.getState;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const session = await http<TokenResponse>("/auth/refresh", { method: "POST" });
      store().setSession(session);
      return true;
    } catch (error) {
      if (!isApiError(error)) throw error;
      // Another tab rotated the cookie a moment ago; wait for its response to land, then retry.
      if (error.code === "REFRESH_TOKEN_RACE" && attempt < 2) {
        await sleep(250 * (attempt + 1));
        continue;
      }
      if (error.status === 401) {
        store().clear();
        return false;
      }
      // Network down, proxy error, or a 5xx: we can't tell whether the session is valid.
      if (store().status === "loading") store().setStatus("unavailable");
      return false;
    }
  }
  store().clear();
  return false;
}

/**
 * Exchanges the httpOnly refresh cookie for a new access token.
 * Single-flight within a tab, and serialised across tabs with the Web Locks API.
 * Resolves to whether a valid session now exists.
 */
export function refreshSession(): Promise<boolean> {
  inflight ??= withCrossTabLock(attemptRefresh).finally(() => {
    inflight = null;
  });
  return inflight;
}

export async function login(identifier: string, password: string): Promise<void> {
  const session = await http<TokenResponse>("/auth/login", { method: "POST", body: { identifier, password } });
  useAuthStore.getState().setSession(session);
}

/** Creates the account, then signs in with the same credentials. */
export async function register(input: { email: string; username: string; password: string }): Promise<void> {
  await http<RegisterResponse>("/auth/register", { method: "POST", body: input });
  await login(input.email, input.password);
}

export async function logout(): Promise<void> {
  try {
    await http<void>("/auth/logout", { method: "POST" });
  } catch {
    // Even if the server can't be reached, drop local state; the cookie expires on its own.
  }
  useAuthStore.getState().clear();
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(AUTH_CHANNEL);
    channel.postMessage("logout");
    channel.close();
  }
}
