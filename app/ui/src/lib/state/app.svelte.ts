// The single app state (docs/architecture.md, section 5): a plain serializable object that
// tests, mocks and debugging tools can read. Only the functions below change it, through the
// Backend.

import type {
  Backend,
  Backup,
  ChampSelectState,
  CommandError,
  DataStatus,
  GameKind,
  GameNames,
  IconParams,
  Imported,
  ImportParams,
  Plan,
  Restored,
} from "../backend/backend.ts";
import {
  browserPicks,
  isEmpty,
  noPicks,
  type Pick,
  type Picks,
  type PicksStore,
  published,
  samePage,
  samePair,
} from "./picks.ts";

export interface Settings {
  /** Import on lock-in without asking (ADR-043); off by default. */
  autoImport: boolean;
}

export interface AppState {
  data: DataStatus | null;
  champSelect: ChampSelectState | null;
  /** Names for the ids on screen, from the client; ids show until they load. */
  names: GameNames | null;
  /** Icons for the ids on screen, as `data:` URLs from the client; `null` for an id the client
   * has none for. Stand-ins show until they load. */
  icons: Record<GameKind, Record<string, string | null>>;
  /** What an import would write for the champion picked or hovered, and each slot's
   * alternatives; loaded as soon as known. */
  plan: { key: string; value: Plan } | null;
  /** The player's picks instead of Stronk's choices, for one champion and role (ADR-050);
   * kept between runs until the patch changes (ADR-051). */
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

/** The most ids one `icons.get` takes. */
export const ICONS_PER_CALL = 200;

export function createApp(
  backend: Backend,
  store: SettingsStore = browserSettings,
  picksStore: PicksStore = browserPicks,
) {
  const state = $state<AppState>({
    data: null,
    champSelect: null,
    names: null,
    icons: { champions: {}, rune_styles: {}, runes: {}, spells: {}, items: {} },
    plan: null,
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
      ...(picks.start ? { start: picks.start } : {}),
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

  /** Every id on screen: the champion, and each option of the plan. */
  function shownIds(): Record<GameKind, number[]> {
    const ids: Record<GameKind, Set<number>> = {
      champions: new Set(),
      rune_styles: new Set(),
      runes: new Set(),
      spells: new Set(),
      items: new Set(),
    };
    const championId = state.champSelect?.session?.champion_id ?? 0;
    if (championId > 0) ids.champions.add(championId);
    const plan = state.plan?.value;
    if (plan) {
      const { runes, spells, items } = plan.alternatives;
      for (const page of [...runes.rows.map((r) => r.value), ...(plan.runes ? [plan.runes.value] : [])]) {
        ids.rune_styles.add(page.primary_style).add(page.sub_style);
        for (const perk of page.perks) ids.runes.add(perk);
      }
      // The rune rows, and every rune of the trees the client lays out (ADR-058).
      for (const r of plan.alternatives.rune_rows) for (const row of r.rows) for (const id of row.value) ids.runes.add(id);
      for (const [style, rows] of Object.entries(state.names?.rune_trees ?? {})) {
        ids.rune_styles.add(Number(style));
        for (const row of rows) for (const id of row) ids.runes.add(id);
      }
      for (const row of state.names?.shard_rows ?? []) for (const id of row) ids.runes.add(id);
      for (const pair of [...spells.rows.map((r) => r.value), ...(plan.spells ? [plan.spells.value] : [])]) {
        for (const spell of pair) ids.spells.add(spell);
      }
      for (const id of [...items.flatMap((s) => s.rows.map((r) => r.value)), ...plan.items.map((i) => i.value)]) {
        ids.items.add(id);
      }
      // The starts' items (ADR-071).
      for (const id of [...plan.alternatives.start.rows.flatMap((r) => r.value), ...(plan.start?.value ?? [])]) {
        ids.items.add(id);
      }
    }
    return Object.fromEntries(Object.entries(ids).map(([k, v]) => [k, [...v]])) as Record<GameKind, number[]>;
  }

  /** Fetches the icons of every option not asked for yet, at most `ICONS_PER_CALL` ids per
   * call. Cosmetic like names: on failure the stand-ins stay and the next refresh asks again. */
  async function loadIcons(): Promise<void> {
    const shown = shownIds();
    const missing = (Object.keys(shown) as GameKind[]).flatMap((kind) =>
      shown[kind].filter((id) => !(String(id) in state.icons[kind])).map((id) => [kind, id] as const),
    );
    for (let start = 0; start < missing.length; start += ICONS_PER_CALL) {
      const wanted: IconParams = {};
      for (const [kind, id] of missing.slice(start, start + ICONS_PER_CALL)) (wanted[kind] ??= []).push(id);
      const icons = await backend.run("icons.get", wanted);
      if (!icons.ok) return;
      for (const kind of Object.keys(wanted) as GameKind[]) {
        const known = { ...state.icons[kind] };
        for (const id of wanted[kind] ?? []) known[String(id)] = icons.value[kind][String(id)] ?? null;
        state.icons[kind] = known;
      }
    }
  }

  async function refresh(): Promise<void> {
    await refreshSelect();
    if (state.champSelect?.session) await loadIcons(); // after any auto-import: icons never delay it
  }

  async function refreshSelect(): Promise<void> {
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
      restorePicks(key, plan.value);
    }
    if (session?.locked && state.settings.autoImport && state.imported?.key !== key) {
      await importBuild();
    }
  }

  /** The picks for the champion and role on screen; none for any other. */
  function currentPicks(): Picks {
    return state.picks && state.picks.key === state.plan?.key ? state.picks.value : noPicks();
  }

  /** The picks saved for this champion and role on this patch, among the plan's options. */
  function restorePicks(key: string, plan: Plan): void {
    const saved = picksStore.load()[key];
    const picks = saved && saved.patch === plan.patch ? published(plan, saved.picks) : noPicks();
    state.picks = isEmpty(picks) ? null : { key, value: picks };
  }

  /** Saves this champion and role's picks; picks made on another patch are dropped. */
  function savePicks(key: string, plan: Plan, picks: Picks): void {
    const saved = Object.fromEntries(
      Object.entries(picksStore.load()).filter(([k, v]) => k !== key && v.patch === plan.patch),
    );
    if (!isEmpty(picks)) saved[key] = { patch: plan.patch, picks: $state.snapshot(picks) };
    picksStore.save(saved);
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
    } else if ("start" in choice) {
      const stronk = plan.value.start?.value;
      picks.start = stronk && samePair(stronk, choice.start) ? undefined : choice.start;
    } else {
      const stronk = plan.value.items.find((i) => i.slot === choice.slot)?.value;
      if (stronk === choice.item) delete picks.items[choice.slot];
      else picks.items[choice.slot] = choice.item;
    }
    state.picks = { key: plan.key, value: picks };
    savePicks(plan.key, plan.value, picks);
  }

  /** Back to Stronk's choices everywhere. */
  function resetPicks(): void {
    if (state.plan) savePicks(state.plan.key, state.plan.value, noPicks());
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
