import type { ApiErrorBody } from "@sahucodex/shared";

/** Same-origin: Next.js proxies /api/* to FastAPI, so cookies and CORS never come into play. */
export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: NonNullable<ApiErrorBody["error"]["details"]>,
    /** Seconds to wait before retrying, from a 429's Retry-After header. */
    public readonly retryAfter?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Maps a VALIDATION_ERROR's details to `{ fieldName: message }` for form display. */
export function fieldErrors(error: ApiError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const detail of error.details ?? []) {
    if (!(detail.field in out)) out[detail.field] = detail.message;
  }
  return out;
}

export interface HttpOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
  signal?: AbortSignal;
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Low-level request. Knows nothing about sessions; see `api()` for the authenticated wrapper. */
export async function http<T>(path: string, { method = "GET", body, token, signal }: HttpOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "NETWORK_ERROR", "Can't reach the SahuCodeX API. Check your connection and try again.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? parseJson(text) : null;

  if (!response.ok) {
    const envelope = (data as Partial<ApiErrorBody> | null)?.error;
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError(
      response.status,
      envelope?.code ?? "HTTP_ERROR",
      envelope?.message ?? `Request failed (${response.status})`,
      envelope?.details,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
    );
  }
  return data as T;
}
