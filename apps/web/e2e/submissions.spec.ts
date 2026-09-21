import type { APIRequestContext, Page } from "@playwright/test";

import { expect, register, test } from "./fixtures";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-dev-password-1";

/**
 * No judge worker runs alongside this e2e stack (see playwright.config.ts: it drives a stack, it doesn't start one),
 * so every submission and run made here stays QUEUED forever — exactly the state docs/troubleshooting.md describes
 * for "no worker is running". That is enough to exercise the browser side end to end: enqueue, the console switching
 * to the right tab, the history list, the detail page, ownership, and — the point that matters most — that nothing a
 * hidden test knows about ever reaches the page.
 */

/** A real hidden-test input for `harbor-cranes`, fetched as an admin — used as a needle nothing public should contain.
 * Long enough (>12 chars, matching the threshold problems.spec.ts's equivalent check uses) that it cannot coincide
 * with an unrelated short substring elsewhere in a response (a status code, a UUID fragment, a count). */
async function hiddenTestNeedle(request: APIRequestContext): Promise<string> {
  const login = await request.post("/api/auth/login", { data: { identifier: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
  const { access_token } = await login.json();
  const headers = { Authorization: `Bearer ${access_token}` };
  const list = await (await request.get("/api/admin/problems?q=harbor&limit=5", { headers })).json();
  const full = await (await request.get(`/api/admin/problems/${list.items[0].id}`, { headers })).json();
  const hidden = full.test_cases
    .filter((c: { kind: string }) => c.kind === "HIDDEN")
    .map((c: { input: string }) => c.input.trim().slice(0, 60))
    .find((s: string) => s.length > 12);
  expect(hidden, "expected at least one hidden test with a long enough input to use as a needle").toBeTruthy();
  return hidden as string;
}

function watchResponses(page: Page): string[] {
  const bodies: string[] = [];
  page.on("response", async (response) => {
    if (response.url().includes("/api/")) bodies.push(await response.text().catch(() => ""));
  });
  return bodies;
}

test.describe("SahuJudge — Run", () => {
  test("runs the code in the editor and switches to the Output tab", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect(page.getByRole("tab", { name: "Output" })).toHaveAttribute("data-state", "active");
    // Nothing consumes the queue in this e2e stack (see the module docstring above), so it never leaves QUEUED.
    await expect(page.getByText("Queued…", { exact: true })).toBeVisible();
    // Neither button can be clicked again mid-run.
    await expect(page.getByRole("button", { name: "Run", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Submit", exact: true })).toBeDisabled();
  });
});

test.describe("SahuJudge — Submit", () => {
  test("submits, shows a live status, and never leaks hidden test data", async ({ page, request, problems }) => {
    void problems;
    const needle = await hiddenTestNeedle(request);
    await register(page);
    const bodies = watchResponses(page);

    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Submit", exact: true }).click();

    await expect(page.getByRole("tab", { name: "Test results" })).toHaveAttribute("data-state", "active");
    await expect(page.getByText("Queued", { exact: true })).toBeVisible();

    for (const body of bodies) {
      expect(body).not.toContain(needle);
      expect(body).not.toContain("expected_output");
    }
  });

  test("appears in submission history, and the detail page shows my own source without hidden data", async ({
    page,
    request,
    problems,
  }) => {
    void problems;
    const needle = await hiddenTestNeedle(request);
    await register(page);
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Submit", exact: true }).click();
    await expect(page.getByText("Queued", { exact: true })).toBeVisible();

    await page.goto("/submissions");
    const row = page.getByRole("row", { name: /Harbor Cranes/ });
    await expect(row).toBeVisible();
    await expect(row).not.toContainText("def solve"); // the list never shows source code

    const bodies = watchResponses(page);
    await row.getByRole("link").click();
    await expect(page).toHaveURL(/\/submissions\/[0-9a-f-]+$/);
    await expect(page.getByRole("heading", { name: "Harbor Cranes" })).toBeVisible();
    await expect(page.getByText("def solve")).toBeVisible(); // my own source, shown back to me
    await expect(page.getByText("Queued for judging…")).toBeVisible();

    for (const body of bodies) {
      expect(body).not.toContain(needle);
      expect(body).not.toContain("expected_output");
    }
  });

  test("another user cannot open my submission", async ({ page, browser, problems }) => {
    void problems;
    await register(page);
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Submit", exact: true }).click();
    await expect(page.getByText("Queued", { exact: true })).toBeVisible();

    await page.goto("/submissions");
    await page.getByRole("row", { name: /Harbor Cranes/ }).getByRole("link").click();
    await expect(page).toHaveURL(/\/submissions\/[0-9a-f-]+$/); // wait for the client-side route change to land
    const mineUrl = page.url();

    const other = await browser.newContext({ baseURL: mineUrl.split("/submissions")[0] });
    const otherPage = await other.newPage();
    await register(otherPage);
    await otherPage.goto(mineUrl);
    await expect(otherPage.getByRole("heading", { name: "Submission not found" })).toBeVisible();
    await other.close();
  });
});

test.describe("submissions page access", () => {
  test("requires sign-in", async ({ page }) => {
    await page.goto("/submissions");
    await expect(page).toHaveURL(/\/login\?next=%2Fsubmissions/);
  });
});
