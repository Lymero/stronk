// Playwright end to end (`just e2e`, ADR-048): the UI in Chromium against MockBackend scenarios
// (`mock.spec.ts`) and against the real core, lcu-mock and the signed fixture data through
// tools/lcu_mock/core_bridge.py (`core.spec.ts`). Screenshots go to runs/e2e/screenshots/.

import { resolve } from "node:path";
import { defineConfig } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../..");
const core = resolve(process.env.STRONK_CORE_BIN ?? `${ROOT}/app/core/target/debug/stronk-core`);

export default defineConfig({
  testDir: "e2e",
  testIgnore: ["real.spec.ts", "site.spec.ts"], // `just e2e-real` and `just site-shot`: playwright.real.config.ts
  outputDir: `${ROOT}/runs/e2e/results`,
  fullyParallel: false,
  workers: 1, // one lcu-mock behind the bridge
  forbidOnly: !!process.env.CI,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 760, height: 900 },
    // A Chromium already on the machine (STRONK_CHROMIUM), else Playwright's own
    // (`pnpm --filter @stronk/ui exec playwright install chromium`).
    launchOptions: process.env.STRONK_CHROMIUM ? { executablePath: process.env.STRONK_CHROMIUM } : {},
  },
  webServer: [
    {
      command: "pnpm exec vite",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `uv run python tools/lcu_mock/core_bridge.py tools/lcu_mock/sessions/ranked-jungle-leesin.json --core ${core} --dir runs/e2e/bridge`,
      cwd: ROOT,
      url: "http://127.0.0.1:8790/mock/state",
      reuseExistingServer: false,
    },
  ],
});
