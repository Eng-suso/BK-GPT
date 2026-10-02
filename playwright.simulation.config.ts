import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

/** Dedicated port guarantees tests exercise this checkout, not another worktree. */
export default defineConfig({
  ...base,
  projects: base.projects?.filter((project) => project.name !== "lighthouse"),
  testMatch: ["**/simulation-workspace.spec.ts", "**/workspace-layout.spec.ts"],
  use: { ...base.use, baseURL: "http://127.0.0.1:3041" },
  webServer: {
    command: "npm --prefix frontend run dev -- --host 127.0.0.1 --port 3041 --strictPort",
    url: "http://127.0.0.1:3041",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
