import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright smoke tests for the chat (M3). `npm run e2e` (or `make e2e`) starts:
 * - the API on :8001 with no cloud (app.devtools.serve: embedded Postgres, migrated and seeded,
 *   its own `campus_pulse_e2e` database, templates instead of an LLM so answers are repeatable),
 * - the web app on :3001 pointing at it.
 * UV is the command that runs uv (default "uv"; on a machine with only `python -m uv`,
 * set UV="python -m uv").
 */
const API_PORT = 8001;
const WEB_PORT = 3001;
const uv = process.env.UV ?? "uv";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `${uv} run python -m app.devtools.serve --port ${API_PORT} --db campus_pulse_e2e --cors-origins http://localhost:${WEB_PORT}`,
      cwd: "../api",
      url: `http://localhost:${API_PORT}/readyz`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: {
        LLM_PROVIDERS: "template",
        STT_MODEL: "fake",
        REDIS_URL: "",
        RESPONSE_CACHE_TTL_SECONDS: "0",
      },
    },
    {
      command: `npm run dev -- --port ${WEB_PORT}`,
      url: `http://localhost:${WEB_PORT}`,
      timeout: 180_000,
      reuseExistingServer: !process.env.CI,
      env: {
        NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`,
        NEXT_PUBLIC_WS_URL: `ws://localhost:${API_PORT}`,
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
