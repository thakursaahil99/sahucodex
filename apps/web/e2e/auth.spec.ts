import { expect, PASSWORD, register, test, uniqueUser } from "./fixtures";

test.describe("landing page", () => {
  test("shows the brand, tagline and calls to action", async ({ page, problems }) => {
    void problems;
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Code. Compete. Learn.");
    await expect(page.getByText("Solve problems.")).toBeVisible();
    await expect(page.getByText("Compete in contests.")).toBeVisible();
    await expect(page.getByText("Learn with AI.")).toBeVisible();
    await expect(page.getByRole("link", { name: /Start Coding/ })).toHaveAttribute("href", "/register");
    await expect(page.getByRole("link", { name: "Explore Problems" })).toHaveAttribute("href", "/problems");
  });

  test("is dark by default and the theme choice persists", async ({ page, problems }) => {
    void problems;
    await page.goto("/");
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.getByRole("button", { name: "Change theme" }).click();
    await page.getByRole("menuitem", { name: "Light" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);

    await page.reload();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });

  test("Start Coding leads to registration", async ({ page, problems }) => {
    void problems;
    await page.goto("/");
    await page.getByRole("link", { name: /Start Coding/ }).click();
    await expect(page).toHaveURL(/\/register$/);
    await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  });
});

test.describe("route protection", () => {
  test("signed-out visitors are sent to login and returned afterwards", async ({ page, problems }) => {
    void problems;
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
  });

  test("the API rejects unauthenticated calls regardless of the UI", async ({ request }) => {
    const me = await request.get("/api/users/me");
    expect(me.status()).toBe(401);
    expect(await me.json()).toMatchObject({ success: false, error: { code: "NOT_AUTHENTICATED" } });

    const admin = await request.get("/api/admin/users");
    expect(admin.status()).toBe(401);
  });
});

test.describe("register, sign in and out", () => {
  test("a new user can register, land on the dashboard, survive a reload and sign out", async ({ page, problems }) => {
    void problems;
    const user = await register(page);

    await expect(page.getByRole("heading", { level: 1 })).toContainText(`Welcome back, ${user.username}`);
    await expect(page.getByText(user.email)).toBeVisible();
    await expect(page.getByText("Unverified")).toBeVisible();

    // Real session data from the API, with this browser marked as the current device.
    await expect(page.getByText("This device")).toBeVisible();

    // A reload restores the session from the httpOnly refresh cookie (no login form in between).
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`Welcome back, ${user.username}`);

    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);
  });

  test("the refresh token is invisible to page scripts", async ({ page, context, problems }) => {
    void problems;
    await register(page);
    const cookies = await context.cookies();
    const refresh = cookies.find((c) => c.name === "sahucodex_refresh");
    expect(refresh).toMatchObject({ httpOnly: true, path: "/api/auth", sameSite: "Lax" });
    expect(await page.evaluate(() => document.cookie)).not.toContain("sahucodex_refresh");
    // Nor is any token parked in web storage.
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toMatch(/eyJ/);
  });

  test("signing in with a wrong password shows a generic error", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    await page.goto("/login");
    await page.getByLabel("Email or username").fill(user.username);
    await page.getByLabel("Password", { exact: true }).fill("definitely-wrong-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "don't match" })).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("validation errors are announced next to the fields", async ({ page, problems }) => {
    void problems;
    await page.goto("/register");
    await page.getByLabel("Email").fill("nope");
    await page.getByLabel("Username").fill("a");
    await page.getByLabel("Password", { exact: true }).fill("short");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByLabel("Email")).toHaveAttribute("aria-invalid", "true");
    await expect(page.getByText("Use at least 10 characters")).toBeVisible();
  });

  test("an existing email is reported on the email field", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    await page.goto("/register");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Username").fill(`${user.username}_2`);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.getByText("already exists")).toBeVisible();
  });

  test("login ignores an off-site ?next= target", async ({ page, problems }) => {
    void problems;
    const user = await register(page);
    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();

    await page.goto("/login?next=https://evil.example/phish");
    await page.getByLabel("Email or username").fill(user.username);
    await page.getByLabel("Password", { exact: true }).fill(user.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });
});

test.describe("sessions", () => {
  test("two tabs refreshing at once both stay signed in (rotation race)", async ({ page, context, problems }) => {
    void problems;
    const user = await register(page);
    const second = await context.newPage();
    await second.goto("/dashboard");
    await expect(second.getByRole("heading", { level: 1 })).toContainText(user.username);

    await Promise.all([page.reload(), second.reload()]);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(user.username);
    await expect(second.getByRole("heading", { level: 1 })).toContainText(user.username);
  });

  test("signing out in one tab signs out the others", async ({ page, context, problems }) => {
    void problems;
    const user = await register(page);
    const second = await context.newPage();
    await second.goto("/dashboard");
    await expect(second.getByRole("heading", { level: 1 })).toContainText(user.username);

    await page.getByRole("button", { name: `Account menu for ${user.username}` }).click();
    await page.getByRole("menuitem", { name: "Log out" }).click();
    await expect(second).toHaveURL(/\/login/);
  });

  test("a second device can be signed out from the first", async ({ page, browser, problems }) => {
    void problems;
    const user = await register(page);

    const otherContext = await browser.newContext({ baseURL: page.url().split("/dashboard")[0] });
    const other = await otherContext.newPage();
    await other.goto("/login");
    await other.getByLabel("Email or username").fill(user.username);
    await other.getByLabel("Password", { exact: true }).fill(user.password);
    await other.getByRole("button", { name: "Sign in" }).click();
    await expect(other).toHaveURL(/\/dashboard$/);

    await page.reload();
    await expect(page.getByText("This device")).toBeVisible();
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByRole("button", { name: "Sign out device" }).click();
    await expect(page.getByText("Session signed out")).toBeVisible();

    // The revoked device loses access on its very next API call, well before its token expires.
    await other.reload();
    await expect(other).toHaveURL(/\/login/);
    await otherContext.close();
  });
});

test.describe("navigation and command palette", () => {
  test("Ctrl+K opens the palette, filters, and Escape closes it", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await page.getByPlaceholder("Type a command or search…").fill("theme");
    await expect(dialog.getByText("Theme: Light")).toBeVisible();
    await expect(dialog.getByText("Open dashboard")).toBeHidden();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("palette actions work: switching theme and logging out", async ({ page, problems }) => {
    void problems;
    await register(page);
    await page.keyboard.press("Control+k");
    await page.getByRole("option", { name: "Theme: Light" }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);

    await page.keyboard.press("Control+k");
    await page.getByRole("option", { name: "Log out" }).click();
    await expect(page).toHaveURL(/\/login/);
  });

  test("features that are not built yet are shown as disabled, not as broken links", async ({ page, problems }) => {
    void problems;
    await register(page);
    const nav = page.getByRole("navigation", { name: "Primary" });
    await expect(nav.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    await expect(nav.getByText("Leaderboard", { exact: false }).first()).toHaveAttribute("aria-disabled", "true");
    await expect(nav.getByRole("link", { name: "Problems" })).toHaveAttribute("href", "/problems"); // shipped in phase 2
    await expect(nav.getByRole("link", { name: "Submissions" })).toHaveAttribute("href", "/submissions"); // phase 3
    await expect(nav.getByRole("link", { name: "Profile" })).toHaveAttribute("href", /^\/profile\//); // phase 4
    await expect(nav.getByRole("link", { name: "AI Assistant" })).toHaveAttribute("href", "/ai"); // phase 5
    await expect(nav.getByRole("link", { name: "Contests" })).toHaveAttribute("href", "/contests"); // phase 6
    await expect(nav.getByRole("link", { name: "Discussions" })).toHaveAttribute("href", "/discussions"); // phase 7
    // A regular user never sees the Admin entry.
    await expect(nav.getByText("Admin")).toHaveCount(0);
  });

  test("the mobile layout collapses navigation into a menu", async ({ page, problems }) => {
    void problems;
    await page.setViewportSize({ width: 390, height: 800 });
    await register(page);
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
    await page.getByRole("button", { name: "Open menu" }).click();
    await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test.describe("admin", () => {
  test("the seeded admin sees the Admin entry and role badge; the API allows admin calls", async ({
    page,
    request,
    problems,
  }) => {
    void problems;
    const email = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
    const password = process.env.E2E_ADMIN_PASSWORD ?? "Admin-dev-password-1";
    await page.goto("/login");
    await page.getByLabel("Email or username").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    await expect(page.getByRole("navigation", { name: "Primary" }).getByText("Admin")).toBeVisible();
    await expect(page.getByText("ADMIN", { exact: true })).toBeVisible();

    const login = await request.post("/api/auth/login", { data: { identifier: email, password } });
    const { access_token } = await login.json();
    const users = await request.get("/api/admin/users?limit=5", { headers: { Authorization: `Bearer ${access_token}` } });
    expect(users.status()).toBe(200);
    expect((await users.json()).total).toBeGreaterThanOrEqual(3);
  });

  test("a regular user's token is refused by admin APIs", async ({ page, request, problems }) => {
    void problems;
    const user = uniqueUser();
    await register(page, user);
    const login = await request.post("/api/auth/login", { data: { identifier: user.username, password: user.password } });
    const { access_token } = await login.json();
    const response = await request.get("/api/admin/users", { headers: { Authorization: `Bearer ${access_token}` } });
    expect(response.status()).toBe(403);
  });
});
