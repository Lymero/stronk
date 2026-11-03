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
  Part,
  Plan,
  Restored,
} from "../backend/backend.ts";
import {
  asItems,
  browserPicks,
  isEmpty,
  noPicks,
  type Pick,
  type Picks,
  type PicksStore,
  published,
  sameOrder,
  samePage,
  samePair,
} from "./picks.ts";

/** The elo bracket builds come from unless the player chooses another (ADR-078). */
export const DEFAULT_ELO = "master_plus";

export interface Settings {
  /** Write Stronk's item set on lock-in, and again until the game starts whenever it changes
   * (ADR-082); on by default: it adds a set and leaves the player's alone. */
  autoItemSet: boolean;
  /** Write the rune page and spells on lock-in too (ADR-043, ADR-082); off by default: they
   * replace what the player had chosen. */
  autoImport: boolean;
  /** The elo bracket the builds come from (ADR-078); a champion and role it has no build for
   * get Master+'s, and the plan says so. */
  elo: string;
}

const defaults: Settings = { autoItemSet: true, autoImport: false, elo: DEFAULT_ELO };

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
  /** The plan for `key` (champion/role), asked with these enemy picks (sorted ids, ADR-074) in
   * this elo bracket (ADR-078); the plan's own `elo` is where it came from. */
  plan: { key: string; value: Plan; enemies?: string; elo: string } | null;
  /** The player's picks instead of Stronk's choices, for one champion and role (ADR-050);
   * kept between runs until the patch changes (ADR-051). */
  picks: { key: string; value: Picks } | null;
  /** The last import, for which champion and role, with which picks, from which bracket, and
   * what its item set was written from (`itemSetOf`); parts an import didn't write keep the
   * outcome and picks of the one before. */
  imported: { key: string; value: Imported; picks: Picks; elo: string; itemSet: string | null } | null;
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
      if (parsed && typeof parsed === "object") {
        const saved = parsed as Partial<Record<keyof Settings, unknown>>;
        const elo = typeof saved.elo === "string" && /^[a-z_]{2,32}$/.test(saved.elo) ? saved.elo : DEFAULT_ELO;
        return { autoItemSet: saved.autoItemSet !== false, autoImport: saved.autoImport === true, elo };
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
    settings: { ...defaults, ...store.load() },
    restore: { backups: null, done: null, error: null },
    error: null,
  });

  /** Imports the plan with the player's picks: every part, or only `parts` (ADR-082). */
  async function importBuild(parts?: Part[]): Promise<void> {
    if (!state.plan) return;
    const { key } = state.plan;
    const { elo } = state.plan.value;
    const picks = currentPicks();
    const params: ImportParams = {
      ...(parts ? { parts } : {}),
      ...(elo !== DEFAULT_ELO ? { elo } : {}),
      ...(picks.runes ? { runes: picks.runes } : {}),
      ...(picks.spells ? { spells: picks.spells } : {}),
      ...(picks.sections.start ? { start: picks.sections.start } : {}),
      ...(picks.sections.components ? { components: picks.sections.components } : {}),
      ...(picks.sections.boots ? { boots: picks.sections.boots[0] } : {}),
      ...(picks.skills?.skill_levels ? { skill_levels: picks.skills.skill_levels } : {}),
      ...(picks.skills?.skill_max ? { skill_max: picks.skills.skill_max } : {}),
      ...(Object.keys(picks.items).length
        ? { items: Object.entries(picks.items).map(([slot, item]) => ({ slot: Number(slot), item })) }
        : {}),
    };
    const imported = await backend.run("build.import", params);
    if (imported.ok) {
      const asked = (part: Part) => !parts || parts.includes(part);
      const before = state.imported?.key === key ? state.imported : null;
      const value = { ...imported.value };
      const kept = { ...picks };
      if (before && !asked("runes")) [value.runes, kept.runes] = [before.value.runes, before.picks.runes];
      if (before && !asked("spells")) [value.spells, kept.spells] = [before.value.spells, before.picks.spells];
      if (before && !asked("item_set")) {
        [value.item_set, value.item_set_backup] = [before.value.item_set, before.value.item_set_backup];
        [kept.items, kept.sections, kept.skills] = [before.picks.items, before.picks.sections, before.picks.skills];
      }
      const itemSet = asked("item_set") ? itemSetOf() : (before?.itemSet ?? null);
      state.imported = { key, value, picks: kept, elo, itemSet };
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
      for (const id of [...plan.alternatives.boots.rows.map((r) => r.value), ...(plan.boots ? [plan.boots.value] : [])]) {
        ids.items.add(id);
      }
      // The starts' and first components' items (ADR-071, ADR-072).
      for (const key of ["start", "components"] as const) {
        for (const id of [...plan.alternatives[key].rows.flatMap((r) => r.value), ...(plan[key]?.value ?? [])]) {
          ids.items.add(id);
        }
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
    // Asked again as the enemies pick: boots follow their damage (ADR-074); and when the
    // player chooses another bracket (ADR-078).
    const enemies = session?.enemies ?? [];
    const seen = [...enemies].sort((a, b) => a - b).join(",");
    const elo = state.settings.elo;
    if (state.plan?.key !== key || (state.plan.enemies ?? "") !== seen || state.plan.elo !== elo) {
      const plan = await backend.run("build.plan", {
        champion,
        role,
        ...(elo !== DEFAULT_ELO ? { elo } : {}),
        ...(enemies.length ? { enemies } : {}),
      });
      if (!plan.ok) {
        state.plan = null;
        state.error = plan.error;
        return;
      }
      // Another bracket has other options: the saved picks are matched against them again.
      const fresh = state.plan?.key !== key || state.plan.elo !== elo;
      state.plan = { key, value: plan.value, enemies: seen, elo }; // hovered earlier: lock-in is a cache hit
      state.error = null;
      if (fresh) restorePicks(key, plan.value);
    }
    if (session?.locked) await autoImport(key);
  }

  /** On lock-in, the parts the player wants without asking; then, until the game starts, the
   * item set again whenever what it would write changes: boots follow the enemies' picks
   * (ADR-074), and the player's picks change (ADR-082). */
  async function autoImport(key: string): Promise<void> {
    const { autoItemSet, autoImport } = state.settings;
    if (state.imported?.key !== key) {
      const parts: Part[] = [...(autoItemSet ? (["item_set"] as const) : []), ...(autoImport ? (["runes", "spells"] as const) : [])];
      if (parts.length) await importBuild(parts.length === 3 ? undefined : parts);
    } else if (autoItemSet && state.imported.itemSet !== itemSetOf()) {
      await importBuild(["item_set"]);
    }
  }

  /** What the item set is written from: the plan's items and skill order (its first block
   * names it, ADR-085), and the player's picks of them. */
  function itemSetOf(): string | null {
    const plan = state.plan?.value;
    if (!plan) return null;
    const { items, sections, skills } = currentPicks();
    const { start, components, boots, skill_levels, skill_max } = plan;
    return JSON.stringify([plan.elo, plan.items, start, components, boots, skill_levels, skill_max, items, sections, skills ?? {}]);
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
    const current = currentPicks();
    const picks: Picks = { ...current, items: { ...current.items }, sections: { ...current.sections } };
    if ("runes" in choice) {
      const stronk = plan.value.runes?.value;
      picks.runes = stronk && samePage(stronk, choice.runes) ? undefined : choice.runes;
    } else if ("spells" in choice) {
      const stronk = plan.value.spells?.value;
      picks.spells = stronk && samePair(stronk, choice.spells) ? undefined : choice.spells;
    } else if ("section" in choice) {
      const stronk = plan.value[choice.section]?.value;
      if (stronk !== undefined && samePair(asItems(stronk), choice.items)) delete picks.sections[choice.section];
      else picks.sections[choice.section] = choice.items;
    } else if ("skills" in choice) {
      const stronk = plan.value[choice.skills]?.value;
      const skills = { ...picks.skills };
      if (stronk && sameOrder(stronk, choice.order)) delete skills[choice.skills];
      else skills[choice.skills] = choice.order;
      if (Object.keys(skills).length) picks.skills = skills;
      else delete picks.skills;
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

  function setAutoItemSet(on: boolean): void {
    state.settings = { ...state.settings, autoItemSet: on };
    store.save(state.settings);
  }

  /** Builds from another elo bracket (ADR-078): the plan on screen is asked again. */
  async function setElo(elo: string): Promise<void> {
    state.settings = { ...state.settings, elo };
    store.save(state.settings);
    await refresh();
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

  return { state, refresh, importBuild, pick, resetPicks, setAutoImport, setAutoItemSet, setElo, loadBackups, restoreItemSets };
}

export type App = ReturnType<typeof createApp>;
