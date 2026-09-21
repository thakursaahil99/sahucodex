import { expect, register, test } from "./fixtures";

test.describe("public profile", () => {
  test("shows zeros and every achievement locked for a user who hasn't solved anything", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.goto(`/profile/${user.username}`);
    await expect(page.getByRole("heading", { name: user.username })).toBeVisible();
    await expect(page.getByText("Joined")).toBeVisible();

    const solvedCard = page.locator('[data-slot="card"]').filter({ hasText: "Solved problems" });
    await expect(solvedCard).toContainText("0");

    await expect(page.getByText("Longest 0 days")).toBeVisible(); // streak
    await expect(page.getByText(/Achievements \(0\//)).toBeVisible();
    await expect(page.getByText("0 submissions in the last year")).toBeVisible();
  });

  test("shows a clear not-found state for an unknown username", async ({ page, problems }) => {
    void problems;
    await page.goto("/profile/no-such-user-at-all");
    await expect(page.getByRole("heading", { name: "User not found" })).toBeVisible();
  });

  test("is reachable while signed out, and never exposes private data", async ({ page, request, problems }) => {
    void problems;
    const user = await register(page);
    await page.context().clearCookies();

    const bodies: string[] = [];
    page.on("response", async (response) => {
      if (response.url().includes("/api/")) bodies.push(await response.text().catch(() => ""));
    });
    await page.goto(`/profile/${user.username}`);
    await expect(page.getByRole("heading", { name: user.username })).toBeVisible();
    for (const body of bodies) {
      expect(body).not.toContain(user.email);
      expect(body).not.toContain("password");
    }
    void request;
  });

  test("the account menu links to my own profile", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Profile" }).click();
    await expect(page).toHaveURL(`/profile/${user.username}`);
  });

  test("the command palette links to my own profile", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("option", { name: new RegExp(`Open profile.*${user.username}`) }).click();
    await expect(page).toHaveURL(`/profile/${user.username}`);
  });

  test("the dashboard links to my own public profile", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.getByRole("link", { name: "View public profile" }).click();
    await expect(page).toHaveURL(`/profile/${user.username}`);
  });
});

test.describe("settings", () => {
  test("requires sign-in", async ({ page }) => {
    await page.goto("/settings");
    await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
  });

  test("saves profile fields and they appear on the public profile", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.goto("/settings");
    await page.getByLabel("Bio").fill("I like graphs and long walks on the beach.");
    await page.getByLabel("Country code").fill("in");
    await page.getByLabel("Website").fill("https://example.com");
    await page.getByLabel("GitHub URL").fill("https://github.com/octocat");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Settings saved")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await page.reload();
    await expect(page.getByLabel("Bio")).toHaveValue("I like graphs and long walks on the beach.");
    await expect(page.getByLabel("Country code")).toHaveValue("IN");

    await page.goto(`/profile/${user.username}`);
    await expect(page.getByText("I like graphs and long walks on the beach.")).toBeVisible();
    await expect(page.getByText("IN", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Website/ })).toHaveAttribute("href", "https://example.com");
    await expect(page.getByRole("link", { name: /GitHub/ })).toHaveAttribute("href", "https://github.com/octocat");
  });

  test("rejects a dangerous URL client-side and never sends it", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.goto("/settings");
    const requests: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "PATCH" && request.url().includes("/api/users/me")) requests.push(request.url());
    });
    await page.getByLabel("Website").fill("javascript:alert(1)");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Must be an http(s) URL")).toBeVisible();
    expect(requests).toEqual([]);
  });

  test("clearing a field removes it from the public profile", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.goto("/settings");
    await page.getByLabel("Website").fill("https://example.com");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Settings saved")).toBeVisible();

    await page.getByLabel("Website").fill("");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Settings saved")).toBeVisible();

    await page.goto(`/profile/${user.username}`);
    await expect(page.getByRole("link", { name: /Website/ })).toHaveCount(0);
  });
});
