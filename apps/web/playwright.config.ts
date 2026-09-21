import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests drive a real browser against a running stack (docker compose up, or the
 * services started by hand). They do not start anything themselves.
 *
 *   E2E_BASE_URL   where the site is served      (default http://localhost:3000)
 *   E2E_ADMIN_*    credentials of the seeded admin (default: the dev values in .env.example)
 *
 * The API rate-limits registration and login per IP. When running many e2e tests, start the API
 * with relaxed limits (RATE_LIMIT_REGISTER=1000/minute RATE_LIMIT_LOGIN=1000/minute ...).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
