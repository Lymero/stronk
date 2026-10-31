// The rune page as rows of decisions (ADR-064): the keystones, the primary tree's three rows, the
// secondary tree's three rows and the three shard rows, each with its options in the shape the
// item lists take (`Slot`), what the page has in it, and the page picking an option makes. The
// secondary runes are measured as a pair, so their numbers come as one list of the tree's pairs
// (`runePairs`). The views draw these as they like; the client's rules stay in runes.ts.

import type { GameNames, Page, Plan, Row } from "../../backend/backend.ts";
import type { Shown, Slot } from "./options.ts";
import { runeStats, withPrimaryRune, withSecondaryPair, withSecondaryRune, withShard } from "./runes.ts";

export interface RuneRow {
  /** "primary-0" (the keystones) to "primary-3", "secondary-1" to "secondary-3", "shard-0" to "shard-2". */
  key: string;
  group: "primary" | "secondary" | "shards";
  /** "Keystone", "Row 1", "Offense"… */
  label: string;
  /** Its runes in the client's order. */
  ids: number[];
  /** Its runes as an item list takes them, most played first; none for a secondary row, whose
   * runes are listed as pairs (`runePairs`). */
  slot: Slot<number> | null;
  /** Whether Stronk's page has `id` in this row: the tree marks it when the player took another. */
  stronk: (id: number) => boolean;
  /** The rune the page has in this row; a secondary row may have none. */
  picked: number | undefined;
  /** The page with `id` picked in this row, by the client's rules. */
  next: (id: number) => Page;
}

const SHARD_ROWS = ["Offense", "Flex", "Defense"];

/** A rune nobody took in these games: no numbers. */
const unplayed = (id: number): Row<number> => ({
  value: id,
  played: 0,
  share: 0,
  wpa: null,
  ci: null,
  versus: "alternatives",
  confidence: "too_few_games",
  fragile: false,
  chosen: false,
  listed: true,
  judged: 0,
});

function slotOf(
  ids: number[],
  stat: (id: number) => Row<unknown> | undefined,
  on: (id: number) => boolean,
  stronk: (id: number) => boolean,
): Slot<number> {
  const rows: Shown<number>[] = ids.map((id) => ({
    ...(stat(id) ?? unplayed(id)),
    value: id,
    key: String(id),
    selected: on(id),
    chosen: stronk(id),
    shown: true,
  }));
  rows.sort((a, b) => b.played - a.played);
  return { rows, more: 0 };
}

/** Every row of `page` in the client's layout from `names`. `last` is the secondary rune picked
 * last, which a pick from a new secondary row keeps (as the client does). */
export function runeRows(
  plan: Plan,
  names: GameNames,
  page: Page,
  stronk: Page | null,
  last: number | null,
): RuneRow[] {
  const trees = names.rune_trees;
  const stats = runeStats(plan);
  const primary = trees[String(page.primary_style)] ?? [];
  const secondary = (trees[String(page.sub_style)] ?? []).slice(1);
  const has = (p: Page | null, id: number, from: number, to: number) => !!p && p.perks.slice(from, to).includes(id);
  return [
    ...primary.map((ids, r) => ({
      key: `primary-${r}`,
      group: "primary" as const,
      label: r === 0 ? "Keystone" : `Row ${r}`,
      ids,
      slot: slotOf(
        ids,
        (id) => (r === 0 ? stats.keystone(id) : stats.primary(page.primary_style, r, id)),
        (id) => has(page, id, r, r + 1),
        (id) => has(stronk, id, r, r + 1),
      ),
      stronk: (id: number) => has(stronk, id, r, r + 1),
      picked: ids.find((id) => page.perks[r] === id),
      next: (id: number) => withPrimaryRune(page, r, id),
    })),
    ...secondary.map((ids, r) => ({
      key: `secondary-${r + 1}`,
      group: "secondary" as const,
      label: `Row ${r + 1}`,
      ids,
      slot: null,
      stronk: (id: number) => has(stronk, id, 4, 6),
      picked: ids.find((id) => page.perks.slice(4, 6).includes(id)),
      next: (id: number) => withSecondaryRune(trees, page, id, last),
    })),
    ...names.shard_rows.map((ids, r) => ({
      key: `shard-${r}`,
      group: "shards" as const,
      label: SHARD_ROWS[r] ?? `Shard ${r + 1}`,
      ids,
      slot: slotOf(
        ids,
        (id) => stats.shard(r, id),
        (id) => page.perks[6 + r] === id,
        (id) => stronk?.perks[6 + r] === id,
      ),
      stronk: (id: number) => stronk?.perks[6 + r] === id,
      picked: ids.find((id) => page.perks[6 + r] === id),
      next: (id: number) => withShard(page, r, id),
    })),
  ];
}

/** The two runes of a pair as one key, whatever their order. */
const pairKey = (pair: number[]) => [...pair].sort((a, b) => a - b).join("+");

/** The page's secondary tree as a list of pairs, the way the data measures them: every pair
 * played in the tree, most played first, and the page's own pair even when nobody played it.
 * Picking one makes both the page's secondary runes. */
export function runePairs(
  plan: Plan,
  names: GameNames,
  page: Page,
  stronk: Page | null,
): { slot: Slot<number[]>; next: (pair: number[]) => Page } {
  const style = page.sub_style;
  const mine = pairKey(page.perks.slice(4, 6));
  const ours = stronk?.sub_style === style ? pairKey(stronk.perks.slice(4, 6)) : null;
  const played = plan.alternatives.rune_rows.find((r) => r.kind === "secondary" && r.style === style)?.rows ?? [];
  const pairs: Row<number[]>[] = played.some((r) => pairKey(r.value) === mine)
    ? played
    : [...played, { ...unplayed(0), value: page.perks.slice(4, 6) }];
  const rowOf = (id: number) => (names.rune_trees[String(style)] ?? []).findIndex((r, i) => i > 0 && r.includes(id));
  const rows: Shown<number[]>[] = pairs.map((r) => {
    const key = pairKey(r.value);
    return {
      ...r,
      value: [...r.value].sort((a, b) => rowOf(a) - rowOf(b)),
      key,
      selected: key === mine,
      chosen: key === ours,
      shown: r.listed || key === mine || key === ours,
    };
  });
  rows.sort((a, b) => b.played - a.played);
  return { slot: { rows, more: 0 }, next: (pair) => withSecondaryPair(names.rune_trees, page, pair) };
}
