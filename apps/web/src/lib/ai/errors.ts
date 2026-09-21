import { isApiError } from "@/lib/api/http";

/** A 429 says when to come back; anything else the server said is already written for the user. */
export function aiErrorMessage(error: unknown): string {
  if (!isApiError(error)) return "Something went wrong. Please try again.";
  if (error.status === 429 && error.retryAfter) {
    return `You've reached the AI usage limit for now. Try again in about ${Math.max(1, Math.ceil(error.retryAfter / 60))} minute(s).`;
  }
  return error.message;
}
