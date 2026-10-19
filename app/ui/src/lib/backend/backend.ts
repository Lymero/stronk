// The Backend port (docs/architecture.md, section 5): the only way the UI reaches the core.
// Command ids, params and results mirror app/core/crates/service; TauriBackend will use the
// bindings tauri-specta generates from them.

import type { BuildV1 } from "@stronk/contracts";

export type Role = BuildV1.Role;
export type Build = BuildV1.Build;

export type ErrorCode =
  | "unknown_command"
  | "invalid_params"
  | "not_found"
  | "invalid_data"
  | "unavailable"
  | "unsupported"
  | "internal";

export interface CommandError {
  code: ErrorCode;
  message: string;
}

export type Result<T> = { ok: true; value: T } | { ok: false; error: CommandError };

export interface ChampSelect {
  champion_id: number;
  locked: boolean;
  role: Role | null;
  phase: string;
  /** The player's spells now, D then F. */
  spells: [number, number] | null;
}

/** Why a choice was made (ADR-043). */
export type Label =
  | { label: "popular" }
  | {
      label: "clearly_better";
      /** Win probability added against the most played option. */
      wpa: number;
      /** Its 95% interval, when published. */
      ci: [number, number] | null;
      /** Games (or picks) with this option. */
      games: number;
    }
  /** The player picked this published option instead of Stronk's choice (ADR-050). */
  | { label: "picked" };
export type Choice<T> = { value: T } & Label;

export interface Page {
  primary_style: number;
  sub_style: number;
  perks: number[];
}

/** How far an option's numbers can be trusted (docs/wpa-method.md, section 7); decided in the
 * core by the rule that picks what to import (ADR-043, ADR-049). */
export type Confidence =
  /** Beats the most played option head to head; the published flags make it clear. */
  | "clearly_better"
  /** Loses to the most played option head to head, by the same rule. */
  | "clearly_worse"
  /** The most played option: what the others are compared with. */
  | "most_played"
  /** Has a number, but isn't distinguishable from the most played option. */
  | "no_clear_difference"
  /** `low_sample` or `low_overlap`: too few comparable games for a number to mean much. */
  | "too_few_games"
  /** No estimate is published for it (spells have none yet). */
  | "not_estimated";

/** One option of a slot, as `build.plan` ranks it. */
export interface Row<T> {
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
  /** Stronk's choice. */
  chosen: boolean;
  /** On the short list: one of the three most played, or Stronk's choice (ADR-051). */
  listed: boolean;
}

/** Every option of a slot, most played first; the player can pick any of them. */
export interface Ranked<T> {
  rows: Row<T>[];
  /** Options played less, off the short list. */
  more: number;
}

export interface Alternatives {
  runes: Ranked<Page>;
  spells: Ranked<[number, number]>;
  items: ({ slot: number } & Ranked<number>)[];
}

/** What an import would write (`build.plan`), and each slot's alternatives. */
export interface Plan {
  champion: string;
  role: Role;
  patch: string;
  /** Games behind the build file, and its elo bracket and region. */
  games: number;
  elo: string;
  region: string;
  runes: Choice<Page> | null;
  spells: Choice<[number, number]> | null;
  items: ({ slot: number } & Choice<number>)[];
  alternatives: Alternatives;
}

export type Outcome = ({ status: "imported"; name: string } & Label) | { status: "skipped"; reason: string };

/** What an import wrote (`build.import`). */
export interface Imported {
  champion: string;
  role: Role;
  runes: Outcome;
  item_set: Outcome;
  /** Where the player's item sets were saved before Stronk wrote its own. */
  item_set_backup: string | null;
  spells: Outcome;
}

export type PlanParams = BuildGetParams;

/** The player's picks for `build.import`, each a published option; Stronk's choice elsewhere. */
export interface ImportParams {
  runes?: Page;
  /** The pair in any order; Flash still goes on the player's key. */
  spells?: [number, number];
  items?: { slot: number; item: number }[];
}

export interface ChampSelectState {
  session: ChampSelect | null;
  champion: string | null;
  role: Role | null;
}

export interface DataStatus {
  patch: string;
  run_id: string;
  key_id: string;
  files: number;
}

/** Display names by id (as a string), from the League client's game data (`names.get`). */
export interface GameNames {
  champions: Record<string, string>;
  rune_styles: Record<string, string>;
  runes: Record<string, string>;
  spells: Record<string, string>;
  items: Record<string, string>;
}

/** A local backup of the player's item sets (`item_sets.backups`). */
export interface Backup {
  location: string;
  /** When it was saved, ms since the Unix epoch, when known. */
  saved_at_ms: number | null;
}

/** What `item_sets.restore` put back. */
export interface Restored {
  restored: string;
  /** Item sets in the restored document. */
  sets: number;
  /** Where the sets it replaced were saved first. */
  previous_backup: string;
}

export interface BuildGetParams {
  champion: string;
  role: Role;
  patch?: string;
  region?: string;
  elo?: string;
}

export interface Commands {
  "build.get": { params: BuildGetParams; result: Build };
  "build.import": { params: ImportParams; result: Imported };
  "build.plan": { params: PlanParams; result: Plan };
  "champselect.state": { params: Record<string, never>; result: ChampSelectState };
  "data.status": { params: Record<string, never>; result: DataStatus };
  "item_sets.backups": { params: Record<string, never>; result: { backups: Backup[] } };
  "item_sets.restore": { params: { backup: string }; result: Restored };
  "names.get": { params: Record<string, never>; result: GameNames };
}

export type CommandId = keyof Commands;

export interface Backend {
  run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>>;
  /** Calls `onChange` when champion select may have changed (the core's websocket watcher,
   * ADR-044); returns the unsubscribe function. Backends without it are polled. */
  subscribe?(onChange: () => void): () => void;
}

export const ok = <T>(value: T): Result<T> => ({ ok: true, value });
export const err = <T>(code: ErrorCode, message: string): Result<T> => ({
  ok: false,
  error: { code, message },
});
