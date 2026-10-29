// The board on the real data (`just e2e-real`, ADR-061): for each pick of the generated session,
// lock it in on lcu-mock, check what a player would see, and save the board to
// runs/e2e-real/screenshots/ to be looked at. Each check names the board and what's wrong.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../../..");
const session = JSON.parse(readFileSync(resolve(ROOT, "runs/e2e-real/session.json"), "utf-8")) as {
  picks: string[];
  champions: { id: number; name: string }[];
  steps: { session: { myTeam: { championId: number }[] } | null }[];
};

/** What may sit under an option: its number, 0 for the baseline, or why it has none. */
const NUMBER = /^(?:[▲▼]?[+−]\d+\.\d|0|few games|too few to compare|almost always|)$/;

async function board(page: Page): Promise<string[]> {
  const problems: string[] = [];
  const build = page.getByRole("region", { name: "Build" });
  const text = (await build.innerText()).replace(/\s+/g, " ");
  // Values that leak from code, as whole words: "Infinity Edge" is an item.
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\bnull\b/, /\bInfinity\b(?! Edge)/, /\[object/]) {
    const found = bad.exec(text);
    if (found) problems.push(`shows "${found[0]}": …${text.slice(Math.max(0, found.index - 30), found.index + 30)}…`);
  }
  const numbers = await build.locator(".cell .num").allInnerTexts();
  for (const n of new Set(numbers.map((t) => t.trim()).filter((t) => !NUMBER.test(t)))) {
    problems.push(`unexpected text under an option: "${n}"`);
  }
  const labels = await build.locator(".cell").evaluateAll((cells) => cells.map((c) => c.getAttribute("aria-label") ?? ""));
  for (const label of labels.filter((l) => /^\D{0,6}\d{3,}\b/.test(l))) problems.push(`an option named by its id: "${label}"`);
  for (const slot of await build.getByRole("region", { name: /^Item \d/ }).all()) {
    const lit = await slot.locator(".cell.on").count();
    if (lit !== 1) problems.push(`${await slot.getAttribute("aria-label")}: ${lit} picks lit`);
  }
  const runes = page.getByLabel("Rune page");
  if ((await runes.count()) > 0) {
    const lit = await runes.locator(".cell.on").count();
    if (lit !== 9) problems.push(`rune page: ${lit} of 9 runes lit`);
  }
  const spells = await build.getByRole("region", { name: "Summoner spells" }).locator(".cell.on").count();
  if (spells !== 1) problems.push(`summoner spells: ${spells} pairs lit`);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 0) problems.push(`page scrolls sideways by ${overflow}px`);
  return problems;
}

session.picks.forEach((pick, i) => {
  test(`the board for ${pick}`, async ({ page }) => {
    expect((await page.request.post("/core/mock/reset")).ok()).toBe(true);
    await page.goto("/?backend=core");
    for (let s = 0; s <= i; s++) expect((await page.request.post("/core/mock/step")).ok()).toBe(true);
    const id = session.steps[i + 1]?.session?.myTeam[0]?.championId;
    const name = session.champions.find((c) => c.id === id)?.name ?? pick;
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Build" }).locator(".cell").first()).toBeVisible();
    await page.screenshot({ path: `${ROOT}/runs/e2e-real/screenshots/${pick.replace("/", "-")}.png`, fullPage: true });
    expect(await board(page), `what a player would see on ${pick}`).toEqual([]);
  });
});
