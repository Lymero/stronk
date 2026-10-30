// Playwright on the real data (`just e2e-real`, ADR-061): the real core, lcu-mock replaying a
// session generated over the data (tools/lcu_mock/real_session.py), one board per pick, checked
// and saved to runs/e2e-real/screenshots/ to look at. Not in `just check`: CI has no real data.

import { resolve } from "node:path";
import { defineConfig } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../..");
const core = resolve(process.env.STRONK_CORE_BIN ?? `${ROOT}/app/core/target/debug/stronk-core`);
const data = resolve(ROOT, process.env.STRONK_REAL_DATA ?? "runs/real/data");
const key = resolve(ROOT, process.env.STRONK_REAL_KEY ?? "runs/real/data.pub");

export default defineConfig({
  testDir: "e2e",
  testMatch: "real.spec.ts",
  outputDir: `${ROOT}/runs/e2e-real/results`,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1200, height: 900 },
    colorScheme: "dark", // the app's own look, as on a dark Windows desktop
    launchOptions: process.env.STRONK_CHROMIUM ? { executablePath: process.env.STRONK_CHROMIUM } : {},
  },
  webServer: [
    { command: "pnpm exec vite", url: "http://127.0.0.1:5173", reuseExistingServer: true },
    {
      command: `uv run python tools/lcu_mock/core_bridge.py runs/e2e-real/session.json --core ${core} --dir runs/e2e-real/bridge --data ${data} --key ${key}`,
      cwd: ROOT,
      url: "http://127.0.0.1:8790/mock/state",
      reuseExistingServer: false,
    },
  ],
});
