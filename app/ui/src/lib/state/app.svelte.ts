// The single app state (docs/architecture.md, section 5): a plain serializable object that
// tests, mocks and debugging tools can read. Only the functions below change it, through the
// Backend.

import type {
  Backend,
  Backup,
  Build,
  ChampSelectState,
  CommandError,
  DataStatus,
  GameNames,
  Imported,
  ImportParams,
  Plan,
  Restored,
} from "../backend/backend.ts";
import { noPicks, type Pick, type Picks, samePage, samePair } from "./picks.ts";

export interface Settings {
  /** Import on lock-in without asking (ADR-043); off by default. */
  autoImport: boolean;
}

export interface AppState {
  data: DataStatus | null;
  champSelect: ChampSelectState | null;
  /** Names for the ids on screen, from the client; ids show until they load. */
  names: GameNames | null;
  /** What an import would write for the champion picked or hovered, loaded as soon as known. */
  plan: { key: string; value: Plan } | null;
  /** The published build file behind the plan: every option, for the alternatives; null
   * value when it couldn't be read (asked once per champion and role). */
  build: { key: string; value: Build | null } | null;
  /** The player's picks instead of Stronk's choices, for one champion and role (ADR-050). */
  picks: { key: string; value: Picks } | null;
  /** The last import, for which champion and role, and with which picks. */
  imported: { key: string; value: Imported; picks: Picks } | null;
  settings: Settings;
  /** Item set backups in settings: listed when settings open, and the last restore. */
  restore: { backups: Backup[] | null; done: Restored | null; error: CommandError | null };
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
    names: null,
    plan: null,
    build: null,
    picks: null,
    imported: null,
    settings: store.load() ?? { autoImport: false },
    restore: { backups: null, done: null, error: null },
    error: null,
  });

  async function importBuild(): Promise<void> {
    const key = state.plan?.key;
    if (!key) return;
    const picks = currentPicks();
    const params: ImportParams = {
      ...(picks.runes ? { runes: picks.runes } : {}),
      ...(picks.spells ? { spells: picks.spells } : {}),
      ...(Object.keys(picks.items).length
        ? { items: Object.entries(picks.items).map(([slot, item]) => ({ slot: Number(slot), item })) }
        : {}),
    };
    const imported = await backend.run("build.import", params);
    if (imported.ok) {
      state.imported = { key, value: imported.value, picks };
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
    if (state.names === null && select.value.session) {
      // Cosmetic: without names the ids show, so a failure is not an error to report.
      const names = await backend.run("names.get", {});
      if (names.ok) state.names = names.value;
    }
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
    if (state.build?.key !== key) {
      // After any import, so lock-in doesn't wait for it. The alternatives only add to the
      // plan: without them it still shows and imports.
      const build = await backend.run("build.get", { champion, role });
      state.build = { key, value: build.ok ? build.value : null };
    }
  }

  /** The picks for the champion and role on screen; none for any other. */
  function currentPicks(): Picks {
    return state.picks && state.picks.key === state.plan?.key ? state.picks.value : noPicks();
  }

  /** Picks an option for a slot; picking Stronk's choice again drops the pick. */
  function pick(choice: Pick): void {
    const plan = state.plan;
    if (!plan) return;
    const picks: Picks = { ...currentPicks(), items: { ...currentPicks().items } };
    if ("runes" in choice) {
      const stronk = plan.value.runes?.value;
      picks.runes = stronk && samePage(stronk, choice.runes) ? undefined : choice.runes;
    } else if ("spells" in choice) {
      const stronk = plan.value.spells?.value;
      picks.spells = stronk && samePair(stronk, choice.spells) ? undefined : choice.spells;
    } else {
      const stronk = plan.value.items.find((i) => i.slot === choice.slot)?.value;
      if (stronk === choice.item) delete picks.items[choice.slot];
      else picks.items[choice.slot] = choice.item;
    }
    state.picks = { key: plan.key, value: picks };
  }

  /** Back to Stronk's choices everywhere. */
  function resetPicks(): void {
    state.picks = null;
  }

  function setAutoImport(on: boolean): void {
    state.settings = { ...state.settings, autoImport: on };
    store.save(state.settings);
  }

  async function loadBackups(): Promise<void> {
    const listed = await backend.run("item_sets.backups", {});
    state.restore = listed.ok
      ? { ...state.restore, backups: listed.value.backups, error: null }
      : { ...state.restore, backups: null, error: listed.error };
  }

  /** Puts a backup of the player's item sets back; the core backs up the current ones first. */
  async function restoreItemSets(location: string): Promise<void> {
    const restored = await backend.run("item_sets.restore", { backup: location });
    state.restore = restored.ok
      ? { ...state.restore, done: restored.value, error: null }
      : { ...state.restore, done: null, error: restored.error };
    if (restored.ok) await loadBackups(); // the replaced sets are now the newest backup
  }

  return { state, refresh, importBuild, pick, resetPicks, setAutoImport, loadBackups, restoreItemSets };
}

export type App = ReturnType<typeof createApp>;
