// The single app state (docs/architecture.md, section 5): a plain serializable object that
// tests, mocks and debugging tools can read. Only the functions below change it, through the
// Backend.

import type { Backend, ChampSelectState, CommandError, DataStatus, Imported, Plan } from "../backend/backend.ts";

export interface Settings {
  /** Import on lock-in without asking (ADR-043); off by default. */
  autoImport: boolean;
}

export interface AppState {
  data: DataStatus | null;
  champSelect: ChampSelectState | null;
  /** What an import would write for the champion picked or hovered, loaded as soon as known. */
  plan: { key: string; value: Plan } | null;
  /** The last import, and for which champion and role. */
  imported: { key: string; value: Imported } | null;
  settings: Settings;
  /** Why something can't be shown or done; cleared when things work again. */
  error: CommandError | null;
}

/** Where settings live between runs; any Storage, so tests can pass their own. */
export interface SettingsStore {
  load(): Settings | null;
  save(settings: Settings): void;
}

const KEY = "stronk.settings";

export const browserSettings: SettingsStore = {
  load() {
    try {
      const raw = globalThis.localStorage?.getItem(KEY);
      const parsed: unknown = raw ? JSON.parse(raw) : null;
      if (parsed && typeof parsed === "object" && "autoImport" in parsed) {
        return { autoImport: parsed.autoImport === true };
      }
    } catch {
      // unreadable or unavailable storage: defaults
    }
    return null;
  },
  save(settings) {
    try {
      globalThis.localStorage?.setItem(KEY, JSON.stringify(settings));
    } catch {
      // the setting still applies for this run
    }
  },
};

export function createApp(backend: Backend, store: SettingsStore = browserSettings) {
  const state = $state<AppState>({
    data: null,
    champSelect: null,
    plan: null,
    imported: null,
    settings: store.load() ?? { autoImport: false },
    error: null,
  });

  async function importBuild(): Promise<void> {
    const key = state.plan?.key;
    if (!key) return;
    const imported = await backend.run("build.import", {});
    if (imported.ok) {
      state.imported = { key, value: imported.value };
      state.error = null;
    } else {
      state.error = imported.error;
    }
  }

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
    const { champion, role, session } = select.value;
    if (champion === null || role === null) {
      state.error = null;
      return;
    }
    const key = `${champion}/${role}`;
    if (state.plan?.key !== key) {
      const plan = await backend.run("build.plan", { champion, role });
      if (!plan.ok) {
        state.plan = null;
        state.error = plan.error;
        return;
      }
      state.plan = { key, value: plan.value }; // hovered earlier: lock-in is a cache hit
      state.error = null;
    }
    if (session?.locked && state.settings.autoImport && state.imported?.key !== key) {
      await importBuild();
    }
  }

  function setAutoImport(on: boolean): void {
    state.settings = { ...state.settings, autoImport: on };
    store.save(state.settings);
  }

  return { state, refresh, importBuild, setAutoImport };
}

export type App = ReturnType<typeof createApp>;
