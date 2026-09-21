import { ApiError, http, isApiError, type HttpOptions } from "@/lib/api/http";
import { refreshSession } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";

/** Codes meaning "this session is over" — as opposed to TOKEN_EXPIRED, which a refresh can fix. */
const SESSION_ENDED = new Set(["TOKEN_INVALID", "TOKEN_REVOKED", "ACCOUNT_UNAVAILABLE"]);

/**
 * Authenticated request. Attaches the in-memory access token, refreshes it transparently when it
 * has expired (once, then retries), and signs the user out locally if the session was revoked.
 */
export async function api<T>(path: string, options: Omit<HttpOptions, "token"> = {}): Promise<T> {
  const state = useAuthStore.getState;

  if (!state().accessToken) {
    await refreshSession();
    if (!state().accessToken) throw new ApiError(401, "NOT_AUTHENTICATED", "Please sign in to continue.");
  }

  try {
    return await http<T>(path, { ...options, token: state().accessToken });
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      if (error.code === "TOKEN_EXPIRED" && (await refreshSession()) && state().accessToken) {
        return http<T>(path, { ...options, token: state().accessToken });
      }
      if (SESSION_ENDED.has(error.code)) state().clear();
    }
    throw error;
  }
}

/**
 * For public endpoints that personalise their answer when the viewer is signed in (problem list, problem page).
 * Sends the access token if there is one, refreshes it when it has expired, but never forces a login: if the
 * session turns out to be over it simply retries anonymously.
 */
export async function apiPublic<T>(path: string, options: Omit<HttpOptions, "token"> = {}): Promise<T> {
  const state = useAuthStore.getState;
  try {
    return await http<T>(path, { ...options, token: state().accessToken });
  } catch (error) {
    if (isApiError(error) && error.status === 401) {
      if (error.code === "TOKEN_EXPIRED" && (await refreshSession()) && state().accessToken) {
        return http<T>(path, { ...options, token: state().accessToken });
      }
      if (SESSION_ENDED.has(error.code) || error.code === "TOKEN_EXPIRED") {
        state().clear();
        return http<T>(path, options);
      }
    }
    throw error;
  }
}
