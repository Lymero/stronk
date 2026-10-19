// The UI against the real core: a replayed ranked champion select on lcu-mock, the signed
// fixture data, imports written into lcu-mock (tools/lcu_mock/core_bridge.py). The session is
// moved on by the test, never by a player's input, and only ever against lcu-mock.

import { expect, type Page, test } from "@playwright/test";
import { screenshot } from "./screens.ts";

interface Write {
  method: string;
  path: string;
  body: unknown;
}

const PAGES = "/lol-perks/v1/pages";
const ITEM_SETS = "/lol-item-sets/v1/item-sets/1/sets";
const SELECTION = "/lol-champ-select/v1/session/my-selection";

async function step(page: Page, times = 1): Promise<void> {
  for (let i = 0; i < times; i++) {
    const response = await page.request.post("/core/mock/step");
    expect(response.ok()).toBe(true);
  }
}

const recorded = async (page: Page): Promise<Write[]> =>
  (await (await page.request.get("/core/mock/recorded")).json()) as Write[];

test.beforeEach(async ({ page }) => {
  expect((await page.request.post("/core/mock/reset")).ok()).toBe(true);
  await page.goto("/?backend=core");
});

test("a replayed lobby leads to the Lee Sin jungle import", async ({ page }) => {
  await expect(page.getByText("Waiting for champion select")).toBeVisible();
  await expect(page.getByText("Data 16.20")).toBeVisible();
  await step(page);
  await expect(page.getByRole("heading", { name: "Graves" })).toBeVisible();
  await step(page);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible(); // the client's name
  await expect(page.getByText("Jungle · Hovering · Bans and picks")).toBeVisible();
  await expect(page.getByLabel("Build").getByText("Precision", { exact: true })).toBeVisible();
  // Icons from the client's game data, as PNG data URLs through the core.
  const portrait = page.getByLabel("Champion select").locator("img");
  await expect(portrait).toHaveAttribute("src", /^data:image\/png;base64,/);
  await expect(page.getByLabel("Build").locator("img").first()).toHaveAttribute("src", /^data:image\/png;base64,/);
  await step(page);
  await expect(page.getByText("Jungle · Locked in · Final changes")).toBeVisible();
  expect(await recorded(page)).toEqual([]); // nothing written before the player asks
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await screenshot(page, "core-imported");

  const writes = await recorded(page);
  const created = writes.find((w) => w.method === "POST" && w.path === PAGES);
  expect(created?.body).toMatchObject({ name: "Stronk: LeeSin JUNGLE", current: true });
  expect(writes.filter((w) => w.method === "PUT" && w.path === ITEM_SETS)).toHaveLength(1);
  // The session has no spells chosen, so the pair keeps its usual order: Smite on D, Flash on F.
  expect(writes.find((w) => w.path === SELECTION)?.body).toEqual({ spell1Id: 11, spell2Id: 4 });
});

test("auto-import writes once on lock-in", async ({ page }) => {
  await page.getByText("Settings").click();
  await page.getByLabel("Auto-import on lock-in").check();
  await step(page, 2);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  expect(await recorded(page)).toEqual([]); // hovering: nothing yet
  await step(page);
  await expect(page.getByRole("status")).toHaveText(/Imported: Rune page, Item set, Spells\./);
  await page.waitForTimeout(2500); // two more polls of the same lock-in
  const pages = (await recorded(page)).filter((w) => w.method === "POST" && w.path === PAGES);
  expect(pages).toHaveLength(1);
});

test("restore puts the player's item sets back after an import", async ({ page }) => {
  await step(page, 3);
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("status")).toHaveText(/Item set/);
  await page.getByText("Settings").click();
  await expect(page.getByRole("radio")).toHaveCount(1); // the sets from before the import
  await page.getByRole("button", { name: "Restore this backup" }).click();
  await page.getByRole("group", { name: "Confirm restore" }).getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText(/Restored 1 item set\./)).toBeVisible();
  await expect(page.getByRole("radio")).toHaveCount(2); // Stronk's sets, backed up first
  await screenshot(page, "core-restored");
  const puts = (await recorded(page)).filter((w) => w.method === "PUT" && w.path === ITEM_SETS);
  expect(puts).toHaveLength(2);
  expect(JSON.stringify(puts[1]?.body)).toContain('"My Lee Sin"');
  expect(JSON.stringify(puts[1]?.body)).not.toContain("Stronk:");
});
