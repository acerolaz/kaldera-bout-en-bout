import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  use: { baseURL: "http://localhost:5173", trace: "retain-on-failure" },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 900 } } },
  ],
  workers: 1, // une seule base de test, préparée par le serveur
  webServer: [
    {
      command: "uv run python -m tests.e2e.serveur",
      cwd: "..",
      url: "http://127.0.0.1:8000/docs",
      reuseExistingServer: false,
      timeout: 60_000,
      env: { TEST_DATABASE_URL: process.env.TEST_DATABASE_URL ?? "postgresql://kaldera:kaldera@localhost:5433/kaldera_test" },
    },
    { command: "npm run dev", url: "http://localhost:5173", reuseExistingServer: false, timeout: 60_000 },
  ],
});
