// The Backend port (docs/architecture.md, section 5): the only way the UI reaches the core.
// Command ids, params, results and errors are generated from the core's registry
// (`commands.ts`, ADR-053); this file names them for the UI and adds generic forms of the
// option types, which the generated per-type copies must match.

import type * as Core from "./commands.ts";

export type Commands = Core.Commands;
export type Role = Core.Role;
export type ErrorCode = Core.ErrorCode;
export type CommandError = Core.CommandError;
export type Result<T> = { ok: true; value: T } | { ok: false; error: CommandError };

export type ChampSelect = Core.ChampSelect;
export type ChampSelectState = Core.ChampSelectState;
export type Page = Core.Page;
export type Confidence = Core.Confidence;
export type Alternatives = Core.Alternatives;
export type Plan = Core.Plan;
export type Outcome = Core.Outcome;
export type Imported = Core.Imported;
export type BuildGetParams = Core.BuildGetParams;
export type PlanParams = Core.PlanParams;
export type ImportParams = Core.ImportParams;
export type DataStatus = Core.DataStatus;
export type GameNames = Core.GameNames;
export type IconParams = Core.IconsParams;
export type GameIcons = Core.Icons;
export type Backup = Core.Backup;
export type Restored = Core.Restored;
export type Build = Commands["build.get"]["result"];

/** What a name or icon is of (the rest of `GameNames` is the rune trees' layout). */
export type GameKind = Exclude<keyof GameNames, "rune_trees" | "shard_rows">;

type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

/** Why a choice was made (ADR-043). */
export type Label = DistributiveOmit<Core.PageChoice, "value">;
export type Choice<T> = { value: T } & Label;
/** One option of a slot, as `build.plan` ranks it. */
export type Row<T> = Omit<Core.PageRow, "value"> & { value: T };
/** Every option of a slot, most played first; the player can pick any of them. */
export type Ranked<T> = Omit<Core.PageRanked, "rows"> & { rows: Row<T>[] };

// The generic forms say the same as each generated copy, in both directions.
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
const same = <T extends true>(): T | undefined => undefined;
same<Same<Choice<number>, DistributiveOmit<Core.SlotChoice, "slot">>>();
same<Same<Choice<[number, number]>, Core.TupleOfInt64AndInt64Choice>>();
same<Same<Row<number>, Core.Int64Row>>();
same<Same<Row<[number, number]>, Core.TupleOfInt64AndInt64Row>>();
same<Same<Ranked<number>, Omit<Core.SlotRanked, "slot">>>();
same<Same<Ranked<[number, number]>, Core.TupleOfInt64AndInt64Ranked>>();

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
