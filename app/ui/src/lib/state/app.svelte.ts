// The single app state (docs/architecture.md, section 5): a plain serializable object that
// tests, mocks and debugging tools can read. Only `refresh` changes it, through the Backend.

import type { Backend, Build, ChampSelectState, CommandError, DataStatus } from "../backend/backend.ts";

export interface AppState {
  data: DataStatus | null;
  champSelect: ChampSelectState | null;
  /** The build for the champion picked or hovered, loaded as soon as it is known. */
  build: { key: string; value: Build } | null;
  /** Why the build or the client can't be shown; cleared when things work again. */
  error: CommandError | null;
}

export function createApp(backend: Backend) {
  const state = $state<AppState>({ data: null, champSelect: null, build: null, error: null });

  async function refresh(): Promise<void> {
    if (state.data === null) {
      const data = await backend.run("data.status", {});
      if (!data.ok) {
        state.error = data.error;
        return;
      }
      state.data = data.value;
    }
    const select = await backend.run("champselect.state", {});
    if (!select.ok) {
      state.champSelect = null;
      state.error = select.error;
      return;
    }
    state.champSelect = select.value;
    const { champion, role } = select.value;
    if (champion === null || role === null) {
      state.error = null;
      return;
    }
    const key = `${champion}/${role}`;
    if (state.build?.key === key) return; // hovered earlier: lock-in is a cache hit
    const build = await backend.run("build.get", { champion, role });
    if (build.ok) {
      state.build = { key, value: build.value };
      state.error = null;
    } else {
      state.build = null;
      state.error = build.error;
    }
  }

  return { state, refresh };
}

export type App = ReturnType<typeof createApp>;
