// The rule behind the rows (order, confidence, which are listed) is tested in the core
// (stronk_domain::select::rank, build.plan); here only what the view adds to them.

import { describe, expect, it } from "vitest";
import type { Plan, Row } from "../../backend/backend.ts";
import { allPopular, changes, explain, figure, mostPlayed, options, selected, share, verdict, wins } from "./options.ts";

const row = <T>(value: T, rest: Partial<Row<T>> = {}): Row<T> => ({
  value,
  played: 10,
  share: 0.1,
  wpa: null,
  ci: null,
  versus: "alternatives",
  confidence: "most_played",
  fragile: false,
  chosen: false,
  listed: true,
  judged: 0,
  ...rest,
});

const plan = (over: Partial<Plan> = {}): Plan => ({
  champion: "LeeSin",
  role: "JUNGLE",
  patch: "16.20",
  games: 1000,
  elo: "master_plus",
  region: "all",
  runes: null,
  spells: { value: [11, 4], label: "popular" },
  items: [{ slot: 4, value: 10, label: "popular" }],
  start: null,
  late_slot: null,
  alternatives: {
    runes: { rows: [row({ primary_style: 8000, sub_style: 8300, perks: [8010, 2, 3] }, { chosen: true })], more: 0 },
    spells: { rows: [row<[number, number]>([11, 4], { chosen: true }), row<[number, number]>([14, 11])], more: 0 },
    start: { rows: [], more: 0 },
    items: [
      {
        slot: 4,
        rows: [row(10, { chosen: true }), row(20), row(50), row(60, { listed: false }), row(70, { listed: false })],
        more: 2,
      },
    ],
    rune_rows: [],
  },
  ...over,
});

describe("options", () => {
  it("keeps the core's rows and count, keyed, Stronk's choice selected", () => {
    const o = options(plan());
    expect(o.runes.rows.map((r) => [r.key, r.selected])).toEqual([["8000/8300/8010,2,3", true]]);
    expect(o.spells.rows.map((r) => [r.key, r.selected])).toEqual([
      ["11,4", true],
      ["11,14", false],
    ]);
    expect(o.items[0]).toMatchObject({ slot: 4, more: 2 });
    expect(o.items[0]?.rows.map((r) => r.shown)).toEqual([true, true, true, false, false]);
  });

  it("lists a pick from past the short list, and counts one fewer left out", () => {
    const o = options(plan(), { items: { 4: 70 } });
    expect(o.items[0]?.rows.map((r) => [r.value, r.selected, r.shown])).toEqual([
      [10, false, true],
      [20, false, true],
      [50, false, true],
      [60, false, false],
      [70, true, true],
    ]);
    expect(o.items[0]?.more).toBe(1);
  });

  it("selects the player's pick instead, Stronk's choice still marked", () => {
    const o = options(plan(), { items: { 4: 50 }, spells: [4, 11] });
    expect(o.items[0]?.rows.map((r) => [r.value, r.chosen, r.selected])).toEqual([
      [10, true, false],
      [20, false, false],
      [50, false, true],
      [60, false, false],
      [70, false, false],
    ]);
    expect(o.spells.rows.map((r) => r.selected)).toEqual([true, false]); // same pair, other keys
  });

  it("gives a verdict only for a clear difference", () => {
    const better = row(1, { wpa: 0.021, ci: [0.008, 0.034], versus: "most_played", confidence: "clearly_better" });
    expect(verdict(better)).toEqual({ text: "▲ +2.1 wins per 100", tone: "positive" });
    expect(verdict(row(1, { wpa: -0.018, versus: "most_played", confidence: "clearly_worse" }))).toEqual({ text: "▼ −1.8 wins per 100", tone: "negative" });
    for (const confidence of ["most_played", "no_clear_difference", "too_few_games", "not_estimated"] as const) {
      expect(verdict(row(1, { wpa: 0.05, versus: "most_played", confidence }))).toBeNull();
    }
    expect(verdict(row(1, { wpa: null, confidence: "clearly_better" }))).toBeNull();
  });

  it("shows only numbers against the most played option, so a row reads on one scale", () => {
    const unsure = { confidence: "no_clear_difference" } as const;
    // Against the other options pooled: a different mix for each option, so no number.
    expect(figure(row(1, { wpa: 0.004, ci: [-0.006, 0.014], versus: "alternatives", ...unsure }))).toBeNull();
    expect(figure(row(1, { wpa: -0.009, ci: [-0.024, 0.006], versus: "most_played", ...unsure }))).toBe("−0.9 wins per 100");
    // The most played option is what the others are measured against: no number of its own.
    const base = row(1, { wpa: -0.024, ci: [-0.041, -0.008], confidence: "most_played" });
    expect(figure(base)).toBeNull();
    expect(explain(base)).toBe("Most played, the others are compared with it.");
    expect(figure(row(1, { wpa: null }))).toBeNull();
    const unclear = row(1, { wpa: -0.009, ci: [-0.024, 0.006], versus: "most_played", confidence: "no_clear_difference" });
    expect(explain(unclear)).toBe(
      "−0.9 wins per 100 games against the most played option. Likely between −2.4 and +0.6 (95%). No clear difference: the interval is too wide to tell it apart from the most played option.",
    );
    expect(explain(row(1, { wpa: null, confidence: "too_few_games" }))).toBe("Too few comparable games to estimate its win impact");
  });

  it("finds a slot's most played option and the one the import writes", () => {
    const slot = {
      rows: [
        { ...row(1, { confidence: "no_clear_difference" }), key: "1", selected: false, shown: true },
        { ...row(2), key: "2", selected: true, shown: true },
      ],
      more: 0,
    };
    expect(mostPlayed(slot)?.value).toBe(2);
    expect(selected(slot)?.value).toBe(2);
    expect(mostPlayed({ rows: [], more: 0 })).toBeUndefined();
  });

  it("formats win impact and shares", () => {
    expect([wins(0.021), wins(-0.004), share(0.3575)]).toEqual(["+2.1", "−0.4", "36%"]);
  });

  it("lists what Stronk imports instead of the most played option, and what it beats", () => {
    const p = plan({
      alternatives: {
        runes: { rows: [], more: 0 },
        spells: { rows: [row([4, 11] as [number, number], { chosen: true })], more: 0 },
        start: { rows: [], more: 0 },
        items: [
          {
            slot: 2,
            rows: [
              row(10, { played: 90 }),
              row(11, { wpa: 0.021, versus: "most_played", confidence: "clearly_better", chosen: true }),
            ],
            more: 0,
          },
          { slot: 3, rows: [row(12, { chosen: true })], more: 0 },
        ],
        rune_rows: [],
      },
    });
    const found = changes(options(p));
    expect(found.map((c) => [c.part, c.row.value, c.base?.value])).toEqual([[2, 11, 10]]);
    expect(changes(options(plan()))).toEqual([]);
  });

  it("reads Stronk's best bet apart from a clear result, and finds it in rune rows", () => {
    const bet = row(1, { wpa: 0.027, ci: [0.0, 0.056], versus: "most_played", confidence: "best_bet", chosen: true });
    expect(verdict(bet)).toEqual({ text: "Best bet +2.7 wins per 100", tone: "bet" });
    expect(explain(bet)).toContain("Stronk's best bet: ahead of the most played option on the numbers so far, not yet clear");
    const runeRows = [
      {
        kind: "primary" as const,
        style: 8000,
        row: 3,
        rows: [row([8014], { played: 2194, confidence: "most_played" }), row([8017], { ...bet, value: [8017], played: 1704 })],
        more: 0,
      },
    ];
    const found = changes(options(plan()), runeRows);
    expect(found.map((c) => [c.part, c.row.value, c.base?.value])).toEqual([["rune", [8017], [8014]]]);
  });

  it("knows when every choice is the most played one", () => {
    expect(allPopular(plan())).toBe(true);
    const better = { slot: 4, value: 10, label: "clearly_better", wpa: 0.02, ci: null, games: 5 } as const;
    expect(allPopular(plan({ items: [better] }))).toBe(false);
  });
});
