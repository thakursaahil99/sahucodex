import { API_BASE, ApiError } from "@/lib/api/http";
import { refreshSession } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";
import { createSseParser } from "@/lib/ai/sse";
import type { StreamEvent } from "@/lib/ai/types";

async function open(path: string, body: unknown, signal?: AbortSignal): Promise<Response> {
  const token = useAuthStore.getState().accessToken;
  try {
    return await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the SahuCodeX API. Check your connection and try again.");
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let envelope: { code?: string; message?: string } | undefined;
  try {
    envelope = ((await response.json()) as { error?: { code?: string; message?: string } }).error;
  } catch {
    envelope = undefined;
  }
  const retryAfter = Number(response.headers.get("Retry-After"));
  return new ApiError(
    response.status,
    envelope?.code ?? "HTTP_ERROR",
    envelope?.message ?? `Request failed (${response.status})`,
    undefined,
    Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
  );
}

/**
 * POSTs to a streaming AI endpoint and calls `onEvent` for each Server-Sent Event as it arrives. Rejects with an
 * `ApiError` for anything that fails *before* the stream starts (401, 404, 422, 429, 503); a failure *during* the
 * stream arrives as an `error` event instead, because the 200 has already been sent by then.
 */
export async function streamAi(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!useAuthStore.getState().accessToken) await refreshSession();
  let response = await open(path, body, signal);
  if (response.status === 401 && (await refreshSession())) response = await open(path, body, signal);
  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError(0, "NETWORK_ERROR", "The server sent an empty response.");

  const push = createSseParser(onEvent);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    push(decoder.decode(value, { stream: true }));
  }
  push(decoder.decode()); // flush a trailing partial sequence, if any
}
