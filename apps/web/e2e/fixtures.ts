import { expect, test as base, type Page } from "@playwright/test";

export const PASSWORD = "correct-horse-battery";

export function uniqueUser() {
  const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  return { username: `e2e_${id}`, email: `e2e_${id}@example.com`, password: PASSWORD };
}

/**
 * Fails a test if the browser reports a CSP violation or a page error. These are exactly the
 * regressions a strict Content-Security-Policy tends to cause silently.
 */
export const test = base.extend<{ problems: string[] }>({
  problems: async ({ page }, provide) => {
    const problems: string[] = [];
    page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      const text = message.text();
      if (message.type() === "error" && /content security policy|refused to|hydrat/i.test(text)) {
        problems.push(`console: ${text}`);
      }
    });
    await provide(problems);
    expect(problems, "browser reported CSP violations or page errors").toEqual([]);
  },
});

export { expect };

export async function register(page: Page, user = uniqueUser()) {
  await page.goto("/register");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Username").fill(user.username);
  await page.getByLabel("Password", { exact: true }).fill(user.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  return user;
}
