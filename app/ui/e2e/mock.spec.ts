// The UI against MockBackend scenarios, in a real browser.

import { expect, test } from "@playwright/test";
import { screenshot } from "./screens.ts";

type Page = import("@playwright/test").Page;
const next = (page: Page) => page.getByRole("button", { name: "Next step" }).click();
/** Opens a slot from the build sheet: "Runes", "Spells", "Item 2". */
const open = (page: Page, slot: string) => page.getByRole("tab", { name: new RegExp(`^${slot}:`) }).click();
/** An option's row in the open slot. */
const option = (page: Page, name: string) => page.getByRole("tabpanel").getByRole("radio", { name: new RegExp(`^${name},`) });

test("follows champion select and shows the plan by name", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  await expect(page.getByText("Waiting for champion select")).toBeVisible();
  await next(page);
  await expect(page.getByRole("heading", { name: "Graves" })).toBeVisible();
  await expect(page.getByLabel("Champion select").locator(".facts > span")).toHaveText(["Jungle", "Hovering", "Declaring picks"]);
  await next(page);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByText("▲ +2.1 wins per 100 vs Black Cleaver")).toBeVisible(); // opens on Stronk's change
  await open(page, "Runes");
  await expect(page.getByLabel("Rune page").getByRole("button", { name: /^Conqueror/ })).toHaveAttribute("aria-pressed", "true");
  await open(page, "Spells");
  await expect(option(page, "Smite \\+ Flash")).toHaveAttribute("aria-checked", "true");
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
  const tree = page.getByLabel("Rune page");
  await open(page, "Item 2");
  await option(page, "Black Cleaver").click();
  await expect(option(page, "Black Cleaver")).toHaveAttribute("aria-checked", "true");
  await open(page, "Runes");
  await tree.getByRole("button", { name: /^Lethal Tempo/ }).click();
  await tree.getByRole("button", { name: /^Biscuit Delivery/ }).click();
  await expect(tree.locator(".cell.on")).toHaveCount(9);
  await expect(page.getByRole("tab", { name: /^Item 2: Black Cleaver, your pick$/ })).toBeVisible();
  await screenshot(page, "mock-picked");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await expect(page.getByRole("status")).toHaveText(/Your picks changed since/);
});

test("shows rare options on request, and keeps picks after a restart", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const tree = page.getByLabel("Rune page");
  await open(page, "Runes");
  await tree.getByRole("button", { name: /^Presence of Mind/ }).click();
  await open(page, "Item 1");
  await page.getByRole("button", { name: "Show 1 more, rarely played" }).click();
  await option(page, "Trinity Force").click();
  await expect(option(page, "Trinity Force")).toHaveAttribute("aria-checked", "true");
  await screenshot(page, "mock-all-options");

  await page.reload(); // the app starts again
  for (let i = 0; i < 3; i++) await next(page);
  await open(page, "Item 1");
  await expect(option(page, "Trinity Force")).toHaveAttribute("aria-checked", "true");
  await open(page, "Runes");
  await expect(tree.getByRole("button", { name: /^Presence of Mind/ })).toHaveAttribute("aria-pressed", "true");
  await screenshot(page, "mock-picks-restored");
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await page.reload();
  for (let i = 0; i < 3; i++) await next(page);
  await open(page, "Item 1");
  await expect(option(page, "Eclipse")).toHaveAttribute("aria-checked", "true");
});

test("shows the build sheet beside the open slot, the runes as the client lays them out", async ({ page }) => {
  await page.setViewportSize({ width: 1200, height: 900 });
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  await screenshot(page, "mock-board");
  await open(page, "Runes");
  const tree = page.getByLabel("Rune page");
  await expect(tree.locator(".cell.on")).toHaveCount(9); // the page's nine choices
  await expect(tree.getByRole("region", { name: "Precision, primary" }).locator(".row")).toHaveCount(4);
  // The sheet and the open slot side by side, all on one screen.
  const sheet = await page.getByRole("tablist").boundingBox();
  const panel = await page.getByRole("tabpanel").boundingBox();
  await screenshot(page, "mock-runes");
  expect(sheet && panel && panel.x > sheet.x + sheet.width - 1 && panel.y + panel.height <= 900).toBe(true);

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
