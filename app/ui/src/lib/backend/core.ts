// CoreBackend: the UI in a plain browser against the real core (ADR-048). Each command goes to
// tools/lcu_mock/core_bridge.py through the dev server's `/core` proxy, which runs `stronk-core`
// against lcu-mock and the signed fixture data. Used by the Playwright tests (`just e2e`) and
// `?backend=core`; the desktop app uses TauriBackend.

import type { Backend, CommandError, CommandId, Commands, Result } from "./backend.ts";

export class CoreBackend implements Backend {
  constructor(readonly base = "/core") {}

  async run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>> {
    try {
      const response = await fetch(`${this.base}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, params }),
      });
      if (!response.ok) throw new Error(`core bridge: HTTP ${response.status}`);
      return (await response.json()) as Result<Commands[K]["result"]>;
    } catch (e) {
      const error: CommandError = { code: "unavailable", message: String(e) };
      return { ok: false, error };
    }
  }
}
