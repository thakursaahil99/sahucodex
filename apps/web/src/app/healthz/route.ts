/** Liveness probe for the container healthcheck. Deliberately independent of the API. */
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
