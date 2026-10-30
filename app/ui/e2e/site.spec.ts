// The product site's screenshot (`just site-shot`, ADR-066): Lee Sin jungle on the real data
// through the real core and lcu-mock, in the app's own dark look, the rune page open on the row
// where Stronk takes its best bet, with the real icons the recipe fetched (lcu-mock serves them);
// the champion's name is the client's ("Lee Sin"), not the data's key.

import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

const ROOT = resolve(import.meta.dirname, "../../..");
const OUT = resolve(ROOT, "site/public/img/champion-select.png");

// Sharp on high-density screens: the site shows it at up to 760 px wide.
test.use({ deviceScaleFactor: 2 });

test("the site's screenshot", async ({ page }) => {
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
  // The app from its name to the open slot: no settings, no footer.
  const top = await page.locator("main > header").boundingBox();
  const bottom = await page.getByRole("region", { name: "Build" }).boundingBox();
  if (!top || !bottom) throw new Error("nothing to capture");
  await page.screenshot({
    path: OUT,
    clip: { x: 0, y: top.y - 12, width: 1200, height: bottom.y + bottom.height - top.y + 16 },
  });
});
