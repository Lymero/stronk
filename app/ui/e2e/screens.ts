import type { Page } from "@playwright/test";

/** Saves a full-page screenshot to runs/e2e/screenshots/<name>.png, to look at after a run. */
export const screenshot = (page: Page, name: string) =>
  page.screenshot({ path: `../../runs/e2e/screenshots/${name}.png`, fullPage: true });
