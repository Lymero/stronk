// The product site's screenshots (`just site-shot`, ADR-066): Lee Sin jungle on the real data
// through the real core and lcu-mock, in the app's own dark look, the rune page open on the row
// where Stronk takes its best bet, with the real icons the recipe fetched (lcu-mock serves them);
// the champion's name is the client's ("Lee Sin"), not the data's key. Two pictures, each at the
// size the site shows it, so its text stays readable: the desktop app at 1200 px for wide
// screens, and the open slot in the app's narrow layout for phones. The app's wordmark, legend
// and hint are left out: the site says what they say.

import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../../..");
const IMG = resolve(ROOT, "site/public/img");

async function open(page: Page): Promise<void> {
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
  await page.getByRole("tab", { name: /^Runes:/ }).click();
  await page.getByLabel("Rune page").getByRole("button", { name: "Cut Down" }).click();
  await expect(page.getByRole("radio", { name: /^Cut Down,/ })).toContainText("Best bet");
  // Every icon on screen loaded, none a stand-in letter.
  await expect(page.locator("main .stand-in")).toHaveCount(0);
  await page.addStyleTag({ content: "main > header, .legend, .how { display: none !important; }" });
}

test.describe("desktop", () => {
  test.use({ viewport: { width: 1200, height: 900 }, deviceScaleFactor: 2 });
  test("the site's screenshot, wide", async ({ page }) => {
    await open(page);
    // From the champion to the open slot: no settings, no footer.
    const top = await page.getByLabel("Champion select").boundingBox();
    const bottom = await page.getByRole("region", { name: "Build" }).boundingBox();
    if (!top || !bottom) throw new Error("nothing to capture");
    const y = top.y - 12;
    await page.screenshot({
      path: resolve(IMG, "champion-select.png"),
      clip: { x: 0, y, width: 1200, height: bottom.y + bottom.height + 12 - y },
    });
  });
});

test.describe("phone", () => {
  test.use({ viewport: { width: 420, height: 1400 }, deviceScaleFactor: 2 }); // under the 512 KB file limit
  test("the site's screenshot, narrow", async ({ page }) => {
    await open(page);
    // The champion, then the open slot (the rune page and its row): the sheet, the patch line and
    // the import button are the wide picture's.
    await page.addStyleTag({
      content: '.loadout-card, [role="tabpanel"] .meta, .champ-select .actions { display: none !important; }',
    });
    const top = await page.getByLabel("Champion select").boundingBox();
    const panel = await page.getByRole("tabpanel").boundingBox();
    if (!top || !panel) throw new Error("nothing to capture");
    await page.screenshot({
      path: resolve(IMG, "champion-select-phone.png"),
      clip: { x: 0, y: top.y - 8, width: 420, height: panel.y + panel.height + 8 - (top.y - 8) },
    });
  });
});
