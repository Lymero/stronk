// The player's picks instead of Stronk's choices (ADR-050): part of the single app state, and
// the equality rules that tell a pick from Stronk's choice.

import type { Page } from "../backend/backend.ts";

/** The player's picks for one champion and role; a slot without one keeps Stronk's choice. */
export interface Picks {
  runes?: Page | undefined;
  spells?: [number, number] | undefined;
  /** Item id by slot. */
  items: Record<number, number>;
}

/** A pick for one slot; picking Stronk's choice again drops it. */
export type Pick = { runes: Page } | { spells: [number, number] } | { slot: number; item: number };

export const noPicks = (): Picks => ({ items: {} });

export const samePage = (a: Page, b: Page): boolean =>
  a.primary_style === b.primary_style && a.sub_style === b.sub_style && a.perks.join() === b.perks.join();

/** The same two spells, whichever key each is on. */
export const samePair = (a: readonly number[], b: readonly number[]): boolean =>
  [...a].sort().join() === [...b].sort().join();
