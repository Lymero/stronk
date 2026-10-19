import { describe, expect, it } from "vitest";
import type { Build, Plan } from "../../backend/backend.ts";
import { allPopular, alternatives, SHOWN } from "./options.ts";

const perks = (keystone: number): Build["runes"][number]["page"]["perks"] => [keystone, 2, 3, 4, 5, 6, 7, 8, 9];

function build(items: Build["items"], runes: Build["runes"] = []): Build {
  return {
    schemaVersion: 1,
    patch: "16.20",
    region: "all",
    elo: "master_plus",
    champion: "LeeSin",
    role: "JUNGLE",
    games: 1000,
    runes,
    spells: [
      { spells: [4, 11], wpa: null, ci: null, n: 900, games: 900, flags: [] },
      { spells: [11, 14], wpa: null, ci: null, n: 100, games: 100, flags: ["low_sample"] },
    ],
    items,
  };
}

const plan = (items: Plan["items"], over: Partial<Plan> = {}): Plan => ({
  champion: "LeeSin",
  role: "JUNGLE",
  patch: "16.20",
  runes: null,
  spells: { value: [11, 4], label: "popular" },
  items,
  ...over,
});

const item = (slot: number, id: number, picks: number, rest: Partial<Build["items"][number]> = {}) => ({
  slot,
  item: id,
  wpa: 0.01,
  ci: [-0.01, 0.03] as [number, number],
  n: picks,
  picks,
  flags: [] as Build["items"][number]["flags"],
  ...rest,
});

describe("alternatives", () => {
  it("lists a slot's options by popularity with their share of games", () => {
    const b = build([item(1, 10, 600), item(1, 20, 300), item(1, 30, 100)]);
    const [slot] = alternatives(b, plan([{ slot: 1, value: 10, label: "popular" }])).items;
    expect(slot?.rows.map((r) => [r.value, r.share])).toEqual([
      [10, 0.6],
      [20, 0.3],
      [30, 0.1],
    ]);
    expect(slot?.rows.map((r) => r.chosen)).toEqual([true, false, false]);
    expect(slot?.rows[0]?.confidence).toBe("most_played");
  });

  it("calls a difference clear only against the most played option with q at most 0.05", () => {
    const b = build([
      item(1, 10, 500),
      item(1, 20, 300, { comparison: { versus: 10, wpa: 0.02, q: 0.03, ci: [0.01, 0.03] } }),
      item(1, 30, 150, { comparison: { versus: 10, wpa: -0.02, q: 0.01 } }),
      item(1, 40, 50, { comparison: { versus: 99, wpa: 0.05, q: 0.001 } }),
    ]);
    const rows = alternatives(b, plan([])).items[0]?.rows ?? [];
    expect(rows.map((r) => r.confidence)).toEqual(["most_played", "clearly_better", "clearly_worse"]);
    expect(rows[1]).toMatchObject({ wpa: 0.02, ci: [0.01, 0.03], versus: "most_played" });
    expect(rows[2]).toMatchObject({ wpa: -0.02, ci: null, versus: "most_played" });
    // Compared with something else: its own estimate against the alternatives, not a claim.
    const other = alternatives(b, plan([])).items[0];
    expect(other?.more).toBe(1);
  });

  it("flags rare options and keeps fragile ones visible as such", () => {
    const b = build([
      item(1, 10, 500, { flags: ["low_overlap"], wpa: null, ci: null }),
      item(1, 20, 300, { flags: ["no_clear_difference", "fragile"], comparison: { versus: 10, wpa: 0.01, q: 0.4 } }),
      item(1, 30, 200, { flags: ["no_clear_difference"], comparison: { versus: 10, wpa: 0.03, q: 0.01 } }),
    ]);
    const rows = alternatives(b, plan([])).items[0]?.rows ?? [];
    expect(rows.map((r) => r.confidence)).toEqual(["too_few_games", "no_clear_difference", "no_clear_difference"]);
    expect(rows.map((r) => r.fragile)).toEqual([false, true, false]);
  });

  it(`shows the ${SHOWN} most played and the chosen option when it is rarer`, () => {
    const b = build([
      item(2, 10, 500),
      item(2, 20, 400),
      item(2, 30, 300),
      item(2, 40, 200),
      item(2, 50, 100, { comparison: { versus: 10, wpa: 0.03, q: 0.02 } }),
    ]);
    const chosen = { slot: 2, value: 50, label: "clearly_better", wpa: 0.03, ci: null, games: 100 } as const;
    const slot = alternatives(b, plan([chosen])).items[0];
    expect(slot?.rows.map((r) => r.value)).toEqual([10, 20, 30, 50]);
    expect(slot?.more).toBe(1);
    expect(slot?.rows.at(-1)?.chosen).toBe(true);
  });

  it("matches the chosen rune page and spell pair whatever the key order", () => {
    const runes: Build["runes"] = [
      { page: { primaryStyle: 8000, subStyle: 8300, perks: perks(8010) }, wpa: null, ci: null, n: 10, games: 10, flags: [] },
      { page: { primaryStyle: 8100, subStyle: 8000, perks: perks(8112) }, wpa: null, ci: null, n: 30, games: 30, flags: [] },
    ];
    const p = plan([], {
      runes: { value: { primary_style: 8000, sub_style: 8300, perks: perks(8010) }, label: "popular" },
    });
    const a = alternatives(build([], runes), p);
    expect(a.runes.rows.map((r) => [r.value.perks[0], r.chosen])).toEqual([
      [8112, false],
      [8010, true],
    ]);
    expect(a.spells.rows.map((r) => [r.value, r.chosen, r.confidence])).toEqual([
      [[4, 11], true, "most_played"],
      [[11, 14], false, "too_few_games"],
    ]);
  });

  it("knows when every choice is the most played one", () => {
    expect(allPopular(plan([{ slot: 1, value: 10, label: "popular" }]))).toBe(true);
    const better = { slot: 1, value: 10, label: "clearly_better", wpa: 0.02, ci: null, games: 5 } as const;
    expect(allPopular(plan([better]))).toBe(false);
  });
});
