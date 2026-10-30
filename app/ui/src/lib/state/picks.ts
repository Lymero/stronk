// The player's picks instead of Stronk's choices (ADR-050): part of the single app state, the
// equality rules that tell a pick from Stronk's choice, and where they are kept between runs
// (ADR-051).

import type { Page, Plan } from "../backend/backend.ts";

/** The player's picks for one champion and role; a slot without one keeps Stronk's choice. */
export interface Picks {
  runes?: Page | undefined;
  spells?: [number, number] | undefined;
  /** A start's items, smallest id first (ADR-071). */
  start?: number[] | undefined;
  /** First components, smallest id first (ADR-072). */
  components?: number[] | undefined;
  /** Upgraded boots (ADR-073). */
  boots?: number | undefined;
  /** Item id by slot. */
  items: Record<number, number>;
}

/** A pick for one slot; picking Stronk's choice again drops it. */
export type Pick =
  | { runes: Page }
  | { spells: [number, number] }
  | { start: number[] }
  | { components: number[] }
  | { boots: number }
  | { slot: number; item: number };

export const noPicks = (): Picks => ({ items: {} });

/** The purchases picked as a set of items: the start (ADR-071), the first components (ADR-072). */
export const PURCHASES = ["start", "components"] as const;
export type Purchase = (typeof PURCHASES)[number];

export const samePage = (a: Page, b: Page): boolean => {
  // The two secondary runes are one choice, whichever order the data or the player gives them in.
  const key = (p: Page) => [...p.perks.slice(0, 4), ...[...p.perks.slice(4, 6)].sort((x, y) => x - y), ...p.perks.slice(6)].join();
  return a.primary_style === b.primary_style && a.sub_style === b.sub_style && key(a) === key(b);
};

/** The same two spells, whichever key each is on; the same items of a start, in any order. */
export const samePair = (a: readonly number[], b: readonly number[]): boolean =>
  [...a].sort().join() === [...b].sort().join();

/** The picks among the plan's options; any other (the data changed) is dropped. A rune page
 * can be one the player built (ADR-059): kept when whole, the core checks it against the
 * client's trees. The core refuses other unpublished picks anyway; this keeps the view from
 * showing one it would refuse. */
export function published(plan: Plan, picks: Picks): Picks {
  const { spells, items } = plan.alternatives;
  const kept: Picks = { items: {} };
  if (picks.runes && picks.runes.perks.length === 9) kept.runes = picks.runes;
  if (picks.spells && spells.rows.some((r) => samePair(r.value, picks.spells as [number, number]))) {
    kept.spells = picks.spells;
  }
  if (picks.boots !== undefined && plan.alternatives.boots.rows.some((r) => r.value === picks.boots)) {
    kept.boots = picks.boots;
  }
  for (const key of PURCHASES) {
    const items = picks[key];
    if (items && plan.alternatives[key].rows.some((r) => samePair(r.value, items))) kept[key] = items;
  }
  for (const [slot, item] of Object.entries(picks.items)) {
    if (items.some((s) => s.slot === Number(slot) && s.rows.some((r) => r.value === item))) {
      kept.items[Number(slot)] = item;
    }
  }
  return kept;
}

export const isEmpty = (picks: Picks): boolean =>
  picks.runes === undefined &&
  picks.spells === undefined &&
  picks.start === undefined &&
  picks.components === undefined &&
  picks.boots === undefined &&
  Object.keys(picks.items).length === 0;

/** Picks by champion and role (`LeeSin/JUNGLE`), each for the patch it was made on. */
export type SavedPicks = Record<string, { patch: string; picks: Picks }>;

/** Where picks live between runs; any Storage, so tests can pass their own. */
export interface PicksStore {
  load(): SavedPicks;
  save(saved: SavedPicks): void;
}

const KEY = "stronk.picks";

const isPage = (v: unknown): v is Page =>
  !!v &&
  typeof v === "object" &&
  "primary_style" in v &&
  "sub_style" in v &&
  "perks" in v &&
  Number.isInteger(v.primary_style) &&
  Number.isInteger(v.sub_style) &&
  Array.isArray(v.perks) &&
  v.perks.every(Number.isInteger);

/** Picks read back from storage, or `null` when they aren't picks: storage is outside input. */
function parsePicks(v: unknown): Picks | null {
  if (!v || typeof v !== "object" || !("items" in v) || !v.items || typeof v.items !== "object") return null;
  const picks: Picks = { items: {} };
  for (const [slot, item] of Object.entries(v.items)) {
    if (!Number.isInteger(Number(slot)) || !Number.isInteger(item)) return null;
    picks.items[Number(slot)] = item as number;
  }
  if ("runes" in v && v.runes !== undefined) {
    if (!isPage(v.runes)) return null;
    picks.runes = v.runes;
  }
  if ("spells" in v && v.spells !== undefined) {
    const s = v.spells;
    if (!Array.isArray(s) || s.length !== 2 || !s.every(Number.isInteger)) return null;
    picks.spells = [s[0], s[1]];
  }
  if ("boots" in v && v.boots !== undefined) {
    if (!Number.isInteger(v.boots)) return null;
    picks.boots = v.boots as number;
  }
  for (const key of PURCHASES) {
    if (!(key in v)) continue;
    const s = (v as Record<string, unknown>)[key];
    if (s === undefined) continue;
    if (!Array.isArray(s) || s.length === 0 || !s.every(Number.isInteger)) return null;
    picks[key] = s as number[];
  }
  return picks;
}

export const browserPicks: PicksStore = {
  load() {
    const saved: SavedPicks = {};
    try {
      const raw = globalThis.localStorage?.getItem(KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== "object") return saved;
      for (const [key, entry] of Object.entries(parsed)) {
        if (!entry || typeof entry !== "object" || !("patch" in entry) || typeof entry.patch !== "string") continue;
        const picks = "picks" in entry ? parsePicks(entry.picks) : null;
        if (picks) saved[key] = { patch: entry.patch, picks };
      }
    } catch {
      // unreadable or unavailable storage: no saved picks
    }
    return saved;
  },
  save(saved) {
    try {
      globalThis.localStorage?.setItem(KEY, JSON.stringify(saved));
    } catch {
      // the picks still apply for this run
    }
  },
};
