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
const NUMBER = /^(?:[▲▼]?[+−]\d+\.\d|0|too few to compare|almost always|)$/;

/** What may sit in a slot's number column: a difference with the baseline, 0, or why none. */
const COLUMN = /^(?:[▲▼] )?(?:[+−]\d+\.\d)$|^(?:0|too few to compare|almost always|)$/;

/** What a player would see in the open slot. */
async function slot(page: Page, name: string): Promise<string[]> {
  const problems: string[] = [];
  const panel = page.getByRole("tabpanel");
  const text = (await panel.innerText()).replace(/\s+/g, " ");
  // Values that leak from code, as whole words: "Infinity Edge" is an item.
  for (const bad of [/\bNaN\b/, /\bundefined\b/, /\bnull\b/, /\bInfinity\b(?! Edge)/, /\[object/]) {
    const found = bad.exec(text);
    if (found) problems.push(`${name}: shows "${found[0]}": …${text.slice(Math.max(0, found.index - 30), found.index + 30)}…`);
  }
  const tree = panel.getByLabel("Rune page");
  if ((await tree.count()) > 0) {
    const lit = await tree.locator(".cell.on").count();
    if (lit !== 9) problems.push(`${name}: ${lit} of 9 runes lit`);
    for (const n of new Set((await tree.locator(".cell .num").allInnerTexts()).map((t) => t.trim()))) {
      if (!NUMBER.test(n)) problems.push(`${name}: unexpected text under a rune: "${n}"`);
    }
    // Cards line up: one width within each row, one height for each kind.
    for (const row of await tree.locator(".row").all()) {
      const widths = await row.locator(".cell").evaluateAll((cells) => cells.map((c) => Math.round(c.getBoundingClientRect().width)));
      if (new Set(widths).size > 1) problems.push(`${name}: runes of different widths in a row: ${[...new Set(widths)].join(", ")}`);
    }
    for (const size of [".md", ".sm"]) {
      const heights = await tree.locator(`.cell${size}`).evaluateAll((cells) => cells.map((c) => Math.round(c.getBoundingClientRect().height)));
      if (new Set(heights).size > 1) problems.push(`${name}: runes of different heights (${size}): ${[...new Set(heights)].join(", ")}`);
    }
    const spilling = await tree.locator(".cell").evaluateAll((cells) =>
      cells
        .filter((c) => [c, ...c.querySelectorAll(".title, .stats, .games")].some((e) => e.scrollWidth > e.clientWidth + 1))
        .map((c) => c.getAttribute("aria-label") ?? ""),
    );
    for (const label of spilling) problems.push(`${name}: a rune spills out of its box: "${label}"`);
  } else {
    const rows = panel.getByRole("radio");
    const checked = await panel.getByRole("radio", { checked: true }).count();
    if ((await rows.count()) > 0 && checked !== 1) problems.push(`${name}: ${checked} options picked`);
    for (const n of new Set((await panel.locator(".row .num").allInnerTexts()).map((t) => t.trim()))) {
      if (!COLUMN.test(n)) problems.push(`${name}: unexpected number "${n}"`);
    }
    const labels = await rows.evaluateAll((r) => r.map((b) => b.getAttribute("aria-label") ?? ""));
    for (const label of labels.filter((l) => /^\D{0,6}\d{3,}\b/.test(l))) problems.push(`${name}: an option named by its id: "${label}"`);
  }
  return problems;
}

/** Every slot of the loadout opened in turn, then the page's width; each slot saved for the first pick, the last for the others. */
async function board(page: Page, pick: string, every: boolean): Promise<string[]> {
  const problems: string[] = [];
  const tabs = page.getByRole("tab");
  const count = await tabs.count();
  if (count === 0) problems.push("no loadout");
  for (let t = 0; t < count; t++) {
    const tab = tabs.nth(t);
    await tab.click();
    const name = (await tab.getAttribute("aria-label")) ?? `slot ${t}`;
    problems.push(...(await slot(page, name.split(":")[0] ?? name)));
    if (every || t === count - 1) await shot(page, `${pick}-${t}`);
  }
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 0) problems.push(`page scrolls sideways by ${overflow}px`);
  return problems;
}

const shot = (page: Page, name: string) =>
  page.screenshot({ path: `${ROOT}/runs/e2e-real/screenshots/${name.replace("/", "-")}.png`, fullPage: true });

session.picks.forEach((pick, i) => {
  test(`the board for ${pick}`, async ({ page }) => {
    expect((await page.request.post("/core/mock/reset")).ok()).toBe(true);
    await page.goto("/?backend=core");
    for (let s = 0; s <= i; s++) expect((await page.request.post("/core/mock/step")).ok()).toBe(true);
    const id = session.steps[i + 1]?.session?.myTeam[0]?.championId;
    const name = session.champions.find((c) => c.id === id)?.name ?? pick;
    await expect(page.getByRole("heading", { name })).toBeVisible();
    await expect(page.getByRole("button", { name: "Import" })).toBeVisible();
    await expect(page.getByRole("tab").first()).toBeVisible();
    await shot(page, pick);
    if (i === 0) {
      await page.emulateMedia({ colorScheme: "light" });
      await shot(page, `${pick}-light`);
      await page.emulateMedia({ colorScheme: "dark" });
    }
    expect(await board(page, pick, i === 0), `what a player would see on ${pick}`).toEqual([]);
  });
});
