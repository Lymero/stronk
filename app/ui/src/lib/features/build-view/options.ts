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

/** A win impact as a signed percentage, "+2.1%". */
export const percent = (v: number): string => `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(1)}%`;

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

/** An option's win impact with its uncertainty, "+0.4% ± 2.6", or "+0.4% ± 2.6 vs others" when
 * it isn't compared with the most played option; null without an estimate. */
export function figure(row: Row<unknown>): string | null {
  if (row.wpa === null) return null;
  const spread = row.ci ? ` ± ${(Math.abs(row.ci[1] - row.ci[0]) * 50).toFixed(1)}` : "";
  return `${percent(row.wpa)}${spread}${row.versus === "alternatives" ? " vs others" : ""}`;
}

/** Why an option's number reads as it does: what it's measured against, its interval, and
 * whether the difference is clear. */
export function explain(row: Row<unknown>): string {
  if (row.wpa === null) return "Too few comparable games to estimate its win impact";
  const against =
    row.versus === "most_played" ? "against the most played option" : "against the other options at this point";
  const interval = row.ci ? `, 95% interval ${percent(row.ci[0])} to ${percent(row.ci[1])}` : "";
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
  return `Win probability added ${against}: ${percent(row.wpa)}${interval}. ${reading}`;
}

/** A clear result as the player reads it, "▲ +2.1% ± 1.3"; nothing for the rest (ADR-056). */
export function verdict(row: Row<unknown>): { text: string; tone: "positive" | "negative" } | null {
  if (row.wpa === null) return null;
  if (row.confidence === "clearly_better") return { text: `▲ ${figure(row)}`, tone: "positive" };
  if (row.confidence === "clearly_worse") return { text: `▼ ${figure(row)}`, tone: "negative" };
  return null;
}

export interface RuneRowSlot {
  key: string;
  kind: "primary" | "secondary" | "shard";
  /** The tree for primary rows and secondary pairs, the row for primary rows and shards. */
  style: number | null;
  row: number | null;
  slot: Slot<number[]>;
}

const sameRunes = (a: number[], b: number[]) => a.length === b.length && a.every((v, i) => v === b[i]);

/** The rune rows of `page`, row by row (ADR-057): its primary tree's rows, its secondary tree's
 * pairs, then the shard rows; each choice in the page selected. Rows of other trees are left out. */
export function runeRows(plan: Plan, page: Page): RuneRowSlot[] {
  const inPage = (kind: string, row: number | null): number[] | null => {
    const at = (i: number) => page.perks[i];
    if (kind === "secondary") {
      const pair = [at(4), at(5)].filter((v): v is number => v !== undefined);
      return pair.length === 2 ? pair.sort((a, b) => a - b) : null;
    }
    const v = row === null ? undefined : at(kind === "shard" ? row + 5 : row);
    return v === undefined ? null : [v];
  };
  const order = { primary: 0, secondary: 1, shard: 2 } as const;
  return plan.alternatives.rune_rows
    .filter(
      (r) =>
        r.kind === "shard" ||
        (r.kind === "primary" && r.style === page.primary_style) ||
        (r.kind === "secondary" && r.style === page.sub_style),
    )
    .sort((a, b) => order[a.kind] - order[b.kind] || (a.row ?? 0) - (b.row ?? 0))
    .map((r) => {
      const mine = inPage(r.kind, r.row ?? null);
      const rows = r.rows.map((x) => {
        const selected = mine !== null && sameRunes(x.value, mine);
        return { ...x, key: x.value.join("+"), selected, shown: x.listed || selected };
      });
      return {
        key: `${r.kind}-${r.style ?? ""}-${r.row ?? ""}`,
        kind: r.kind,
        style: r.style ?? null,
        row: r.row ?? null,
        slot: { rows, more: rows.filter((x) => !x.shown).length },
      };
    });
}
