// Building a rune page by clicking runes, as the client lets the player (ADR-059): one keystone
// and one rune per row of the primary tree, two runes from two different rows of the secondary
// tree, one shard per shard row. The trees' layout comes from the player's client
// (`names.get`); the core checks the page again before importing it.

import type { GameNames, Page, Plan, Row } from "../../backend/backend.ts";

type Trees = GameNames["rune_trees"];

const rowsOf = (trees: Trees, style: number): number[][] => trees[String(style)] ?? [];

/** The most played published page with `primary` as its primary tree, if any. */
const playedWith = (plan: Plan, primary: number): Page | undefined =>
  [...plan.alternatives.runes.rows]
    .sort((a, b) => b.played - a.played)
    .find((r) => r.value.primary_style === primary)?.value;

/** The secondary pair most played in `style`, else its first rune of rows 1 and 2. */
function pairFor(plan: Plan, trees: Trees, style: number): [number, number] {
  const row = plan.alternatives.rune_rows.find((r) => r.kind === "secondary" && r.style === style);
  const best = row && [...row.rows].sort((a, b) => b.played - a.played)[0];
  if (best && best.value.length === 2) return [best.value[0] ?? 0, best.value[1] ?? 0];
  const rows = rowsOf(trees, style);
  return [rows[1]?.[0] ?? 0, rows[2]?.[0] ?? 0];
}

/** The page with another primary tree: the page most played with that tree, else the tree's
 * first rune in each row, keeping the secondary tree when it can stay and the shards. */
export function withPrimaryTree(plan: Plan, trees: Trees, page: Page, style: number): Page {
  if (style === page.primary_style) return page;
  const played = playedWith(plan, style);
  if (played) return { ...played, perks: [...played.perks.slice(0, 6), ...page.perks.slice(6)] };
  const rows = rowsOf(trees, style);
  const primary = rows.slice(0, 4).map((r) => r[0] ?? 0);
  let sub = page.sub_style;
  let pair = page.perks.slice(4, 6);
  if (sub === style) {
    sub = Number(Object.keys(trees).find((t) => Number(t) !== style) ?? 0);
    pair = pairFor(plan, trees, sub);
  }
  return { primary_style: style, sub_style: sub, perks: [...primary, ...pair, ...page.perks.slice(6)] };
}

/** The page with another secondary tree, its most played pair in that tree. */
export function withSecondaryTree(plan: Plan, trees: Trees, page: Page, style: number): Page {
  if (style === page.sub_style || style === page.primary_style) return page;
  const perks = [...page.perks];
  perks.splice(4, 2, ...pairFor(plan, trees, style));
  return { ...page, sub_style: style, perks };
}

/** The page with `rune` in its primary tree's `row` (0 is the keystone). */
export function withPrimaryRune(page: Page, row: number, rune: number): Page {
  const perks = [...page.perks];
  perks[row] = rune;
  return { ...page, perks };
}

/** The row (1 to 3) of `rune` in secondary tree `style`; -1 when it isn't in one. */
const secondaryRow = (trees: Trees, style: number) => (rune: number) =>
  rowsOf(trees, style).findIndex((row, i) => i > 0 && row.includes(rune));

/** The page with `pair` as its two secondary runes, in row order. */
export function withSecondaryPair(trees: Trees, page: Page, pair: number[]): Page {
  const rowOf = secondaryRow(trees, page.sub_style);
  const perks = [...page.perks];
  perks.splice(4, 2, ...[...pair].sort((a, b) => rowOf(a) - rowOf(b)));
  return { ...page, perks };
}

/** The page with `rune` among its two secondary runes. A rune from a row already taken
 * replaces the one in that row; otherwise it replaces the one picked before the other, as in
 * the client: `last` is the secondary rune the player picked last, kept when it's still on the
 * page (without it, the upper one goes). The two stay in row order, so the page alone can't
 * tell which came last. */
export function withSecondaryRune(trees: Trees, page: Page, rune: number, last: number | null = null): Page {
  const rowOf = secondaryRow(trees, page.sub_style);
  const row = rowOf(rune);
  if (row < 1) return page;
  const [first = 0, second = 0] = page.perks.slice(4, 6);
  let pair: number[];
  if (rowOf(first) === row) pair = [rune, second];
  else if (rowOf(second) === row) pair = [first, rune];
  else pair = [last === first ? first : second, rune];
  pair.sort((a, b) => rowOf(a) - rowOf(b));
  const perks = [...page.perks];
  perks.splice(4, 2, ...pair);
  return { ...page, perks };
}

/** The page with `shard` in shard row `row` (0 to 2). */
export function withShard(page: Page, row: number, shard: number): Page {
  const perks = [...page.perks];
  perks[6 + row] = shard;
  return { ...page, perks };
}

/** Each rune's numbers on this plan: a keystone's from its published page, the rest from the
 * rune rows of their tree, a shard's from its row (ADR-057). Secondary runes have none of their
 * own: they're measured as a pair (`runePairs`). */
export function runeStats(plan: Plan): {
  keystone: (id: number) => Row<unknown> | undefined;
  primary: (style: number, row: number, id: number) => Row<unknown> | undefined;
  shard: (row: number, id: number) => Row<unknown> | undefined;
} {
  const keystones = new Map<number, Row<unknown>>();
  for (const r of plan.alternatives.runes.rows) {
    const k = r.value.perks[0];
    if (k !== undefined && !keystones.has(k)) keystones.set(k, r);
  }
  const rows = new Map<string, Row<unknown>>();
  for (const r of plan.alternatives.rune_rows) {
    for (const x of r.rows) if (r.kind !== "secondary") rows.set(`${r.kind}/${r.style ?? ""}/${r.row ?? ""}/${x.value.join("+")}`, x);
  }
  return {
    keystone: (id) => keystones.get(id),
    primary: (style, row, id) => rows.get(`primary/${style}/${row}/${id}`),
    shard: (row, id) => rows.get(`shard//${row + 1}/${id}`),
  };
}
