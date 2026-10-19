// MockBackend: scripted scenarios in a plain browser (`just app-mock`) and in tests. The
// `ranked-jungle` scenario follows the same steps as tools/lcu_mock's session; its plans are
// what the core's `build.plan` gives for the signed fixture data (fixtures/data).

import {
  type Backend,
  type Backup,
  type Build,
  type ChampSelectState,
  type CommandError,
  type CommandId,
  type Commands,
  type DataStatus,
  err,
  type GameNames,
  type Imported,
  ok,
  type Outcome,
  type Plan,
  type Result,
} from "./backend.ts";

export interface Scenario {
  steps: (ChampSelectState | CommandError)[];
  plans: Record<string, Plan | CommandError>;
  /** The published build files behind the plans (`build.get`), for the alternatives. */
  builds?: Record<string, Build>;
  status: DataStatus | CommandError;
  /** The client's game data names; without them the UI shows ids. */
  names?: GameNames | CommandError;
  /** What importing the rune page does; imported by default. */
  runes?: Outcome;
  /** The item set backups on this machine, newest first; restoring one adds a backup. */
  backups?: Backup[];
}

const lobby: ChampSelectState = { session: null, champion: null, role: null };
const status: DataStatus = { patch: "16.20", run_id: "fixture", key_id: "036EAC4B585E4DCA", files: 80 };

function selecting(champion: string, champion_id: number, phase: string, locked = false): ChampSelectState {
  return { session: { champion_id, locked, role: "JUNGLE", phase, spells: [4, 14] }, champion, role: "JUNGLE" };
}

const leeSin: Plan = {
  champion: "LeeSin",
  role: "JUNGLE",
  patch: "16.20",
  runes: {
    value: { primary_style: 8000, sub_style: 8300, perks: [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001] },
    label: "popular",
  },
  spells: { value: [11, 4], label: "popular" },
  items: [
    { slot: 1, value: 6692, label: "popular" },
    { slot: 2, value: 6610, label: "clearly_better", wpa: 0.021, ci: [0.008, 0.034], games: 640 },
    { slot: 3, value: 3053, label: "popular" },
  ],
};

/** Names for the ids above and in the build files below; the ones tools/lcu_mock/game_data.json
 * serves are a subset. */
const names: GameNames = {
  champions: { "64": "Lee Sin", "104": "Graves" },
  rune_styles: { "8000": "Precision", "8100": "Domination", "8300": "Inspiration", "8400": "Resolve" },
  runes: {
    "8010": "Conqueror",
    "9111": "Triumph",
    "9104": "Legend: Alacrity",
    "8014": "Coup de Grace",
    "8304": "Magical Footwear",
    "8347": "Cosmic Insight",
    "5005": "Attack Speed",
    "5008": "Adaptive Force",
    "5001": "Health Scaling",
    "8112": "Electrocute",
    "8143": "Sudden Impact",
    "8138": "Eyeball Collection",
    "8135": "Treasure Hunter",
    "8369": "First Strike",
    "8345": "Biscuit Delivery",
    "8005": "Press the Attack",
    "8009": "Presence of Mind",
    "8429": "Conditioning",
    "8451": "Overgrowth",
  },
  spells: { "4": "Flash", "11": "Smite", "14": "Ignite" },
  items: {
    "6692": "Eclipse",
    "6610": "Sundered Sky",
    "3053": "Sterak's Gage",
    "6676": "The Collector",
    "6631": "Stridebreaker",
    "6698": "Profane Hydra",
    "3071": "Black Cleaver",
    "6333": "Death's Dance",
    "3026": "Guardian Angel",
    "6694": "Serylda's Grudge",
  },
};

type Perks = Build["runes"][number]["page"]["perks"];
const page = (primaryStyle: number, subStyle: number, perks: Perks) => ({ primaryStyle, subStyle, perks });
const conqueror: Perks = [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001];

/** Lee Sin's build file: several options per slot, one clearly better item at slot 2 (the
 * plan's choice), one clearly worse, one fragile, and rare options with too few games. */
const leeSinBuild: Build = {
  schemaVersion: 1,
  patch: "16.20",
  region: "all",
  elo: "master_plus",
  champion: "LeeSin",
  role: "JUNGLE",
  games: 1840,
  runes: [
    { page: page(8000, 8300, conqueror), wpa: 0.004, ci: [-0.006, 0.014], n: 1650, games: 920, flags: ["no_clear_difference"] },
    {
      page: page(8100, 8000, [8112, 8143, 8138, 8135, 9111, 9104, 5005, 5008, 5001]),
      wpa: -0.006,
      ci: [-0.019, 0.007],
      n: 600,
      games: 510,
      flags: ["no_clear_difference"],
      comparison: { versus: 8010, wpa: -0.009, q: 0.41, ci: [-0.024, 0.006] },
    },
    { page: page(8300, 8000, [8369, 8304, 8345, 8347, 8009, 9104, 5005, 5008, 5001]), wpa: null, ci: null, n: 180, games: 180, flags: ["low_sample"] },
    { page: page(8000, 8400, [8010, 9111, 9104, 8014, 8429, 8451, 5005, 5008, 5001]), wpa: null, ci: null, n: 90, games: 90, flags: ["low_sample"] },
    { page: page(8000, 8300, [8005, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001]), wpa: null, ci: null, n: 40, games: 40, flags: ["low_overlap"] },
  ],
  spells: [
    { spells: [11, 4], wpa: null, ci: null, n: 1790, games: 1790, flags: [] },
    { spells: [11, 14], wpa: null, ci: null, n: 50, games: 50, flags: ["low_sample"] },
  ],
  items: [
    { slot: 1, item: 6692, wpa: 0.003, ci: [-0.005, 0.011], n: 1500, picks: 1120, flags: ["no_clear_difference"] },
    {
      slot: 1,
      item: 6631,
      wpa: -0.002,
      ci: [-0.014, 0.01],
      n: 520,
      picks: 410,
      flags: ["no_clear_difference"],
      comparison: { versus: 6692, wpa: -0.004, q: 0.62, ci: [-0.018, 0.01] },
    },
    { slot: 1, item: 6698, wpa: null, ci: null, n: 210, picks: 210, flags: ["low_sample"] },
    { slot: 1, item: 3071, wpa: null, ci: null, n: 100, picks: 100, flags: ["low_overlap"] },
    { slot: 2, item: 3071, wpa: 0.001, ci: [-0.008, 0.01], n: 1300, picks: 900, flags: ["no_clear_difference"] },
    {
      slot: 2,
      item: 6610,
      wpa: 0.015,
      ci: [0.004, 0.026],
      n: 820,
      picks: 640,
      flags: [],
      comparison: { versus: 3071, wpa: 0.021, q: 0.03, ci: [0.008, 0.034] },
    },
    {
      slot: 2,
      item: 6333,
      wpa: -0.003,
      ci: [-0.017, 0.011],
      n: 330,
      picks: 180,
      flags: ["no_clear_difference"],
      comparison: { versus: 3071, wpa: -0.004, q: 0.7, ci: [-0.02, 0.012] },
    },
    { slot: 2, item: 3053, wpa: null, ci: null, n: 70, picks: 70, flags: ["low_sample"] },
    { slot: 3, item: 3053, wpa: 0.006, ci: [-0.004, 0.016], n: 1100, picks: 610, flags: ["no_clear_difference"] },
    {
      slot: 3,
      item: 6333,
      wpa: -0.012,
      ci: [-0.024, 0.0],
      n: 700,
      picks: 420,
      flags: [],
      comparison: { versus: 3053, wpa: -0.018, q: 0.04, ci: [-0.033, -0.004] },
    },
    {
      slot: 3,
      item: 3026,
      wpa: 0.009,
      ci: [-0.006, 0.024],
      n: 340,
      picks: 160,
      flags: ["no_clear_difference", "fragile"],
      comparison: { versus: 3053, wpa: 0.005, q: 0.38, ci: [-0.01, 0.02] },
    },
    { slot: 3, item: 6694, wpa: null, ci: null, n: 90, picks: 90, flags: ["low_sample"] },
  ],
};

/** Graves: a small build file where nothing has enough games to compare. */
const gravesBuild: Build = {
  ...leeSinBuild,
  champion: "Graves",
  games: 140,
  runes: [{ page: page(8000, 8300, conqueror), wpa: null, ci: null, n: 140, games: 140, flags: ["low_sample"] }],
  spells: [{ spells: [11, 4], wpa: null, ci: null, n: 140, games: 140, flags: ["low_sample"] }],
  items: [{ slot: 1, item: 6676, wpa: null, ci: null, n: 60, picks: 60, flags: ["low_sample"] }],
};

const builds = { "Graves/JUNGLE": gravesBuild, "LeeSin/JUNGLE": leeSinBuild };

const backups = (): Backup[] => [
  { location: "backups/item-sets-0001792405200000-000.json", saved_at_ms: 1792405200000 },
  { location: "backups/item-sets-0001792318800000-000.json", saved_at_ms: 1792318800000 },
];

const rankedJungle = [
  lobby,
  selecting("Graves", 104, "PLANNING"),
  selecting("LeeSin", 64, "BAN_PICK"),
  selecting("LeeSin", 64, "FINALIZATION", true),
];

const graves: Plan = { ...leeSin, champion: "Graves", items: [{ slot: 1, value: 6676, label: "popular" }] };

export const scenarios = {
  "ranked-jungle": {
    steps: rankedJungle,
    plans: { "Graves/JUNGLE": graves, "LeeSin/JUNGLE": leeSin },
    builds,
    status,
    names,
    backups: backups(),
  },
  "pages-full": {
    steps: rankedJungle,
    plans: { "Graves/JUNGLE": graves, "LeeSin/JUNGLE": leeSin },
    builds,
    status,
    names,
    runes: {
      status: "skipped",
      reason: "all your rune pages are in use: delete one in the client, then import again",
    },
  },
  "no-client": {
    steps: [{ code: "unavailable", message: "no lockfile: is the League client running?" }],
    plans: {},
    status,
  },
  "bad-data": {
    steps: [selecting("LeeSin", 64, "FINALIZATION", true)],
    plans: { "LeeSin/JUNGLE": { code: "invalid_data", message: "16.20 all/master_plus/LeeSin/JUNGLE.json: hash mismatch" } },
    status,
  },
} satisfies Record<string, Scenario>;

export type ScenarioName = keyof typeof scenarios;

const isError = (v: object): v is CommandError => "code" in v && "message" in v;
const result = <T extends object>(v: T | CommandError): Result<T> =>
  isError(v) ? { ok: false, error: v } : ok(v);

export class MockBackend implements Backend {
  #step = 0;
  #listeners = new Set<() => void>();
  readonly calls: { id: CommandId; params: unknown }[] = [];
  /** This run's backups: restoring adds one, and scenarios stay as written. */
  #backups: Backup[];

  constructor(readonly scenario: Scenario) {
    this.#backups = [...(scenario.backups ?? [])];
  }

  /** Moves to the next champion-select step; stays on the last one. */
  step(): void {
    this.#step = Math.min(this.#step + 1, this.scenario.steps.length - 1);
    for (const listener of this.#listeners) listener();
  }

  /** Like the core's watcher: tells subscribers when the champion-select step changed. */
  subscribe(onChange: () => void): () => void {
    this.#listeners.add(onChange);
    return () => this.#listeners.delete(onChange);
  }

  async run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>> {
    this.calls.push({ id, params });
    type Out = Result<Commands[K]["result"]>;
    const current = this.scenario.steps[this.#step] ?? lobby;
    switch (id) {
      case "data.status":
        return result(this.scenario.status) as Out;
      case "champselect.state":
        return result(current) as Out;
      case "item_sets.backups":
        return ok({ backups: [...this.#backups] }) as Out;
      case "item_sets.restore": {
        const { backup } = params as Commands["item_sets.restore"]["params"];
        if (isError(current)) return result(current) as Out;
        if (!this.#backups.some((b) => b.location === backup)) {
          return err("not_found", `${backup}: no such backup`) as Out;
        }
        const saved_at_ms = Date.now();
        const previous_backup = `backups/item-sets-${String(saved_at_ms).padStart(16, "0")}-000.json`;
        this.#backups.unshift({ location: previous_backup, saved_at_ms });
        return ok({ restored: backup, sets: 30, previous_backup }) as Out;
      }
      case "names.get":
        return result(this.scenario.names ?? { code: "unavailable", message: "no names" }) as Out;
      case "build.plan": {
        const { champion, role } = params as Commands["build.plan"]["params"];
        const plan = this.scenario.plans[`${champion}/${role}`];
        return (plan ? result(plan) : err("not_found", `no build for ${champion} ${role}`)) as Out;
      }
      case "build.get": {
        const { champion, role } = params as Commands["build.get"]["params"];
        const build = this.scenario.builds?.[`${champion}/${role}`];
        return (build ? ok(build) : err("not_found", `no build for ${champion} ${role}`)) as Out;
      }
      case "build.import": {
        if (isError(current) || !current.champion || !current.role) {
          return err("invalid_params", "no champion select to import for") as Out;
        }
        const name = `Stronk: ${current.champion} ${current.role}`;
        const imported: Imported = {
          champion: current.champion,
          role: current.role,
          runes: this.scenario.runes ?? { status: "imported", name, label: "popular" },
          item_set: { status: "imported", name, label: "popular" },
          item_set_backup: "backups/item-sets-1.json",
          spells: { status: "imported", name: "4 11", label: "popular" },
        };
        return ok(imported) as Out;
      }
      default:
        return err("unknown_command", `unknown command ${String(id)}`) as Out;
    }
  }
}
