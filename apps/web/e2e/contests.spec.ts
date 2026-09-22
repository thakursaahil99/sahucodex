import type { APIRequestContext, Page } from "@playwright/test";

import { expect, register, test } from "./fixtures";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-dev-password-1";

async function signIn(page: Page, identifier: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill(identifier);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

async function adminHeaders(request: APIRequestContext): Promise<Record<string, string>> {
  const login = await request.post("/api/auth/login", { data: { identifier: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  const { access_token } = await login.json();
  return { Authorization: `Bearer ${access_token}` };
}

/** Creates and publishes a contest with one problem (the seeded "harbor-cranes"), via the admin API directly — the
 * UI for this is covered separately by the admin-authoring test below. */
async function seedContest(
  request: APIRequestContext,
  slug: string,
  { startTime, endTime }: { startTime: Date; endTime: Date },
): Promise<string> {
  const headers = await adminHeaders(request);
  const created = await request.post("/api/admin/contests", {
    headers,
    data: {
      slug,
      title: `E2E ${slug}`,
      description: "An end-to-end test contest.",
      start_time: startTime.toISOString(),
      end_time: endTime.toISOString(),
      penalty_minutes: 20,
      problems: [{ problem_slug: "harbor-cranes", label: "A", points: 100 }],
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const { id } = await created.json();
  const published = await request.post(`/api/admin/contests/${id}/publish`, { headers });
  expect(published.ok()).toBeTruthy();
  return id;
}

test.describe("contests", () => {
  test("an upcoming contest hides its problems from everyone, spectators included", async ({ page, request, problems }) => {
    void problems;
    const slug = `upcoming-${Date.now()}`;
    await seedContest(request, slug, {
      startTime: new Date(Date.now() + 3_600_000),
      endTime: new Date(Date.now() + 7_200_000),
    });
    await page.goto("/contests");
    await expect(page.getByText(/Upcoming/).first()).toBeVisible();

    // Navigate straight by slug: the list can carry other contests left over from earlier runs of this same spec.
    await page.goto(`/contests/${slug}`);
    await expect(page.getByRole("heading", { name: `E2E ${slug}` })).toBeVisible();
    await expect(page.getByText("Upcoming", { exact: true })).toBeVisible();
    await expect(page.getByText(/hidden until the contest starts/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Harbor Cranes" })).toHaveCount(0);
  });

  test("a running contest: register, submit, and see standings update", async ({ page, request, problems }) => {
    void problems;
    const slug = `running-${Date.now()}`;
    await seedContest(request, slug, {
      startTime: new Date(Date.now() - 60_000),
      endTime: new Date(Date.now() + 3_600_000),
    });

    const user = await register(page);
    await page.goto(`/contests/${slug}`);
    await expect(page.getByText("Running", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Harbor Cranes" })).toBeVisible();

    // Not registered yet: the workspace is read-only (spectator), and a submit attempt is refused with a clear reason.
    await page.getByRole("link", { name: "Harbor Cranes" }).click();
    await expect(page).toHaveURL(new RegExp(`/contests/${slug}/A$`));
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/viewing this problem as a spectator/)).toBeVisible();
    await expect(page.getByRole("tab", { name: "SahuCodeX AI" })).toHaveCount(0);

    // Register from the workspace's own banner.
    await page.getByRole("button", { name: "Register" }).click();
    await expect(page.getByText(/viewing this problem as a spectator/)).toHaveCount(0);

    // No judge worker runs in this environment (same constraint as submissions.spec.ts), so this only reaches
    // "Queued" — the point here is that the contest-scoped submit endpoint accepted it for real, tagged with this
    // contest, exactly like the plain submit path.
    await page.getByRole("button", { name: /^Submit/ }).click();
    await expect(page.getByRole("tab", { name: "Test results" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Queued", { exact: true })).toBeVisible({ timeout: 15_000 });

    // Standings are computed live from real submissions, not client-supplied: a registered participant appears
    // (0 points — nothing has been judged yet), never a fabricated score.
    await page.goto(`/contests/${slug}`);
    await page.getByRole("tab", { name: "Standings" }).click();
    const row = page.getByRole("row", { name: new RegExp(user.username) });
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row.getByRole("cell").nth(2)).toHaveText("0"); // total points
  });

  test("submitting without registering is refused with a clear reason, not a raw error", async ({ page, request, problems }) => {
    void problems;
    const slug = `spectator-${Date.now()}`;
    await seedContest(request, slug, { startTime: new Date(Date.now() - 60_000), endTime: new Date(Date.now() + 3_600_000) });
    await register(page);
    await page.goto(`/contests/${slug}/A`);
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: /^Submit/ }).click();
    await expect(page.getByText(/Register for this contest first/)).toBeVisible();
  });

  test("admin creates, edits and publishes a contest through the UI", async ({ page, problems }) => {
    void problems;
    const slug = `admin-ui-${Date.now()}`;
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/contests");
    await page.getByRole("link", { name: "New contest" }).click();

    await page.getByLabel("Slug").fill(slug);
    await page.getByLabel("Title").fill("Admin UI Cup");
    await page.getByRole("button", { name: "Add problem" }).click();
    await page.getByLabel("Problem slug").fill("harbor-cranes");
    await page.getByRole("button", { name: "Create draft" }).click();

    await expect(page.getByRole("heading", { name: /Edit: Admin UI Cup/ })).toBeVisible();
    await expect(page).toHaveURL(/\/admin\/contests\/.+\/edit/);

    await page.getByRole("button", { name: "Publish" }).click();
    await expect(page.getByRole("button", { name: "Unpublish" })).toBeVisible();

    await page.goto(`/contests/${slug}`);
    await expect(page.getByRole("heading", { name: "Admin UI Cup" })).toBeVisible();
  });

  test("a contest's schedule cannot be edited once it has started", async ({ request }) => {
    const headers = await adminHeaders(request);
    const id = await seedContest(request, `locked-${Date.now()}`, {
      startTime: new Date(Date.now() - 60_000),
      endTime: new Date(Date.now() + 3_600_000),
    });
    const response = await request.put(`/api/admin/contests/${id}`, {
      headers,
      data: {
        slug: `locked-${Date.now()}`,
        title: "Should not save",
        description: "",
        start_time: new Date(Date.now() + 3_600_000).toISOString(),
        end_time: new Date(Date.now() + 7_200_000).toISOString(),
        penalty_minutes: 20,
        problems: [],
      },
    });
    expect(response.status()).toBe(409);
    expect((await response.json()).error.code).toBe("CONTEST_ALREADY_STARTED");
  });
});
