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
  const { runes, spells, items } = plan.alternatives;
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
    items: items.map((s) => {
      const pick = picks.items[s.slot];
      return { slot: s.slot, ...slot(s, String, pick === undefined ? null : (item) => item === pick) };
    }),
  };
}

/** A win impact in wins per 100 games (percentage points of win probability), "+2.1" (ADR-060). */
export const wins = (v: number): string => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}`;

/** Half an interval's width in wins per 100 games. */
export const spread = (ci: [number, number]): number => Math.abs(ci[1] - ci[0]) * 50;

/** A share of games as a whole percentage. */
export const share = (v: number): string => `${Math.round(v * 100)}%`;

/** True when every choice is the most played one: nothing beat it clearly. */
export const allPopular = (plan: Plan): boolean =>
  [plan.runes, plan.spells, ...plan.items].every((c: Choice<unknown> | null) => c === null || c.label === "popular");

/** The option the others are compared with: the slot's most played. */
export const mostPlayed = <T>(slot: Slot<T>): Shown<T> | undefined =>
  slot.rows.find((r) => r.confidence === "most_played") ?? slot.rows[0];

/** What the import writes for a slot: the player's pick, else Stronk's choice. */
export const selected = <T>(slot: Slot<T>): Shown<T> | undefined => slot.rows.find((r) => r.selected);

/** An option's win impact, "+0.4 wins per 100", ending "vs others" when it isn't compared with
 * the most played option; null without an estimate. Its uncertainty is in `explain`, shown on
 * hover (ADR-060). */
export function figure(row: Row<unknown>): string | null {
  if (row.wpa === null) return null;
  return `${wins(row.wpa)} wins per 100${row.versus === "alternatives" ? " vs others" : ""}`;
}

/** Why an option's number reads as it does: what it's measured against, its interval, and
 * whether the difference is clear. */
export function explain(row: Row<unknown>): string {
  if (row.wpa === null)
    return row.confidence === "too_few_games"
      ? "Too few comparable games to estimate its win impact"
      : "No win impact is estimated for this yet";
  const against =
    row.versus === "most_played" ? "against the most played option" : "against the other options at this point";
  const interval = row.ci ? ` Likely between ${wins(row.ci[0])} and ${wins(row.ci[1])} (95%).` : "";
  const reading =
    row.confidence === "clearly_better"
      ? "Clearly better: the difference holds once false discoveries are controlled."
      : row.confidence === "clearly_worse"
        ? "Clearly worse: the difference holds once false discoveries are controlled."
        : row.confidence === "too_few_games"
          ? "Too few comparable games for this number to mean much."
          : row.confidence === "most_played"
            ? "The most played option, which the others are compared with."
            : "No clear difference: the interval is too wide to tell it apart from the most played option.";
  return `${wins(row.wpa)} wins per 100 games ${against}.${interval} ${reading}`;
}

/** A clear result as the player reads it, "▲ +2.1 wins per 100"; nothing for the rest (ADR-056). */
export function verdict(row: Row<unknown>): { text: string; tone: "positive" | "negative" } | null {
  if (row.wpa === null) return null;
  if (row.confidence === "clearly_better") return { text: `▲ ${figure(row)}`, tone: "positive" };
  if (row.confidence === "clearly_worse") return { text: `▼ ${figure(row)}`, tone: "negative" };
  return null;
}

/** What Stronk imports instead of the most played option: each clearly better choice with the
 * option it beats (ADR-060). */
export interface Change<T> {
  part: "runes" | "spells" | number;
  row: Shown<T>;
  base: Shown<T> | undefined;
}

export function changes(options: Options): Change<unknown>[] {
  const of = <T>(part: Change<T>["part"], slot: Slot<T>): Change<unknown>[] => {
    const row = slot.rows.find((r) => r.chosen);
    return row && row.confidence === "clearly_better"
      ? [{ part, row, base: mostPlayed(slot) } as Change<unknown>]
      : [];
  };
  return [
    ...of("runes", options.runes),
    ...of("spells", options.spells),
    ...options.items.flatMap((s) => of(s.slot, s)),
  ];
}

/** An option's reading laid out for its tooltip (ADR-060): the estimate, what it's against, its
 * likely range, the verdict in words, and the games behind it. */
export interface Details {
  value: string | null;
  against: string | null;
  range: string | null;
  verdict: { text: string; tone: "positive" | "negative" | "muted" };
  games: string;
}

export function details(row: Row<unknown>): Details {
  const has = row.wpa !== null;
  const tone = row.confidence === "clearly_better" ? "positive" : row.confidence === "clearly_worse" ? "negative" : "muted";
  const text = {
    clearly_better: "Clearly better",
    clearly_worse: "Clearly worse",
    most_played: "The most played option, the one the others are measured against",
    no_clear_difference: "No clear difference from the most played option",
    too_few_games: "Too few games to tell",
    not_estimated: "Not estimated yet",
  }[row.confidence];
  return {
    value: has ? `${wins(row.wpa ?? 0)} wins per 100 games` : null,
    against: has ? (row.versus === "most_played" ? "against the most played option" : "against the other options") : null,
    range: has && row.ci ? `Likely between ${wins(row.ci[0])} and ${wins(row.ci[1])}` : null,
    verdict: { text: has || row.confidence === "too_few_games" ? text : "Not estimated yet", tone: has ? tone : "muted" },
    games: `${row.played.toLocaleString("en-US")} games, ${share(row.share)} of this choice`,
  };
}
