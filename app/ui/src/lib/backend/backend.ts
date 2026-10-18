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
export type Label = { label: "popular" } | { label: "clearly_better"; wpa: number };
export type Choice<T> = { value: T } & Label;

export interface Page {
  primary_style: number;
  sub_style: number;
  perks: number[];
}

/** What an import would write (`build.plan`). */
export interface Plan {
  champion: string;
  role: Role;
  patch: string;
  runes: Choice<Page> | null;
  spells: Choice<[number, number]> | null;
  items: ({ slot: number } & Choice<number>)[];
}

export type Outcome = ({ status: "imported"; name: string } & Label) | { status: "skipped"; reason: string };

/** What an import wrote (`build.import`). */
export interface Imported {
  champion: string;
  role: Role;
  runes: Outcome;
  item_set: Outcome;
  spells: Outcome;
}

export type PlanParams = BuildGetParams;

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

export interface BuildGetParams {
  champion: string;
  role: Role;
  patch?: string;
  region?: string;
  elo?: string;
}

export interface Commands {
  "build.get": { params: BuildGetParams; result: Build };
  "build.import": { params: Record<string, never>; result: Imported };
  "build.plan": { params: PlanParams; result: Plan };
  "champselect.state": { params: Record<string, never>; result: ChampSelectState };
  "data.status": { params: Record<string, never>; result: DataStatus };
}

export type CommandId = keyof Commands;

export interface Backend {
  run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>>;
}

export const ok = <T>(value: T): Result<T> => ({ ok: true, value });
export const err = <T>(code: ErrorCode, message: string): Result<T> => ({
  ok: false,
  error: { code, message },
});
