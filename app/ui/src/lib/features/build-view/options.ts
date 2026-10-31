// The alternatives behind each import choice, as `build.plan` ranks them (ADR-049): the core
// decides the order and the confidence by the same rule that picks what to import; here they
// only get a key, the player's pick and their wording. Every option comes back; the view lists
// the core's short list and the player's pick, and the rest on request (ADR-051).

import type { Choice, Page, Plan, Ranked, Row } from "../../backend/backend.ts";
import { noPicks, type Picks, samePage, samePair } from "../../state/picks.ts";

export interface Shown<T> extends Row<T> {
  key: string;
  /** What the import writes: the player's pick, else Stronk's choice. */
  selected: boolean;
  /** Listed before the player asks for every option: on the core's short list, or picked. */
  shown: boolean;
}

export interface Slot<T> {
  /** Every option, most played first. */
  rows: Shown<T>[];
  /** Options listed only on request. */
  more: number;
}

export interface Options {
  runes: Slot<Page>;
  spells: Slot<[number, number]>;
  /** The starts (ADR-071) and first components (ADR-072): each its items, smallest id first. */
  start: Slot<number[]>;
  components: Slot<number[]>;
  /** The upgraded boots (ADR-073). */
  boots: Slot<number>;
  items: ({ slot: number } & Slot<number>)[];
}

function slot<T>(ranked: Ranked<T>, key: (value: T) => string, picked: ((value: T) => boolean) | null): Slot<T> {
  const rows = ranked.rows.map((r) => {
    const selected = picked ? picked(r.value) : r.chosen;
    return { ...r, key: key(r.value), selected, shown: r.listed || selected };
  });
  return { rows, more: rows.filter((r) => !r.shown).length };
}

/** The plan's alternatives with the player's picks marked. */
export function options(plan: Plan, picks: Picks = noPicks()): Options {
  const { runes, spells, start, components, boots, items } = plan.alternatives;
  return {
    runes: slot(
      runes,
      (p) => `${p.primary_style}/${p.sub_style}/${p.perks.join(",")}`,
      picks.runes ? (p) => samePage(picks.runes as Page, p) : null,
    ),
    spells: slot(
      spells,
      (pair) => [...pair].sort().join(","),
      picks.spells ? (pair) => samePair(pair, picks.spells as [number, number]) : null,
    ),
    start: slot(start, (items) => items.join(","), picks.start ? (items) => samePair(items, picks.start as number[]) : null),
    boots: slot(boots, String, picks.boots === undefined ? null : (item) => item === picks.boots),
    components: slot(
      components,
      (items) => items.join(","),
      picks.components ? (items) => samePair(items, picks.components as number[]) : null,
    ),
    items: items.map((s) => {
      const pick = picks.items[s.slot];
      return { slot: s.slot, ...slot(s, String, pick === undefined ? null : (item) => item === pick) };
    }),
  };
}

/** A win impact in wins per 100 games (percentage points of win probability), "+2.1" (ADR-060). */
export const wins = (v: number): string => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}`;

/** True when every choice is the most played one: nothing beat it clearly. */
export const allPopular = (plan: Plan): boolean =>
  [plan.runes, plan.spells, plan.start, plan.components, plan.boots, ...plan.items].every((c: Choice<unknown> | null) => c === null || c.label === "popular");

/** The option the others are compared with: the slot's most played. */
export const mostPlayed = <T>(slot: Slot<T>): Shown<T> | undefined =>
  slot.rows.find((r) => r.confidence === "most_played") ?? slot.rows[0];

/** What the import writes for a slot: the player's pick, else Stronk's choice. */
export const selected = <T>(slot: Slot<T>): Shown<T> | undefined => slot.rows.find((r) => r.selected);

/** An option's win impact against its slot's most played option, "+0.4 wins per 100"; null when
 * it isn't compared with it head to head (ADR-060). Every number on the board is on that one scale,
 * the most played option at 0, so a row can be read in order; a number against the other options
 * pooled is against a different mix for each option, and isn't shown. */
export function figure(row: Row<unknown>): string | null {
  if (row.wpa === null || row.versus !== "most_played") return null;
  return `${wins(row.wpa)} wins per 100`;
}

/** True when a slot has an option compared with its most played one: its numbers have a 0. */
export const compared = <T>(slot: Slot<T>): boolean => slot.rows.some((r) => figure(r) !== null);

/** Why an option's number reads as it does: what it's measured against, its interval, and
 * whether the difference is clear. */
export function explain(row: Row<unknown>): string {
  if (row.confidence === "most_played") return "Most played, the others are compared with it.";
  if (row.confidence === "almost_always") return "Almost always taken: there's nothing to compare it with.";
  if (row.confidence === "too_few_to_compare")
    return "Plenty of games, but too few in situations comparable with the other options' to compare.";
  if (row.wpa === null)
    return row.confidence === "too_few_games"
      ? "Too few comparable games to estimate its win impact"
      : "No win impact is estimated for this yet";
  const against =
    row.versus === "most_played" ? "against the most played option" : "against the other options at this point";
  const interval = row.ci ? ` Likely between ${wins(row.ci[0])} and ${wins(row.ci[1])} (95%).` : "";
  const reading =
    row.confidence === "best_bet"
      ? "Stronk's best bet: ahead of the most played option on the numbers so far, not yet clear once false discoveries are controlled."
      : row.confidence === "clearly_better"
      ? "Clearly better: the difference holds once false discoveries are controlled."
      : row.confidence === "clearly_worse"
        ? "Clearly worse: the difference holds once false discoveries are controlled."
        : row.confidence === "too_few_games"
          ? "Too few comparable games for this number to mean much."
          : "No clear difference: the interval is too wide to tell it apart from the most played option.";
  return `${wins(row.wpa)} wins per 100 games ${against}.${interval} ${reading}`;
}

/** A clear result as the player reads it, "▲ +2.1 wins per 100", or Stronk's best bet, "Best bet
 * +2.7 wins per 100" (ADR-065); nothing for the rest (ADR-056). */
export function verdict(row: Row<unknown>): { text: string; tone: "positive" | "negative" | "bet" } | null {
  const number = figure(row);
  if (number === null) return null;
  if (row.confidence === "best_bet") return { text: `Best bet ${number}`, tone: "bet" };
  if (row.confidence === "clearly_better") return { text: `▲ ${number}`, tone: "positive" };
  if (row.confidence === "clearly_worse") return { text: `▼ ${number}`, tone: "negative" };
  return null;
}

/** What Stronk imports instead of the most played option: each choice clearly better than it, or
 * Stronk's best bet against it, with the option it beats (ADR-060, ADR-065). A rune row's change
 * (`"rune"`) has the row's runes as its value. */
export interface Change<T> {
  part: "runes" | "rune" | "spells" | "start" | "components" | "boots" | number;
  row: Shown<T>;
  base: Shown<T> | undefined;
}

/** Stronk's choice differs from the most played one for one of these. */
const changed = (row: Row<unknown>) => row.confidence === "clearly_better" || row.confidence === "best_bet";

export function changes(options: Options, runeRows: Plan["alternatives"]["rune_rows"] = []): Change<unknown>[] {
  const of = <T>(part: Change<T>["part"], slot: Slot<T>): Change<unknown>[] => {
    const row = slot.rows.find((r) => r.chosen);
    return row && changed(row) ? [{ part, row, base: mostPlayed(slot) } as Change<unknown>] : [];
  };
  const shown = <T>(row: Row<T>): Shown<T> => ({ ...row, key: "", selected: row.chosen, shown: true });
  const rows = runeRows.flatMap((r) => {
    const row = r.rows.find((x) => x.chosen && changed(x));
    const base = r.rows.find((x) => x.confidence === "most_played");
    return row ? [{ part: "rune" as const, row: shown(row), base: base && shown(base) } as Change<unknown>] : [];
  });
  return [
    ...of("runes", options.runes),
    ...rows,
    ...of("spells", options.spells),
    ...of("start", options.start),
    ...of("components", options.components),
    ...of("boots", options.boots),
    ...options.items.flatMap((s) => of(s.slot, s)),
  ];
}
