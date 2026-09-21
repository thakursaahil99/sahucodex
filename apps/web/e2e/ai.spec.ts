import type { Page } from "@playwright/test";

import { expect, register, test } from "./fixtures";

/**
 * SahuCodeX AI, end to end, against a REAL local model (Ollama) — nothing here is mocked. The stack under test must
 * have OLLAMA_MODEL set and a model pulled; these tests assert on structure and behaviour, never on the model's wording
 * (a real model's text is not deterministic).
 */
const MODEL_WAIT = 150_000; // a cold model load on CPU can take a while
test.describe.configure({ timeout: 240_000 });

const BANNER = "a suggestion, not a verdict";
const aiPanel = (page: Page) => page.getByRole("tabpanel", { name: "SahuCodeX AI" });

test.describe("SahuCodeX AI", () => {
  test("the Assistant page requires signing in", async ({ page, problems }) => {
    void problems;
    await page.goto("/ai");
    await expect(page).toHaveURL(/\/login\?next=%2Fai/);
  });

  test("AI Hint in the workspace is a real model reply, labelled as a suggestion — never as a verdict", async ({
    page,
    problems,
  }) => {
    void problems;
    await register(page);
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "AI Hint", exact: true }).click();
    // While the model works the button spins and the AI tab explains why it is slow.
    await expect(page.getByRole("tab", { name: "SahuCodeX AI" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText(BANNER)).toBeVisible({ timeout: MODEL_WAIT });
    await expect(page.getByText(/AI hint #1/)).toBeVisible();
    await expect(page.getByText(/from qwen/)).toBeVisible(); // it names the model that answered

    expect((await aiPanel(page).locator(".markdown").innerText()).trim().length).toBeGreaterThan(20);

    // The judge's own tabs are untouched: an AI hint is not a submission.
    await page.getByRole("tab", { name: "Test results" }).click();
    await expect(page.getByText("No submissions yet")).toBeVisible();

    // A second hint builds on the first and is numbered accordingly.
    await page.getByRole("button", { name: "AI Hint", exact: true }).click();
    await expect(page.getByText(/AI hint #2/)).toBeVisible({ timeout: MODEL_WAIT });
  });

  test("AI Review and Explain answer, and stay labelled as AI output", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.goto("/problems/harbor-cranes");
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 20_000 });

    await page.getByRole("button", { name: "AI Review", exact: true }).click();
    await expect(page.getByText(/AI review/)).toBeVisible({ timeout: MODEL_WAIT });
    await expect(page.getByText(BANNER)).toBeVisible();
    // The review prompt demands these headings; a real 3B model follows them (asserted loosely: at least one).
    await expect(aiPanel(page).locator(".markdown h2").first()).toBeVisible();

    await page.getByRole("button", { name: "Explain", exact: true }).click();
    await expect(page.getByText(/AI explanation/)).toBeVisible({ timeout: MODEL_WAIT });
  });

  test("the Assistant chat streams a reply, persists it, and can be renamed and deleted", async ({
    page,
    problems,
  }) => {
    void problems;
    await register(page);
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "AI Assistant" }).click();
    await expect(page).toHaveURL(/\/ai$/);
    await expect(page.getByText("Ask SahuCodeX AI anything about coding")).toBeVisible();
    await expect(page.getByText("No conversations yet.")).toBeVisible();

    const box = page.getByRole("textbox", { name: "Message SahuCodeX AI" });
    await box.fill("In one short sentence, what is a queue?");
    await box.press("Enter");

    const log = page.getByRole("log", { name: "Conversation" });
    await expect(log.locator("[data-role=user]")).toContainText("what is a queue");
    // The reply arrives as a stream; the Stop button is only there while it does.
    await expect(log.locator("[data-role=assistant]")).toContainText(/\w{3}/, { timeout: MODEL_WAIT });
    await expect(page.getByRole("button", { name: /Stop/ })).toHaveCount(0, { timeout: MODEL_WAIT });
    const reply = (await log.locator("[data-role=assistant]").innerText()).trim();
    expect(reply.length).toBeGreaterThan(10);

    // It is saved: listed in the sidebar (titled from the first message) and still there after a reload.
    const item = page.getByRole("button", { name: "In one short sentence, what is a queue?", exact: true });
    await expect(item).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "In one short sentence, what is a queue?", exact: true }).click();
    await expect(log.locator("[data-role=assistant]")).toContainText(reply.slice(0, 20));
    await expect(log.locator("[data-role=user]")).toContainText("what is a queue");

    // A follow-up goes to the same conversation and sees the earlier turn.
    await box.fill("Repeat the word I asked about, in one word.");
    await box.press("Enter");
    await expect(log.locator("[data-role=assistant]")).toHaveCount(2, { timeout: MODEL_WAIT });
    await expect(page.getByRole("button", { name: /Stop/ })).toHaveCount(0, { timeout: MODEL_WAIT });
    await expect(page.getByRole("navigation", { name: "Conversations" }).getByRole("listitem")).toHaveCount(1);

    // Rename inline.
    await page.getByRole("button", { name: /^Rename / }).click();
    const title = page.getByRole("textbox", { name: "Conversation title" });
    await title.fill("Queues explained");
    await title.press("Enter");
    await expect(page.getByRole("button", { name: "Queues explained", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Queues explained" })).toBeVisible();

    // Delete asks first, then really removes it.
    await page.getByRole("button", { name: "Delete Queues explained" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete" }).click();
    await expect(page.getByText("No conversations yet.")).toBeVisible();
    await expect(page.getByText("Ask SahuCodeX AI anything about coding")).toBeVisible();
  });

  test("someone else's conversation is not reachable, even by id", async ({ page, browser, problems }) => {
    void problems;
    await register(page);
    await page.goto("/ai");
    const box = page.getByRole("textbox", { name: "Message SahuCodeX AI" });
    await box.fill("Say hi in one word.");
    await box.press("Enter");
    await expect(page.getByRole("button", { name: /Stop/ })).toHaveCount(0, { timeout: MODEL_WAIT });

    // Read the id out of the API as the owner, then try to fetch it as a second user.
    const owned = await page.evaluate(async () => {
      const refreshed = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
      const { access_token } = (await refreshed.json()) as { access_token: string };
      const list = await fetch("/api/ai/conversations", { headers: { Authorization: `Bearer ${access_token}` } });
      return ((await list.json()) as Array<{ id: string }>)[0]!.id;
    });

    const other = await browser.newContext();
    const otherPage = await other.newPage();
    await register(otherPage);
    const status = await otherPage.evaluate(async (id) => {
      const refreshed = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
      const { access_token } = (await refreshed.json()) as { access_token: string };
      const response = await fetch(`/api/ai/conversations/${id}`, { headers: { Authorization: `Bearer ${access_token}` } });
      return response.status;
    }, owned);
    expect(status).toBe(404);
    await other.close();
  });
});
