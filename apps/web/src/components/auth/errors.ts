import { isApiError } from "@/lib/api/http";

/** Turns an API failure into a sentence a person can act on. Never echoes server internals. */
export function describeAuthError(error: unknown): string {
  if (!isApiError(error)) return "Something went wrong. Please try again.";
  switch (error.code) {
    case "INVALID_CREDENTIALS":
      return "That email/username and password don't match. Check them and try again.";
    case "RATE_LIMITED":
      return error.retryAfter
        ? `Too many attempts. Please wait ${formatWait(error.retryAfter)} and try again.`
        : "Too many attempts. Please wait a moment and try again.";
    case "ACCOUNT_DISABLED":
      return "This account has been disabled. Contact support if you think this is a mistake.";
    case "NETWORK_ERROR":
      return error.message;
    case "TOKEN_INVALID":
      return "This link is invalid or has expired. Request a new one and try again.";
    default:
      return error.status >= 500 ? "The server hit a problem. Please try again shortly." : error.message;
  }
}

function formatWait(seconds: number): string {
  if (seconds < 90) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} minute${minutes === 1 ? "" : "s"}`;
}
