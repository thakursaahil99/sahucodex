import type { APIRequestContext, Page } from "@playwright/test";

import { expect, PASSWORD, register, test, uniqueUser } from "./fixtures";

const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "Admin-dev-password-1";

async function signIn(page: Page, identifier: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill(identifier);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

/** How many problems learners can currently see. Tests derive expectations from this, never from a constant. */
async function publishedTotal(request: APIRequestContext): Promise<number> {
  const body = await (await request.get("/api/problems?limit=1")).json();
  return body.total as number;
}

/** The text Monaco currently holds (the AMD build exposes `window.monaco`). */
type MonacoGlobal = { monaco: { editor: { getModels(): Array<{ getValue(): string }> } } };
const editorText = (page: Page) => page.evaluate(() => (window as unknown as MonacoGlobal).monaco.editor.getModels()[0]!.getValue());

async function typeIntoEditor(page: Page, text: string) {
  await page.locator(".monaco-editor .view-lines").first().click();
  await page.keyboard.press("Control+End");
  await page.keyboard.type(text);
}

test.describe("browsing problems", () => {
  test("lists the seeded problems, filters by difficulty and topic, and keeps filters in the URL", async ({ page, request, problems }) => {
    void problems;
    const total = await publishedTotal(request);
    expect(total).toBeGreaterThanOrEqual(30);
    await page.goto("/problems");
    await expect(page.getByText(`${total} problems`, { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Problems" }).getByRole("listitem")).toHaveCount(20);

    await page.getByRole("button", { name: "Hard", exact: true }).click();
    await expect(page).toHaveURL(/difficulty=HARD/);
    await expect(page.getByText("8 problems match your filters")).toBeVisible();

    await page.getByRole("button", { name: "Show all 23 topics" }).click();
    await page.getByRole("button", { name: /^Trie/ }).click();
    await expect(page.getByText("1 problem match your filters")).toBeVisible();
    await expect(page.getByRole("link", { name: /Prefix Directory/ })).toBeVisible();

    // The filtered view survives a reload (it lives in the URL).
    await page.reload();
    await expect(page.getByRole("button", { name: "Hard", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("link", { name: /Prefix Directory/ })).toBeVisible();

    await page.getByRole("button", { name: "Clear all filters" }).click();
    await expect(page).toHaveURL(/\/problems$/);
    await expect(page.getByText(`${total} problems`, { exact: true })).toBeVisible();
  });

  test("search finds problems by title, clears cleanly, and paginates", async ({ page, request, problems }) => {
    void problems;
    const total = await publishedTotal(request);
    await page.goto("/problems");
    await page.getByRole("searchbox", { name: "Search problems" }).fill("coin");
    await expect(page).toHaveURL(/q=coin/);
    await expect(page.getByRole("link", { name: /Fewest Coins/ })).toBeVisible();

    await page.getByRole("button", { name: "Clear all filters" }).click();
    await expect(page.getByRole("searchbox", { name: "Search problems" })).toHaveValue("");
    await page.getByRole("button", { name: /Next/ }).click();
    await expect(page.getByText(`Page 2 of ${Math.ceil(total / 20)}`)).toBeVisible();
    await expect(page.getByRole("list", { name: "Problems" }).getByRole("listitem")).toHaveCount(Math.min(20, total - 20));
  });

  test("a search with no matches explains itself", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems?q=zzzzqqqq");
    await expect(page.getByText("No problems match those filters")).toBeVisible();
  });

  test("hostile URL parameters are ignored instead of breaking the page", async ({ page, request, problems }) => {
    void problems;
    const total = await publishedTotal(request);
    await page.goto("/problems?difficulty=<script>&sort=drop&page=-5&tag=Not%20A%20Slug&acceptance=x");
    await expect(page.getByText(`${total} problems`, { exact: true })).toBeVisible();
  });

  test("signed-in users can filter by their own progress", async ({ page, request, problems }) => {
    void problems;
    const total = await publishedTotal(request);
    await register(page);
    await page.goto("/problems");
    await page.getByRole("button", { name: "Unsolved" }).click();
    await expect(page).toHaveURL(/status=unsolved/);
    await expect(page.getByText(`${total} problems match your filters`)).toBeVisible();
    await page.getByRole("button", { name: "Solved", exact: true }).click();
    await expect(page.getByText("No problems match those filters")).toBeVisible();
  });
});

test.describe("problem workspace", () => {
  test("shows the statement, examples, locked editorial and step-by-step hints", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    await expect(page.getByRole("heading", { level: 1, name: "Harbor Cranes" })).toBeVisible();
    await expect(page.getByText("Port Sahu")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Constraints" })).toBeVisible();
    await expect(page.getByText("Example 1", { exact: true })).toBeVisible();
    await expect(page.getByText("5 9", { exact: false }).first()).toBeVisible();

    await page.getByRole("tab", { name: /Hints/ }).click();
    await expect(page.getByText("0 of 3 hints revealed")).toBeVisible();
    await page.getByRole("button", { name: "Reveal hint 1" }).click();
    await expect(page.getByText("Checking every pair works")).toBeVisible();
    await expect(page.getByText("1 of 3 hints revealed")).toBeVisible();

    await page.getByRole("tab", { name: /Editorial/ }).click();
    await expect(page.getByText("The editorial unlocks when you solve this problem")).toBeVisible();
  });

  test("the Monaco editor loads, offers all languages, and switches starter code", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    expect(await editorText(page)).toContain("def solve");

    await expect(page.getByLabel("Language")).toContainText("Python 3");
    await page.getByLabel("Language").selectOption("cpp");
    await expect(page.locator(".monaco-editor").first()).toBeVisible();
    await expect.poll(() => editorText(page)).toContain("#include <bits/stdc++.h>");

    await page.getByLabel("Language").selectOption("javascript");
    await expect.poll(() => editorText(page)).toContain("readFileSync");
  });

  test("Monaco is served from our own origin (no CDN) under the strict CSP", async ({ page, problems }) => {
    void problems;
    const external: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin !== new URL(page.url() || "http://localhost").origin && !url.protocol.startsWith("data") && !url.protocol.startsWith("blob")) {
        external.push(request.url());
      }
    });
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    expect(external.filter((u) => /jsdelivr|unpkg|cdnjs/.test(u))).toEqual([]);
  });

  test("code drafts are saved automatically, restored after a reload, and can be reset", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await typeIntoEditor(page, "\n# my draft marker");
    await expect(page.getByText("Draft saved")).toBeVisible({ timeout: 5_000 });

    await page.reload();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await expect.poll(() => editorText(page)).toContain("# my draft marker");

    // Drafts are per language.
    await page.getByLabel("Language").selectOption("cpp");
    await expect.poll(() => editorText(page)).not.toContain("# my draft marker");
    await page.getByLabel("Language").selectOption("python");
    await expect.poll(() => editorText(page)).toContain("# my draft marker");

    await page.getByRole("button", { name: "Reset" }).click();
    await page.getByRole("button", { name: "Reset code" }).click();
    await expect.poll(() => editorText(page)).not.toContain("# my draft marker");
    await page.reload();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await expect.poll(() => editorText(page)).not.toContain("# my draft marker");
  });

  test("editor preferences (font size, minimap, wrap) persist", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Increase font size" }).click();
    await page.getByRole("button", { name: "Increase font size" }).click();
    await page.getByRole("button", { name: "Wrap" }).click();
    await page.reload();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("group", { name: "Font size" })).toContainText("16");
    await expect(page.getByRole("button", { name: "Wrap" })).toHaveAttribute("aria-pressed", "true");
  });

  test("Format tidies whitespace and says honestly what it did for Python", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await typeIntoEditor(page, "\nx = 1     ");
    await page.getByRole("button", { name: "Format" }).click();
    await expect(page.getByText("Whitespace tidied")).toBeVisible();
    expect(await editorText(page)).not.toMatch(/x = 1 +\n/);
  });

  test("Run and Submit are enabled for everyone; the AI needs a signed-in user and says so", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");

    // Run and Submit are enabled for everyone; see submissions.spec.ts for the signed-in, judged flow.
    await expect(page.getByRole("button", { name: "Run", exact: true })).not.toHaveAttribute("aria-disabled", "true");
    await expect(page.getByRole("button", { name: "Submit", exact: true })).not.toHaveAttribute("aria-disabled", "true");

    // The AI is a real, signed-in feature (see ai.spec.ts): anonymously, asking gets an honest message, not a fake reply.
    await page.getByRole("button", { name: "AI Hint", exact: true }).click();
    await expect(page.getByRole("tabpanel", { name: "SahuCodeX AI" }).getByRole("alert")).toContainText("sign in");
    await expect(page.getByText("a suggestion, not a verdict")).toHaveCount(0);

    await page.getByRole("tab", { name: "Output" }).click();
    await expect(page.getByText("Nothing has run yet")).toBeVisible();
    await page.getByRole("tab", { name: "Test results" }).click();
    await expect(page.getByText("No submissions yet")).toBeVisible();
  });

  test("custom input can be edited and examples loaded into it", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/harbor-cranes");
    const input = page.getByLabel("Custom input");
    await expect(input).toHaveValue("5 9\n2 7 11 15 1\n");
    await input.fill("1 2\n3\n");
    await page.getByRole("button", { name: "2", exact: true }).click();
    await expect(input).toHaveValue("3 100\n1 2 3\n");
  });

  test("an unknown problem shows a clear not-found state", async ({ page, problems }) => {
    void problems;
    await page.goto("/problems/no-such-problem");
    await expect(page.getByRole("heading", { name: "Problem not found" })).toBeVisible();
  });

  test("the mobile layout stacks the panes into tabs with no horizontal scroll", async ({ page, problems }) => {
    void problems;
    await page.setViewportSize({ width: 390, height: 800 });
    await page.goto("/problems/harbor-cranes");
    await expect(page.getByRole("tab", { name: "Problem" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { level: 1, name: "Harbor Cranes" })).toBeVisible();

    await page.getByRole("tab", { name: "Code" }).click();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Submit", exact: true })).toBeVisible();

    await page.getByRole("tab", { name: "Console" }).click();
    await expect(page.getByLabel("Custom input")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test.describe("hidden tests stay hidden", () => {
  test("no public page or API response ever contains hidden test data", async ({ page, request, problems }) => {
    void problems;
    // Fetch a real hidden test input as an administrator...
    const login = await request.post("/api/auth/login", { data: { identifier: ADMIN_EMAIL, password: ADMIN_PASSWORD } });
    const { access_token } = await login.json();
    const headers = { Authorization: `Bearer ${access_token}` };
    const list = await (await request.get("/api/admin/problems?q=harbor&limit=5", { headers })).json();
    const full = await (await request.get(`/api/admin/problems/${list.items[0].id}`, { headers })).json();
    const hidden = full.test_cases.filter((c: { kind: string }) => c.kind === "HIDDEN");
    expect(hidden.length).toBeGreaterThanOrEqual(6);
    const needles: string[] = hidden.map((c: { input: string }) => c.input.trim().slice(0, 60)).filter((s: string) => s.length > 12);
    expect(needles.length).toBeGreaterThan(2);

    // ...then browse the site anonymously and inspect every byte the browser receives.
    const bodies: string[] = [];
    page.on("response", async (response) => {
      if (response.url().includes("/api/")) bodies.push(await response.text().catch(() => ""));
    });
    await page.goto("/problems");
    await page.goto("/problems/harbor-cranes");
    await page.getByRole("tab", { name: /Hints/ }).click();
    await page.getByRole("button", { name: "Reveal hint 1" }).click();
    await page.waitForTimeout(500);

    expect(bodies.length).toBeGreaterThan(2);
    for (const body of bodies) {
      for (const needle of needles) expect(body).not.toContain(needle);
      expect(body).not.toContain("expected_output");
    }
  });
});

test.describe("admin", () => {
  test("regular users are told they lack access, and the API agrees", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Administrators only" })).toBeVisible();
    await page.goto("/admin/problems/new");
    await expect(page.getByRole("heading", { name: "Administrators only" })).toBeVisible();
    const me = await page.evaluate(async () => {
      const refreshed = await fetch("/api/auth/refresh", { method: "POST" }).then((r) => r.json());
      const response = await fetch("/api/admin/problems", { headers: { Authorization: `Bearer ${refreshed.access_token}` } });
      return response.status;
    });
    expect(me).toBe(403);
  });

  test("the overview shows real counts", async ({ page, problems }) => {
    void problems;
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin");
    await expect(page.getByRole("heading", { name: "Admin" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Published/ })).toContainText(/\d+/);
    await page.getByRole("navigation", { name: "Admin sections" }).getByRole("link", { name: "Problems" }).click();
    await expect(page.getByRole("table")).toBeVisible();
    // The seeded problems share one timestamp, so which page a given one lands on is arbitrary: search, don't scroll.
    await page.getByPlaceholder("Search by title or slug…").fill("harbor-cranes");
    await page.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page.getByRole("row", { name: /Harbor Cranes/ })).toBeVisible();
  });

  test("create → validate → publish → edit → archive, seen by learners at every step", async ({ page, browser, problems }) => {
    void problems;
    const suffix = Date.now().toString(36);
    const title = `E2E Zebra Crossing ${suffix}`;
    const slug = `e2e-zebra-crossing-${suffix}`;

    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/problems/new");

    // Basics: the slug follows the title until edited by hand.
    await page.getByLabel("Title", { exact: true }).fill(title);
    await expect(page.getByLabel("Slug")).toHaveValue(slug);
    await page.getByRole("button", { name: "Array", exact: true }).click();

    // Statement.
    await page.getByRole("tab", { name: /Statement/ }).click();
    await page.getByLabel("Description (Markdown)").fill("Count the **zebras** crossing the road in one minute. This statement is long enough to publish.");
    await page.getByLabel("Input format").fill("A single integer n.");
    await page.getByLabel("Output format").fill("The number n doubled.");
    await page.getByLabel("Constraints (Markdown)").fill("- 1 ≤ n ≤ 1000");

    // Tests: one example + three hidden.
    await page.getByRole("tab", { name: /Test cases/ }).click();
    await page.getByLabel("Input (stdin)").first().fill("2\n");
    await page.getByLabel("Expected output (stdout)").first().fill("4\n");
    await page.getByLabel("Explanation shown under the example (optional)").fill("Two zebras become four legs of six.");
    for (let i = 0; i < 3; i++) {
      await page.getByRole("button", { name: "Hidden test" }).click();
      await page.getByLabel("Input (stdin)").nth(i + 1).fill(`${10 + i}\n`);
      await page.getByLabel("Expected output (stdout)").nth(i + 1).fill(`${(10 + i) * 2}\n`);
    }

    // Starter code.
    await page.getByRole("tab", { name: /Starter code/ }).click();
    await page.getByRole("button", { name: "Use the generic template" }).click();

    // Save as a draft — and learners cannot see it yet.
    await page.getByRole("button", { name: "Create draft" }).click();
    await expect(page).toHaveURL(/\/admin\/problems\/[0-9a-f-]+\/edit$/);
    await expect(page.getByText("All changes saved")).toBeVisible();
    const anon = await browser.newContext({ baseURL: page.url().split("/admin")[0] });
    const visitor = await anon.newPage();
    await visitor.goto(`/problems/${slug}`);
    await expect(visitor.getByRole("heading", { name: "Problem not found" })).toBeVisible();

    // Publish.
    await page.getByRole("tab", { name: "Publish" }).click();
    await page.getByRole("button", { name: "Check readiness" }).click();
    await expect(page.getByText("Everything required to publish is in place.")).toBeVisible();
    await page.getByRole("button", { name: "Publish", exact: true }).click();
    await expect(page.getByText("Published — learners can see it now")).toBeVisible();

    await visitor.goto(`/problems/${slug}`);
    await expect(visitor.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(visitor.getByText("Two zebras become four legs of six.")).toBeVisible();
    await visitor.goto(`/problems?q=zebra`);
    await expect(visitor.getByRole("link", { name: new RegExp(title) })).toBeVisible();

    // Edit the live problem: the change is visible at once (cache invalidation).
    await page.getByRole("tab", { name: "Basics" }).click();
    await page.getByLabel("Title", { exact: true }).fill(`${title} Reloaded`);
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Changes saved", { exact: true })).toBeVisible();
    await visitor.goto(`/problems/${slug}`);
    await expect(visitor.getByRole("heading", { level: 1, name: `${title} Reloaded` })).toBeVisible();

    // Archive: gone for learners immediately.
    await page.getByRole("tab", { name: "Publish" }).click();
    await page.getByRole("button", { name: "Archive", exact: true }).click();
    await page.getByRole("button", { name: "Archive", exact: true }).last().click();
    await expect(page.getByText("Archived", { exact: true }).first()).toBeVisible();
    await visitor.goto(`/problems/${slug}`);
    await expect(visitor.getByRole("heading", { name: "Problem not found" })).toBeVisible();
    await anon.close();
  });

  test("an incomplete problem cannot be published and the blockers are listed", async ({ page, problems }) => {
    void problems;
    const suffix = Date.now().toString(36);
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/problems/new");
    await page.getByLabel("Title", { exact: true }).fill(`Half Done ${suffix}`);
    await page.getByRole("button", { name: "Create draft" }).click();
    await expect(page).toHaveURL(/\/edit$/);
    await page.getByRole("tab", { name: "Publish" }).click();
    await page.getByRole("button", { name: "Check readiness" }).click();
    const blockers = page.getByRole("list", { name: "Publishing blockers" });
    await expect(blockers).toBeVisible();
    await expect(blockers.getByRole("listitem")).not.toHaveCount(0);
    await expect(blockers).toContainText(/hidden|tag|starter|description|format/i);
  });

  test("client-side validation stops a bad slug before it reaches the API", async ({ page, problems }) => {
    void problems;
    await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await page.goto("/admin/problems/new");
    await page.getByLabel("Title", { exact: true }).fill("Valid Title");
    await page.getByLabel("Slug").fill("Not A Valid Slug!");
    await page.getByRole("button", { name: "Create draft" }).click();
    await expect(page.getByText(/Slug: lowercase letters/)).toBeVisible();
  });
});

// Keep the shared constant referenced: user passwords in these tests come from the fixtures.
void PASSWORD;
void uniqueUser;
