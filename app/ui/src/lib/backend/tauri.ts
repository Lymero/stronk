// TauriBackend: the desktop app's adapter for the Backend port. Every command goes through the
// shell's single `run` IPC command into the core's registry (app/core/src-tauri).

import { invoke } from "@tauri-apps/api/core";
import type { Backend, CommandError, CommandId, Commands, Result } from "./backend.ts";

const isCommandError = (e: unknown): e is CommandError =>
  typeof e === "object" && e !== null && "code" in e && "message" in e;

export class TauriBackend implements Backend {
  async run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>> {
    try {
      const value = await invoke<Commands[K]["result"]>("run", { id, params });
      return { ok: true, value };
    } catch (e) {
      const error: CommandError = isCommandError(e) ? e : { code: "internal", message: String(e) };
      return { ok: false, error };
    }
  }
}

/** True inside the Tauri webview. */
export const inTauri = (): boolean => "__TAURI_INTERNALS__" in window;
