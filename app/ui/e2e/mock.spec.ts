// The UI against MockBackend scenarios, in a real browser.

import { expect, test } from "@playwright/test";
import { screenshot } from "./screens.ts";

const next = (page: import("@playwright/test").Page) => page.getByRole("button", { name: "Next step" }).click();
/** Opens a slot of the build (`Runes`, `Item 2`) to show its options. */
const openSlot = (page: import("@playwright/test").Page, slot: string) =>
  page.getByLabel("Build").getByRole("button", { name: new RegExp(`^${slot} `) }).click();

test("follows champion select and shows the plan by name", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  await expect(page.getByText("Waiting for champion select")).toBeVisible();
  await next(page);
  await expect(page.getByRole("heading", { name: "Graves" })).toBeVisible();
  await expect(page.getByLabel("Champion select").locator(".facts > span")).toHaveText(["Jungle", "Hovering", "Declaring picks"]);
  await next(page);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByText("Conqueror (Precision + Inspiration)")).toBeVisible();
  await expect(page.getByText("Smite + Flash")).toBeVisible();
  await expect(page.getByText("▲ +2.1% ± 1.3 vs Black Cleaver")).toBeVisible();
  await expect(page.getByLabel("Champion select").locator("img")).toHaveAttribute("src", /^data:image\/svg\+xml,/);
  await screenshot(page, "mock-hovering");
  await next(page);
  await expect(page.getByLabel("Champion select").locator(".facts > span")).toHaveText(["Jungle", "Locked in", "Final changes"]);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await screenshot(page, "mock-imported");
});

test("imports the options the player clicks", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const build = page.getByLabel("Build");
  await openSlot(page, "Item 2");
  await openSlot(page, "Runes");
  await build.getByRole("button", { name: /^Black Cleaver/ }).click();
  await build.getByRole("button", { name: /^Electrocute/ }).click();
  await expect(build.getByRole("button", { name: /^Black Cleaver/ })).toHaveAttribute("aria-pressed", "true");
  await expect(build.getByRole("button", { name: /^Runes Electrocute \(Domination \+ Precision\)/ })).toContainText("Your pick");
  await screenshot(page, "mock-picked");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await expect(page.getByRole("status")).toHaveText(/Your picks changed since/);
});

test("lists every option on request, and keeps picks after a restart", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  const build = page.getByLabel("Build");
  await openSlot(page, "Runes");
  await build.getByRole("button", { name: "Show 2 more" }).click();
  await build.getByRole("button", { name: /^Press the Attack/ }).click();
  await openSlot(page, "Item 1");
  await build.locator("#slot-item-1").getByRole("button", { name: "Show 1 more" }).click();
  await build.getByRole("button", { name: /^The Collector/ }).click();
  await expect(build.getByRole("button", { name: /^The Collector/ })).toHaveAttribute("aria-pressed", "true");
  await screenshot(page, "mock-all-options");

  await page.reload(); // the app starts again
  for (let i = 0; i < 3; i++) await next(page);
  await expect(build.getByRole("button", { name: /^Item 1 The Collector/ })).toContainText("Your pick");
  await expect(build.getByRole("button", { name: /^Runes Press the Attack \(Precision \+ Resolve\)/ })).toContainText("Your pick");
  await openSlot(page, "Item 1");
  await expect(build.getByRole("button", { name: /^The Collector/ })).toHaveAttribute("aria-pressed", "true");
  await screenshot(page, "mock-picks-restored");
  await page.getByRole("button", { name: "Use Stronk's picks" }).click();
  await page.reload();
  for (let i = 0; i < 3; i++) await next(page);
  await expect(build.getByRole("button", { name: /^Item 1 Eclipse/ })).toBeVisible();
});

test("shows the page rune by rune", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  await openSlot(page, "Runes");
  const byRune = page.getByRole("region", { name: "Rune by rune" });
  await expect(byRune.getByRole("heading", { level: 5 })).toHaveCount(7);
  await expect(byRune.locator(".option[aria-current]")).toHaveCount(7); // the page's choice in each row
  await screenshot(page, "mock-rune-by-rune");
});

test("fits a narrow window, one slot a line", async ({ page }) => {
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto("/?scenario=ranked-jungle");
  for (let i = 0; i < 3; i++) await next(page);
  await openSlot(page, "Item 3");
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
