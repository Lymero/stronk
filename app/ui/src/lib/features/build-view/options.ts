// The alternatives behind each import choice, from the published build file (`build.get`):
// per slot, the most played options with their share of games, win impact and how far the
// numbers can be trusted (docs/wpa-method.md, section 7). Pure, so the rules are tested here
// and the view only draws them.

import type { Build, Choice, Page, Plan } from "../../backend/backend.ts";

/** How far an option's numbers can be trusted, shown next to it. */
export type Confidence =
  /** Beats the most played option head to head, false discoveries controlled (q ≤ 0.05). */
  | "clearly_better"
  /** Loses to the most played option head to head, false discoveries controlled. */
  | "clearly_worse"
  /** The most played option: what the others are compared with. */
  | "most_played"
  /** Has a number, but isn't distinguishable from the most played option. */
  | "no_clear_difference"
  /** `low_sample` or `low_overlap`: too few comparable games for a number to mean much. */
  | "too_few_games"
  /** No estimate is published for it (spells have none yet). */
  | "not_estimated";

export interface Row<T> {
  key: string;
  value: T;
  /** Games (or picks) with this option. */
  played: number;
  /** Its share of the slot's games, 0 to 1. */
  share: number;
  /** Win probability added: against the most played option when compared with it, else
   * against the alternatives at this decision point. */
  wpa: number | null;
  ci: [number, number] | null;
  versus: "most_played" | "alternatives";
  confidence: Confidence;
  /** A modest hidden confounder could overturn the result. */
  fragile: boolean;
  /** What the import writes. */
  chosen: boolean;
}

export interface Slot<T> {
  rows: Row<T>[];
  /** Options not shown. */
  more: number;
}

/** Options shown per slot: the most played, plus the chosen one when it is not among them. */
export const SHOWN = 3;
const CLEAR_Q = 0.05;

interface Option<T> {
  key: string;
  value: T;
  /** Its id in comparisons: keystone for rune pages, item id for items. */
  id: number;
  played: number;
  wpa: number | null;
  ci: [number, number] | null;
  flags: string[];
  comparison?: { versus: number; wpa: number; q: number; ci?: [number, number] } | undefined;
}

function slot<T>(options: Option<T>[], chosen: (value: T) => boolean): Slot<T> {
  if (options.length === 0) return { rows: [], more: 0 };
  const sorted = [...options].sort((a, b) => b.played - a.played || a.id - b.id);
  const popular = sorted[0] as Option<T>;
  const total = sorted.reduce((sum, o) => sum + o.played, 0);
  const rows = sorted.map((o): Row<T> => {
    const compared = o.comparison && o.comparison.versus === popular.id && o !== popular ? o.comparison : undefined;
    return {
      key: o.key,
      value: o.value,
      played: o.played,
      share: total > 0 ? o.played / total : 0,
      wpa: compared ? compared.wpa : o.wpa,
      ci: compared ? (compared.ci ?? null) : o.ci,
      versus: compared ? "most_played" : "alternatives",
      confidence: confidence(o, o === popular, compared),
      fragile: o.flags.includes("fragile"),
      chosen: chosen(o.value),
    };
  });
  const shown = rows.slice(0, SHOWN);
  const pick = rows.find((r) => r.chosen);
  if (pick && !shown.includes(pick)) shown.push(pick);
  return { rows: shown, more: rows.length - shown.length };
}

function confidence<T>(o: Option<T>, popular: boolean, compared: Option<T>["comparison"]): Confidence {
  if (o.flags.includes("low_sample") || o.flags.includes("low_overlap")) return "too_few_games";
  if (compared && compared.q <= CLEAR_Q && !o.flags.includes("no_clear_difference")) {
    return compared.wpa > 0 ? "clearly_better" : "clearly_worse";
  }
  if (popular) return "most_played";
  return o.wpa === null ? "not_estimated" : "no_clear_difference";
}

const samePage = (a: Page, b: Page) =>
  a.primary_style === b.primary_style && a.sub_style === b.sub_style && a.perks.join() === b.perks.join();
const samePair = (a: readonly number[], b: readonly number[]) => [...a].sort().join() === [...b].sort().join();

export interface Alternatives {
  runes: Slot<Page>;
  spells: Slot<[number, number]>;
  items: ({ slot: number } & Slot<number>)[];
}

/** Each slot's alternatives, the plan's choices marked. */
export function alternatives(build: Build, plan: Plan): Alternatives {
  const chosenPage = plan.runes?.value;
  const chosenPair = plan.spells?.value;
  const runes = slot(
    build.runes.map((o) => ({
      key: `${o.page.primaryStyle}/${o.page.subStyle}/${o.page.perks.join(",")}`,
      value: { primary_style: o.page.primaryStyle, sub_style: o.page.subStyle, perks: [...o.page.perks] },
      id: o.page.perks[0],
      played: o.games ?? o.n,
      wpa: o.wpa,
      ci: o.ci,
      flags: o.flags,
      comparison: o.comparison,
    })),
    (page) => chosenPage !== undefined && samePage(chosenPage, page),
  );
  const spells = slot(
    build.spells.map((o) => {
      const [d, f] = o.spells;
      return {
        key: [d, f].sort().join(","),
        value: [d, f] as [number, number],
        id: Math.min(d, f) * 1000 + Math.max(d, f),
        played: o.games ?? o.n,
        wpa: o.wpa,
        ci: o.ci,
        flags: o.flags,
      };
    }),
    (pair) => chosenPair !== undefined && samePair(pair, chosenPair),
  );
  const slots = [...new Set(build.items.map((o) => o.slot))].sort((a, b) => a - b);
  const items = slots.map((n) => {
    const chosen = plan.items.find((i) => i.slot === n)?.value;
    return {
      slot: n,
      ...slot(
        build.items
          .filter((o) => o.slot === n)
          .map((o) => ({
            key: String(o.item),
            value: o.item,
            id: o.item,
            played: o.picks ?? o.n,
            wpa: o.wpa,
            ci: o.ci,
            flags: o.flags,
            comparison: o.comparison,
          })),
        (item) => item === chosen,
      ),
    };
  });
  return { runes, spells, items };
}

/** True when every choice is the most played one: nothing beat it clearly. */
export const allPopular = (plan: Plan): boolean =>
  [plan.runes, plan.spells, ...plan.items].every((c: Choice<unknown> | null) => c === null || c.label === "popular");
