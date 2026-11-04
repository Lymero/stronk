// What the player reads instead of the client's codes and ids: champion-select phases, roles,
// and rune, spell and item names from the client's game data (`names.get`). An id without a
// name (no client yet, or one it doesn't know) shows as the id. Icons (`icons.get`) are looked
// up the same way; without one, a stand-in shows.

import type { GameNames, IconKind, Page, Role } from "../backend/backend.ts";

const PHASES: Record<string, string> = {
  PLANNING: "Declaring picks",
  BAN_PICK: "Bans and picks",
  FINALIZATION: "Final changes",
  GAME_STARTING: "Game starting",
};

/** The client's timer phase (`BAN_PICK`) as words; an unknown phase is spelled out. */
export function phase(code: string): string {
  const known = PHASES[code];
  if (known) return known;
  const words = code.toLowerCase().replaceAll("_", " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : "Champion select";
}

const ROLES: Record<Role, string> = {
  TOP: "Top",
  JUNGLE: "Jungle",
  MIDDLE: "Mid",
  BOTTOM: "Bot",
  UTILITY: "Support",
};

export const role = (r: Role): string => ROLES[r];

export type Kind = Exclude<keyof GameNames, "rune_trees" | "shard_rows">;

/** The name of `id` in `kind`, or the id itself. */
export const name = (names: GameNames | null, kind: Kind, id: number): string =>
  names?.[kind][String(id)] ?? String(id);

/** Icons by kind and id, as the app state keeps them (`null`: the client has none). */
export type Icons = Record<IconKind, Record<string, string | null>>;

/** The icon of `id` in `kind`, if loaded. */
export const icon = (icons: Icons | null, kind: IconKind, id: number): string | null =>
  icons?.[kind][String(id)] ?? null;


/** A rune page as three lines: the primary tree and its four runes, the secondary tree and
 * its two, then the three stat shards. */
export function runePage(names: GameNames | null, page: Page): { title: string; runes: string[] }[] {
  const runes = (ids: number[]) => ids.map((id) => name(names, "runes", id));
  return [
    { title: name(names, "rune_styles", page.primary_style), runes: runes(page.perks.slice(0, 4)) },
    { title: name(names, "rune_styles", page.sub_style), runes: runes(page.perks.slice(4, 6)) },
    { title: "Shards", runes: runes(page.perks.slice(6)) },
  ].filter((line) => line.runes.length > 0);
}

/** An elo bracket id (`master_plus`) as players say it. */
export function elo(id: string): string {
  const [tier = "", plus] = id.split("_");
  const word = tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : id;
  return plus === "plus" ? `${word}+` : id === "all" ? "All ranks" : word;
}

/** Why an option says "Changed in 16.22" (ADR-088). */
export const changedNote = (patch: string): string =>
  `Riot changed it in patch ${patch}: its numbers count games from ${patch} on, never older ones.`;

/** The patches a build's games come from: `Patch 16.22`, or `Patches 16.21–16.22` pooled
 * (ADR-088). */
export function patches(list: string[]): string {
  const [first, last] = [list[0], list[list.length - 1]];
  return list.length > 1 ? `Patches ${first}–${last}` : `Patch ${first ?? ""}`;
}

/** A region id (`euw1`, `all`) as players say it. */
export const region = (id: string): string => (id === "all" ? "All regions" : id.toUpperCase());

/** A count of games, `1 game` or `1,840 games`. */
export const games = (n: number): string => `${n.toLocaleString("en-US")} ${n === 1 ? "game" : "games"}`;

/** True when an error only means the League client isn't open yet: the app waits for it and
 * says so calmly instead of showing the error. */
export const clientMissing = (error: { code: string; message: string } | null): boolean =>
  error?.code === "unavailable" && /lockfile|League client/i.test(error.message);
