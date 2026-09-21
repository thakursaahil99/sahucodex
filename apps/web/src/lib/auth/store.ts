import { create } from "zustand";

import type { TokenResponse, User } from "@/lib/api/types";

/**
 * loading      – haven't asked the server yet (first paint)
 * authenticated / anonymous – the server has answered
 * unavailable  – the API could not be reached, so we can't tell; show a retry, don't log out
 */
export type AuthStatus = "loading" | "authenticated" | "anonymous" | "unavailable";

interface AuthState {
  status: AuthStatus;
  /** Held in memory only — never localStorage — so XSS cannot read a long-lived credential. */
  accessToken: string | null;
  expiresAt: number | null;
  user: User | null;
  setSession: (response: TokenResponse) => void;
  setUser: (user: User) => void;
  setStatus: (status: AuthStatus) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  status: "loading",
  accessToken: null,
  expiresAt: null,
  user: null,
  setSession: (response) =>
    set({
      status: "authenticated",
      accessToken: response.access_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      user: response.user,
    }),
  setUser: (user) => set({ user }),
  setStatus: (status) => set({ status }),
  clear: () => set({ status: "anonymous", accessToken: null, expiresAt: null, user: null }),
}));
