// The product site's screenshots (`just site-shot`, ADR-066): Lee Sin jungle on the real data
// through the real core and lcu-mock, in the app's own dark look, the rune page open on the row
// where Stronk takes its best bet, with the real icons the recipe fetched (lcu-mock serves them);
// the champion's name is the client's ("Lee Sin"), not the data's key. Two views, the rune page
// on the row of Stronk's best bet and an item slot where it takes one, each as two pictures at the
// size the site shows them, so their text stays readable: the desktop app at 1200 px for wide
// screens, and the open slot in the app's narrow layout for phones. The app's wordmark, legend
// and hint are left out: the site says what they say.

import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../../..");
const IMG = resolve(ROOT, "site/public/img");

/** Each view: how to open it, once the champion is locked in. */
const VIEWS: Record<string, (page: Page) => Promise<void>> = {
  // The rune page, on the row where Stronk takes Cut Down over Coup de Grace.
  runes: async (page) => {
    await page.getByRole("tab", { name: /^Runes:/ }).click();
    await page.getByLabel("Rune page").getByRole("button", { name: "Cut Down" }).click();
    await expect(page.getByRole("radio", { name: /^Cut Down,/ })).toContainText("Best bet");
  },
  // Item 1, where Stronk takes Profane Hydra over Eclipse.
  items: async (page) => {
    await page.getByRole("tab", { name: /^Item 1:/ }).click();
    await expect(page.getByRole("radio", { name: /^Profane Hydra,/ })).toContainText("Best bet");
  },
};

async function open(page: Page, view: string): Promise<void> {
  await page.route("**/core/run", async (route) => {
    const request = route.request().postDataJSON() as { id: string };
    const response = await route.fetch();
    const body = (await response.json()) as { ok: boolean; value?: { champions?: Record<string, string> } };
    if (request.id === "names.get" && body.value?.champions) body.value.champions["64"] = "Lee Sin";
    return route.fulfill({ response, json: body });
  });
  expect((await page.request.post("/core/mock/reset")).ok()).toBe(true);
  await page.goto("/?backend=core");
  expect((await page.request.post("/core/mock/step")).ok()).toBe(true);
  await expect(page.getByRole("heading", { name: "Lee Sin" })).toBeVisible();
  await VIEWS[view]?.(page);
  // Every icon on screen loaded, none a stand-in letter.
  await expect(page.locator("main .stand-in")).toHaveCount(0);
  await page.addStyleTag({ content: "main > header, .legend, .how { display: none !important; }" });
  // No hover highlight left by the clicks.
  await page.mouse.move(0, 0);
}

for (const view of Object.keys(VIEWS)) {
  test.describe(`${view}, wide`, () => {
    test.use({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 2 });
    test(`the site's ${view} screenshot, wide`, async ({ page }) => {
      await open(page, view);
      // From the champion to the open slot: no settings, no footer.
      const top = await page.getByLabel("Champion select").boundingBox();
      const bottom = await page.getByRole("region", { name: "Build" }).boundingBox();
      if (!top || !bottom) throw new Error("nothing to capture");
      const y = top.y - 12;
      await page.screenshot({
        path: resolve(IMG, `${view}.png`),
        clip: { x: 0, y, width: 1200, height: bottom.y + bottom.height + 12 - y },
      });
    });
  });

  test.describe(`${view}, phone`, () => {
    test.use({ viewport: { width: 420, height: 1400 }, deviceScaleFactor: 2 }); // under the 512 KB file limit
    test(`the site's ${view} screenshot, narrow`, async ({ page }) => {
      await open(page, view);
      // The champion, then the open slot: the sheet, the patch line and the import button are the
      // wide picture's.
      await page.addStyleTag({
        content: '.loadout-card, [role="tabpanel"] .meta, .champ-select .actions { display: none !important; }',
      });
      const top = await page.getByLabel("Champion select").boundingBox();
      const panel = await page.getByRole("tabpanel").boundingBox();
      if (!top || !panel) throw new Error("nothing to capture");
      await page.screenshot({
        path: resolve(IMG, `${view}-phone.png`),
        clip: { x: 0, y: top.y - 8, width: 420, height: panel.y + panel.height + 8 - (top.y - 8) },
      });
    });
  });
}
