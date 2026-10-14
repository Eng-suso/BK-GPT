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
    // Piano video: 1440x900 a densita' 2, cosi' gli zoom stretti restano nitidi
    // (fotogrammi 2880x1800, uscita 1920x1080 e 1080x1350).
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    launchOptions: { executablePath },
  },
  /**
   * Lo screencast di Chromium manda i fotogrammi in pixel CSS anche con
   * `deviceScaleFactor`: la densita' vera la da' il flag del browser. Desktop
   * a 2 (fotogrammi 2880x1800); le riprese da telefono (`-4x5`) a 1080/390,
   * cosi' il 4:5 esce a 1080 px di larghezza reale.
   */
  projects: [
    {
      name: "desktop",
      grepInvert: /-4x5$/,
      use: { launchOptions: { executablePath, args: ["--force-device-scale-factor=2"] } },
    },
    {
      name: "telefono",
      grep: /-4x5$/,
      use: { launchOptions: { executablePath, args: [`--force-device-scale-factor=${1080 / 390}`] } },
    },
  ],
  webServer: [
    {
      command: "npm run dev:frontend",
      url: "http://127.0.0.1:3030",
      reuseExistingServer: true,
      timeout: 120 * 1000,
    },
    {
      // La landing statica con il video hero (landing/).
      command: "python3 -m http.server 4310 --bind 127.0.0.1 --directory landing",
      url: "http://127.0.0.1:4310/index.html",
      reuseExistingServer: true,
      timeout: 20 * 1000,
    },
    {
      // Le risposte dell'agente in streaming, come dal backend (streamServer.mjs).
      command: "node e2e/launch-media/streamServer.mjs",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 20 * 1000,
    },
  ],
});
