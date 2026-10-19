// What the player reads instead of the client's codes and ids: champion-select phases, roles,
// and rune, spell and item names from the client's game data (`names.get`). An id without a
// name (no client yet, or one it doesn't know) shows as the id.

import type { GameNames, Page, Role } from "../backend/backend.ts";

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

export type Kind = keyof GameNames;

/** The name of `id` in `kind`, or the id itself. */
export const name = (names: GameNames | null, kind: Kind, id: number): string =>
  names?.[kind][String(id)] ?? String(id);

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
