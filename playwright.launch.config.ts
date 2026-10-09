import { defineConfig, devices } from "@playwright/test";

/**
 * Media della landing e del video di lancio (`e2e/launch-media/`).
 *
 * Non e' una suite di test: scrive file in `artifacts/launch-media/`. Un solo
 * worker, perche' le clip si registrano in sequenza e il tempo conta.
 * `PLAYWRIGHT_CHROMIUM_EXECUTABLE` serve dove il Chromium installato non e'
 * quello del pacchetto (es. container con browser preinstallati).
 */
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

export default defineConfig({
  testDir: "./e2e/launch-media",
  fullyParallel: false,
  workers: 1,
  timeout: 5 * 60 * 1000,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3030",
    viewport: { width: 1920, height: 1080 },
    launchOptions: { executablePath },
  },
  webServer: {
    command: "npm run dev:frontend",
    url: "http://127.0.0.1:3030",
    reuseExistingServer: true,
    timeout: 120 * 1000,
  },
});
