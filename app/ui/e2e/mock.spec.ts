// The UI against MockBackend scenarios, in a real browser.

import { expect, test } from "@playwright/test";
import { screenshot } from "./screens.ts";

const next = (page: import("@playwright/test").Page) => page.getByRole("button", { name: "Next step" }).click();

test("follows champion select and shows the plan by name", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  await expect(page.getByText("Waiting for champion select")).toBeVisible();
  await next(page);
  await expect(page.getByRole("heading", { name: "Graves" })).toBeVisible();
  await expect(page.getByLabel("Champion select").locator(".facts > span")).toHaveText(["Jungle", "Hovering", "Declaring picks"]);
  await next(page);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByLabel("Rune page").getByRole("button", { name: /^Conqueror/ })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Smite + Flash" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("▲ +2.1% ± 1.3 vs Black Cleaver")).toBeVisible();
  await expect(page.getByLabel("Champion select").locator("img")).toHaveAttribute("src", /^data:image\/svg\+xml,/);
  await screenshot(page, "mock-hovering");
  await next(page);
  await expect(page.getByLabel("Champion select").locator(".facts > span")).toHaveText(["Jungle", "Locked in", "Final changes"]);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await screenshot(page, "mock-imported");
});

test("imports the options the player clicks, runes one by one", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const build = page.getByLabel("Build");
  const tree = page.getByLabel("Rune page");
  await build.getByRole("region", { name: "Item 2" }).getByRole("button", { name: /^Black Cleaver/ }).click();
  await tree.getByRole("button", { name: /^Lethal Tempo/ }).click();
  await tree.getByRole("button", { name: /^Biscuit Delivery/ }).click();
  await expect(build.getByRole("button", { name: /^Black Cleaver/ })).toHaveAttribute("aria-pressed", "true");
  await expect(tree.locator(".cell.on")).toHaveCount(9);
  await screenshot(page, "mock-picked");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await expect(page.getByRole("status")).toHaveText(/Your picks changed since/);
});

test("shows rare options on request, and keeps picks after a restart", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const build = page.getByLabel("Build");
  const item1 = build.getByRole("region", { name: "Item 1" });
  const tree = page.getByLabel("Rune page");
  await tree.getByRole("button", { name: /^Presence of Mind/ }).click();
  await item1.getByRole("button", { name: "+1" }).click();
  await item1.getByRole("button", { name: /^Trinity Force/ }).click();
  await expect(item1.getByRole("button", { name: /^Trinity Force/ })).toHaveAttribute("aria-pressed", "true");
  await screenshot(page, "mock-all-options");

  await page.reload(); // the app starts again
  for (let i = 0; i < 3; i++) await next(page);
  await expect(item1.getByRole("button", { name: /^Trinity Force/ })).toHaveAttribute("aria-pressed", "true");
  await expect(tree.getByRole("button", { name: /^Presence of Mind/ })).toHaveAttribute("aria-pressed", "true");
  await screenshot(page, "mock-picks-restored");
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await page.reload();
  for (let i = 0; i < 3; i++) await next(page);
  await expect(item1.getByRole("button", { name: /^Eclipse/ })).toHaveAttribute("aria-pressed", "true");
});

test("shows the whole build at once, the runes as the client lays them out", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const tree = page.getByLabel("Rune page");
  await expect(tree.locator(".cell.on")).toHaveCount(9); // the page's nine choices
  await expect(tree.getByRole("region", { name: "Precision, primary" }).locator(".row")).toHaveCount(4);
  // Runes and items side by side, all on one screen.
  const runes = await page.getByRole("region", { name: "Runes" }).boundingBox();
  const items = await page.getByRole("region", { name: "Items" }).boundingBox();
  expect(items && runes && items.x > runes.x + runes.width - 1).toBe(true);
  await screenshot(page, "mock-board");
});

test("fits a narrow window, one column", async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const width = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(width).toBeLessThanOrEqual(420); // no sideways scrolling
  await screenshot(page, "mock-narrow");
});

test("warns when every rune page is in use", async ({ page }) => {
  await page.goto("/?scenario=pages-full");
  for (let i = 0; i < 3; i++) await next(page);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("alert")).toHaveText(/Rune page not imported: all your rune pages are in use/);
  await screenshot(page, "mock-pages-full");
});

test("waits for the League client when it isn't running", async ({ page }) => {
  await page.goto("/?scenario=no-client");
  await expect(page.getByRole("status")).toHaveText("League of Legends isn't open");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await screenshot(page, "mock-no-client");
});

test("refuses data that failed verification", async ({ page }) => {
  await page.goto("/?scenario=bad-data");
  await expect(page.getByRole("alert")).toHaveText(/hash mismatch/);
  await expect(page.getByLabel("Build")).toHaveCount(0);
});

test("restores item sets from a backup after confirming", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  await page.getByText("Settings").click();
  await expect(page.getByRole("radio")).toHaveCount(2);
  await page.getByRole("radio").nth(1).check();
  await page.getByRole("button", { name: "Restore this backup" }).click();
  await screenshot(page, "mock-restore-confirm");
  await page.getByRole("group", { name: "Confirm restore" }).getByRole("button", { name: "Restore" }).click();
  await expect(page.getByRole("status")).toHaveText(/Restored 30 item sets/);
  await expect(page.getByRole("radio")).toHaveCount(3);
});
