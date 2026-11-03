// The web viewer (ADR-086) in Chromium: its WebAssembly core (`just web-core`) on the signed
// fixture data, served as the CDN would. CommunityDragon is stubbed: the client's game data from
// lcu-mock's subset (tools/lcu_mock/game_data.json), a champion summary naming the fixture's
// champions by their keys and Lee Sin by name, each champion's abilities, and no images
// (stand-ins show).

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { VIEWER_DATA, VIEWER_GAME_DATA } from "../playwright.config.ts";
import { screenshot } from "./screens.ts";

const ROOT = resolve(import.meta.dirname, "../../..");
const VIEWER = "http://127.0.0.1:5174/viewer.html";
const gameData = JSON.parse(readFileSync(`${ROOT}/tools/lcu_mock/game_data.json`, "utf8")) as Record<string, unknown>;
const manifest = JSON.parse(readFileSync(`${ROOT}/fixtures/data/16.20/manifest.json`, "utf8")) as { files: { path: string }[] };
const keys = [...new Set(manifest.files.map((f) => f.path.split("/")[2]).filter((k): k is string => !!k && !k.endsWith(".json")))];
const champions = keys.map((alias, i) => ({
  id: alias === "LeeSin" ? 64 : 1000 + i,
  alias,
  name: alias === "LeeSin" ? "Lee Sin" : alias,
  squarePortraitPath: `/lol-game-data/assets/v1/champion-icons/${alias === "LeeSin" ? 64 : 1000 + i}.png`,
}));

async function stubGameData(page: Page): Promise<string[]> {
  const asked: string[] = [];
  await page.route(`${VIEWER_GAME_DATA}**`, (route) => {
    const url = route.request().url();
    asked.push(url);
    const doc = url.match(/\/global\/default\/v1\/([a-z-]+\.json)$/)?.[1];
    const champion = Number(url.match(/\/v1\/champions\/(\d+)\.json$/)?.[1] ?? 0);
    const abilities = (id: number) => ({
      id,
      spells: [..."qwer"].map((k) => ({ spellKey: k, abilityIconPath: `/lol-game-data/assets/v1/abilities/${id}${k}.png` })),
    });
    const body = champion
      ? abilities(champion)
      : doc === "champion-summary.json"
        ? champions
        : doc
          ? gameData[`/lol-game-data/assets/v1/${doc}`]
          : undefined;
    return body === undefined ? route.fulfill({ status: 404 }) : route.fulfill({ json: body });
  });
  return asked;
}

test("lists the builds by role and shows the one picked, read-only", async ({ page }) => {
  const asked = await stubGameData(page);
  await page.goto(VIEWER);
  await expect(page.getByText("Choose a champion and a role")).toBeVisible();
  await page.getByRole("button", { name: "Jungle", exact: true }).click();
  await page.getByRole("button", { name: "Lee Sin Jungle" }).click();
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Build to import" })).toBeVisible();
  // Nothing to import into: no Import button, no settings.
  await expect(page.getByRole("button", { name: "Import" })).toHaveCount(0);
  await expect(page.getByText("Settings")).toHaveCount(0);
  await expect(page).toHaveURL(/\?champion=LeeSin&role=JUNGLE$/);
  // Names and icons came from the patch's game data on CommunityDragon.
  expect(asked.some((u) => u.startsWith(`${VIEWER_GAME_DATA}16.20/plugins/rcp-be-lol-game-data/global/default/v1/`))).toBe(true);
  // Lee Sin's abilities, for the skill order, from his own document.
  await expect.poll(() => asked.filter((u) => u.endsWith("/v1/champions/64.json")).length).toBe(1);
  await expect.poll(() => asked.some((u) => u.endsWith("/global/default/v1/abilities/64q.png"))).toBe(true);
  await screenshot(page, "viewer-board");
});

test("opens on the build its address names", async ({ page }) => {
  await stubGameData(page);
  await page.goto(`${VIEWER}?champion=LeeSin&role=JUNGLE`);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Lee Sin Jungle" })).toHaveClass(/current/);
});

test("refuses a build file that isn't the one the signed manifest lists", async ({ page }) => {
  await stubGameData(page);
  await page.route(`${VIEWER_DATA}16.20/all/master_plus/LeeSin/JUNGLE.json`, async (route) => {
    const response = await route.fetch();
    const tampered = (await response.text()).replace('"games":', '"games": 1, "x":');
    return route.fulfill({ response, body: tampered });
  });
  await page.goto(`${VIEWER}?champion=LeeSin&role=JUNGLE`);
  await expect(page.getByRole("alert")).toContainText("refused");
  await expect(page.getByRole("tablist", { name: "Build to import" })).toHaveCount(0);
});

test("fits a narrow window", async ({ page }) => {
  await stubGameData(page);
  await page.setViewportSize({ width: 420, height: 900 });
  await page.goto(`${VIEWER}?champion=LeeSin&role=JUNGLE`);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await screenshot(page, "viewer-narrow");
});
