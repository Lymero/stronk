// The UI against MockBackend scenarios, in a real browser.

import { expect, test } from "@playwright/test";
import { screenshot } from "./screens.ts";

const next = (page: import("@playwright/test").Page) => page.getByRole("button", { name: "Next step" }).click();

test("follows champion select and shows the plan by name", async ({ page }) => {
  await page.goto("/?scenario=ranked-jungle");
  await expect(page.getByText("Waiting for champion select")).toBeVisible();
  await next(page);
  await expect(page.getByRole("heading", { name: "Graves" })).toBeVisible();
  await expect(page.getByText("Jungle · Hovering · Declaring picks")).toBeVisible();
  await next(page);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByText("Conqueror · Triumph · Legend: Alacrity · Coup de Grace")).toBeVisible();
  await expect(page.getByText("Smite · Flash")).toBeVisible();
  await expect(page.getByText("Clearly better · +2.1% win")).toBeVisible();
  await screenshot(page, "mock-hovering");
  await next(page);
  await expect(page.getByText("Jungle · Locked in · Final changes")).toBeVisible();
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await screenshot(page, "mock-imported");
});

test("warns when every rune page is in use", async ({ page }) => {
  await page.goto("/?scenario=pages-full");
  for (let i = 0; i < 3; i++) await next(page);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("alert")).toHaveText(/Rune page not imported: all your rune pages are in use/);
  await screenshot(page, "mock-pages-full");
});

test("says when the League client isn't running", async ({ page }) => {
  await page.goto("/?scenario=no-client");
  await expect(page.getByRole("alert")).toHaveText(/is the League client running\?/);
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
