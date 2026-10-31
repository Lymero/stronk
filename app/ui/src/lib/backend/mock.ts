// MockBackend: scripted scenarios in a plain browser (`just app-mock`) and in tests. The
// `ranked-jungle` scenario follows the same steps as tools/lcu_mock's session; its plans are
// what the core's `build.plan` gives for the signed fixture data (fixtures/data).

import {
  type Alternatives,
  type Backend,
  type Backup,
  type ChampSelectState,
  type CommandError,
  type CommandId,
  type Commands,
  type DataStatus,
  err,
  type GameIcons,
  type GameKind,
  type GameNames,
  type Imported,
  ok,
  type Outcome,
  type Page,
  type Plan,
  type Result,
  type Row,
} from "./backend.ts";

const KINDS: GameKind[] = ["champions", "rune_styles", "runes", "spells", "items"];

/** A stand-in icon: a square in a colour taken from the id, with the name's initials. */
export function placeholderIcon(kind: GameKind, id: number, name: string): string {
  let hash = 0;
  for (const c of `${kind}/${id}`) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  const initials = name
    .split(/[\s:'-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">` +
    `<rect width="32" height="32" fill="hsl(${hash % 360} 45% 42%)"/>` +
    `<text x="16" y="21" font-family="sans-serif" font-size="13" font-weight="700" fill="#fff" text-anchor="middle">${initials}</text>` +
    `</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export interface Scenario {
  steps: (ChampSelectState | CommandError)[];
  plans: Record<string, Plan | CommandError>;
  status: DataStatus | CommandError;
  /** The client's game data names; without them the UI shows ids. */
  names?: GameNames | CommandError;
  /** `false`: the client serves no icons (stand-ins show); otherwise a placeholder for every
   * id it has a name for. */
  icons?: false;
  /** What importing the rune page does; imported by default. */
  runes?: Outcome;
  /** The item set backups on this machine, newest first; restoring one adds a backup. */
  backups?: Backup[];
}

const lobby: ChampSelectState = { session: null, champion: null, role: null };
const status: DataStatus = { patch: "16.20", run_id: "fixture", key_id: "036EAC4B585E4DCA", files: 80 };

function selecting(champion: string, champion_id: number, phase: string, locked = false, enemies: number[] = []): ChampSelectState {
  return { session: { champion_id, locked, role: "JUNGLE", phase, spells: [4, 14], enemies }, champion, role: "JUNGLE" };
}


/** Names for the ids in the plans below; the ones tools/lcu_mock/game_data.json
 * serves are a subset. */
const names: GameNames = {
  champions: { "64": "Lee Sin", "104": "Graves" },
  rune_styles: { "8000": "Precision", "8100": "Domination", "8200": "Sorcery", "8300": "Inspiration", "8400": "Resolve" },
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
    "9105": "Legend: Haste",
    "9103": "Legend: Bloodline",
    "8017": "Cut Down",
    "8299": "Last Stand",
    "5010": "Move Speed",
    "5011": "Health",
    "8429": "Conditioning",
    "8451": "Overgrowth",
    "8008": "Lethal Tempo",
    "8021": "Fleet Footwork",
    "9101": "Absorb Life",
    "8128": "Dark Harvest",
    "9923": "Hail of Blades",
    "8126": "Cheap Shot",
    "8139": "Taste of Blood",
    "8137": "Sixth Sense",
    "8140": "Grisly Mementos",
    "8141": "Deep Ward",
    "8105": "Relentless Hunter",
    "8106": "Ultimate Hunter",
    "8214": "Summon Aery",
    "8229": "Arcane Comet",
    "8230": "Phase Rush",
    "8224": "Axiom Arcanist",
    "8226": "Manaflow Band",
    "8275": "Nimbus Cloak",
    "8210": "Transcendence",
    "8234": "Celerity",
    "8233": "Absolute Focus",
    "8237": "Scorch",
    "8232": "Waterwalking",
    "8236": "Gathering Storm",
    "8351": "Glacial Augment",
    "8360": "Unsealed Spellbook",
    "8306": "Hextech Flashtraption",
    "8321": "Cash Back",
    "8313": "Triple Tonic",
    "8352": "Time Warp Tonic",
    "8410": "Approach Velocity",
    "8316": "Jack Of All Trades",
    "8437": "Grasp of the Undying",
    "8439": "Aftershock",
    "8465": "Guardian",
    "8446": "Demolish",
    "8463": "Font of Life",
    "8401": "Shield Bash",
    "8444": "Second Wind",
    "8473": "Bone Plating",
    "8453": "Revitalize",
    "8242": "Unflinching",
    "5007": "Ability Haste",
    "5013": "Tenacity and Slow Resist",
  },
  rune_trees: {
    "8000": [[8005, 8008, 8021, 8010], [9101, 9111, 8009], [9104, 9105, 9103], [8014, 8017, 8299]],
    "8100": [[8112, 8128, 9923], [8126, 8139, 8143], [8137, 8140, 8141], [8135, 8105, 8106]],
    "8200": [[8214, 8229, 8230], [8224, 8226, 8275], [8210, 8234, 8233], [8237, 8232, 8236]],
    "8300": [[8351, 8360, 8369], [8306, 8304, 8321], [8313, 8352, 8345], [8347, 8410, 8316]],
    "8400": [[8437, 8439, 8465], [8446, 8463, 8401], [8429, 8444, 8473], [8451, 8453, 8242]],
  },
  shard_rows: [[5008, 5005, 5007], [5008, 5010, 5001], [5011, 5013, 5001]],
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
    "3078": "Trinity Force",
    "3156": "Maw of Malmortius",
    "1101": "Scorchclaw Pup",
    "1102": "Gustwalker Hatchling",
    "1103": "Mosstomper Seedling",
    "2003": "Health Potion",
    "1036": "Long Sword",
    "1037": "Pickaxe",
    "3047": "Plated Steelcaps",
    "3111": "Mercury's Treads",
    "3158": "Ionian Boots of Lucidity",
  },
};

type Perks = Page["perks"];
const conqueror: Perks = [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001];
const electrocute: Page = { primary_style: 8100, sub_style: 8000, perks: [8112, 8143, 8138, 8135, 9111, 9104, 5005, 5008, 5001] };

/** One ranked option, as the core's `build.plan` gives it, with Stronk's judgement as the core
 * makes it (ADR-070): a head-to-head gain shrunk by its uncertainty (τ = 0.02), else 0. */
function row<T>(value: T, played: number, total: number, rest: Partial<Row<T>> = {}): Row<T> {
  const r: Row<T> = {
    value,
    played,
    share: played / total,
    wpa: null,
    ci: null,
    versus: "alternatives",
    confidence: "no_clear_difference",
    fragile: false,
    chosen: false,
    listed: true,
    judged: 0,
    ...rest,
  };
  const measured = r.versus === "most_played" && r.wpa !== null && r.ci && !r.confidence.startsWith("too_few");
  const se = r.ci ? (r.ci[1] - r.ci[0]) / (2 * 1.96) : 0;
  return { ...r, judged: rest.judged ?? (measured ? ((r.wpa ?? 0) * 0.0004) / (0.0004 + se * se) : 0) };
}

/** An option past the short list: played less, shown when the player asks for every option. */
const rare = <T>(value: T, played: number, total: number, rest: Partial<Row<T>> = {}): Row<T> =>
  row(value, played, total, { confidence: "too_few_games", listed: false, ...rest });

/** Lee Sin's rune rows (ADR-057): each row of Precision and of Domination, Inspiration's pairs and
 * the three shard rows; the conqueror page's choices are chosen. */
const leeSinRuneRows: Alternatives["rune_rows"] = [
  {
    kind: "primary",
    style: 8000,
    row: 1,
    rows: [
      row([9111], 1480, 1740, { wpa: 0.002, ci: [-0.006, 0.01], confidence: "most_played", chosen: true }),
      row([8009], 260, 1740, { wpa: -0.006, ci: [-0.027, 0.015], versus: "most_played" }),
    ],
    more: 0,
  },
  {
    kind: "primary",
    style: 8000,
    row: 2,
    rows: [
      row([9104], 1210, 1740, { wpa: 0.003, ci: [-0.006, 0.012], confidence: "most_played", chosen: true }),
      row([9105], 470, 1740, { wpa: -0.004, ci: [-0.019, 0.011], versus: "most_played" }),
      rare([9103], 60, 1740),
    ],
    more: 1,
  },
  {
    kind: "primary",
    style: 8000,
    row: 3,
    rows: [
      row([8014], 990, 1740, { wpa: 0.001, ci: [-0.009, 0.011], confidence: "most_played", chosen: true }),
      row([8017], 610, 1740, { wpa: 0.004, ci: [-0.009, 0.017], versus: "most_played" }),
      row([8299], 140, 1740, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  {
    kind: "primary",
    style: 8100,
    row: 1,
    rows: [row([8143], 560, 560, { wpa: 0.0, ci: [-0.012, 0.012], confidence: "most_played" })],
    more: 0,
  },
  {
    kind: "secondary",
    style: 8300,
    row: null,
    rows: [
      row([8304, 8347], 1020, 1100, { wpa: 0.001, ci: [-0.01, 0.012], confidence: "most_played", chosen: true }),
      row([8345, 8347], 80, 1100, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  {
    kind: "shard",
    style: null,
    row: 1,
    rows: [
      row([5005], 1650, 1840, { wpa: 0.001, ci: [-0.008, 0.01], confidence: "most_played", chosen: true }),
      row([5008], 190, 1840, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  {
    kind: "shard",
    style: null,
    row: 2,
    rows: [
      row([5008], 1500, 1840, { wpa: 0.002, ci: [-0.007, 0.011], confidence: "most_played", chosen: true }),
      row([5010], 340, 1840, { wpa: -0.011, ci: [-0.03, 0.008], versus: "most_played" }),
    ],
    more: 0,
  },
  {
    kind: "shard",
    style: null,
    row: 3,
    rows: [
      row([5001], 1220, 1840, { wpa: 0.0, ci: [-0.01, 0.01], confidence: "most_played", chosen: true }),
      row([5011], 620, 1840, { wpa: 0.003, ci: [-0.012, 0.018], versus: "most_played" }),
    ],
    more: 0,
  },
];

/** Lee Sin's alternatives: several options per slot, some past the short list, one clearly better item at slot 2 (the
 * plan's choice), one clearly worse, one fragile, and rare options with too few games. */
const leeSinAlternatives: Alternatives = {
  runes: {
    rows: [
      row({ primary_style: 8000, sub_style: 8300, perks: conqueror }, 920, 1740, {
        wpa: 0.004,
        ci: [-0.006, 0.014],
        confidence: "most_played",
        chosen: true,
      }),
      row(electrocute, 510, 1740, { wpa: -0.009, ci: [-0.024, 0.006], versus: "most_played" }),
      row({ primary_style: 8300, sub_style: 8000, perks: [8369, 8304, 8345, 8347, 8009, 9104, 5005, 5008, 5001] }, 180, 1740, {
        confidence: "too_few_games",
      }),
      rare({ primary_style: 8000, sub_style: 8400, perks: [8005, 9111, 9104, 8014, 8429, 8451, 5005, 5008, 5001] }, 80, 1740),
      rare({ primary_style: 8100, sub_style: 8300, perks: [8112, 8143, 8138, 8135, 8304, 8347, 5005, 5008, 5001] }, 50, 1740),
    ],
    more: 2,
  },
  spells: {
    rows: [
      row<[number, number]>([11, 4], 1790, 1840, { confidence: "most_played", chosen: true }),
      row<[number, number]>([11, 14], 50, 1840, { confidence: "not_estimated" }), // spells have no flags
    ],
    more: 0,
  },
  items: [
    {
      slot: 1,
      rows: [
        row(6692, 1120, 1840, { wpa: 0.003, ci: [-0.005, 0.011], confidence: "most_played", chosen: true }),
        row(6631, 410, 1840, { wpa: -0.004, ci: [-0.018, 0.01], versus: "most_played" }),
        row(6698, 210, 1840, { confidence: "too_few_games" }),
        rare(6676, 100, 1840),
        rare(3078, 20, 1840), // under 2% of games: behind "+1"
      ],
      more: 2,
    },
    {
      slot: 2,
      rows: [
        row(3071, 900, 1790, { wpa: 0.001, ci: [-0.008, 0.01], confidence: "most_played" }),
        row(6610, 640, 1790, { wpa: 0.021, ci: [0.008, 0.034], versus: "most_played", confidence: "clearly_better", chosen: true }),
        row(6333, 180, 1790, { wpa: -0.004, ci: [-0.02, 0.012], versus: "most_played" }),
        rare(6676, 70, 1790),
      ],
      more: 1,
    },
    {
      slot: 3,
      rows: [
        row(3053, 610, 1280, { wpa: 0.006, ci: [-0.004, 0.016], confidence: "most_played" }),
        row(6333, 420, 1280, { wpa: -0.018, ci: [-0.033, -0.004], versus: "most_played", confidence: "clearly_worse" }),
        // Ahead of Sterak's Gage on the numbers, not yet clear: Stronk's best bet (ADR-065).
        row(3026, 160, 1280, { wpa: 0.012, ci: [0.0, 0.024], versus: "most_played", confidence: "best_bet", fragile: true, chosen: true }),
        rare(6694, 90, 1280),
      ],
      more: 1,
    },
    {
      // The late items, from the fourth on (ADR-067).
      slot: 4,
      rows: [
        row(3053, 900, 2510, { wpa: 0.002, ci: [-0.006, 0.01], confidence: "most_played", chosen: true }),
        row(3156, 600, 2510, { wpa: 0.004, ci: [-0.008, 0.016], versus: "most_played" }),
        row(6333, 400, 2510, { wpa: -0.003, ci: [-0.018, 0.012], versus: "most_played" }),
        row(3026, 300, 2510, { confidence: "too_few_games" }),
        row(6694, 200, 2510, { confidence: "too_few_games" }),
        rare(3071, 80, 2510),
        rare(3078, 30, 2510),
      ],
      more: 2,
    },
  ],
  // The starts (ADR-071): the jungle pets, Gustwalker behind Scorchclaw, Mosstomper too rare.
  start: {
    rows: [
      row([1101], 1100, 1840, { wpa: 0.001, ci: [-0.008, 0.01], confidence: "most_played", chosen: true }),
      row([1102], 600, 1840, { wpa: -0.004, ci: [-0.016, 0.008], versus: "most_played" }),
      row([1103], 140, 1840, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  // The first components (ADR-072): a Long Sword, a Pickaxe, or both.
  components: {
    rows: [
      row([1036], 1000, 1610, { wpa: 0.0, ci: [-0.009, 0.009], confidence: "most_played", chosen: true }),
      row([1037], 350, 1610, { wpa: 0.003, ci: [-0.011, 0.017], versus: "most_played" }),
      row([1036, 1037], 260, 1610, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  // The boots (ADR-073): Plated Steelcaps most played, Mercury's Treads behind, Ionian too rare.
  boots: {
    rows: [
      row(3047, 900, 1470, { wpa: 0.002, ci: [-0.007, 0.011], confidence: "most_played", chosen: true }),
      row(3111, 450, 1470, { wpa: -0.012, ci: [-0.026, 0.002], versus: "most_played" }),
      row(3158, 120, 1470, { confidence: "too_few_games" }),
    ],
    more: 0,
  },
  rune_rows: leeSinRuneRows,
};

/** Graves: a small build file where nothing has enough games to compare. */
const gravesAlternatives: Alternatives = {
  runes: {
    rows: [row({ primary_style: 8000, sub_style: 8300, perks: conqueror }, 140, 140, { confidence: "too_few_games", chosen: true })],
    more: 0,
  },
  spells: { rows: [row<[number, number]>([11, 4], 140, 140, { confidence: "most_played", chosen: true })], more: 0 },
  items: [{ slot: 1, rows: [row(6676, 60, 60, { confidence: "too_few_games", chosen: true })], more: 0 }],
  start: { rows: [], more: 0 },
  components: { rows: [], more: 0 },
  boots: { rows: [], more: 0 },
  rune_rows: [],
};

const leeSin: Plan = {
  champion: "LeeSin",
  role: "JUNGLE",
  patch: "16.20",
  games: 1840,
  elo: "master_plus",
  region: "all",
  runes: {
    value: { primary_style: 8000, sub_style: 8300, perks: [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001] },
    label: "popular",
  },
  spells: { value: [11, 4], label: "popular" },
  start: { value: [1101], label: "popular" },
  start_buy: [1101, 2003],
  components: { value: [1036], label: "popular" },
  components_buy: [1036, 2003],
  boots: { value: 3047, label: "popular" },
  boots_then: [3111],
  boots_against: null,
  items: [
    { slot: 1, value: 6692, label: "popular", block: 4 },
    { slot: 2, value: 6610, label: "clearly_better", wpa: 0.021, ci: [0.008, 0.034], games: 640, block: 4 },
    { slot: 3, value: 3026, label: "best_bet", wpa: 0.012, ci: [0.0, 0.024], games: 160, block: 4 },
    // Guardian Angel, item 3, left out of the late items' list.
    // In Stronk's order: Maw ahead, then the ones it knows nothing against, Death's Dance behind;
    // Trinity Force is under 2%.
    // Stronk's order: its choice, Maw ahead of it, those it knows nothing against, Death's Dance
    // behind (Trinity Force, under 2%, isn't in it).
    { slot: 4, value: 3053, label: "popular", then: [3156, 6694, 3071, 6333], order: [3053, 3156, 3026, 6694, 3071, 6333], block: 6 },
  ],
  late_slot: 4,
  alternatives: leeSinAlternatives,
};

const backups = (): Backup[] => [
  { location: "backups/item-sets-0001792405200000-000.json", saved_at_ms: 1792405200000 },
  { location: "backups/item-sets-0001792318800000-000.json", saved_at_ms: 1792318800000 },
];

const rankedJungle = [
  lobby,
  selecting("Graves", 104, "PLANNING"),
  selecting("LeeSin", 64, "BAN_PICK"),
  // By lock-in three enemies have picked, mages: boots against a magic team (ADR-074).
  selecting("LeeSin", 64, "FINALIZATION", true, [103, 103, 104]),
];

const graves: Plan = {
  ...leeSin,
  champion: "Graves",
  games: 140,
  items: [{ slot: 1, value: 6676, label: "popular", block: 4 }],
  alternatives: gravesAlternatives,
  start: null,
  components: null,
  boots: null,
};

export const scenarios = {
  "ranked-jungle": {
    steps: rankedJungle,
    plans: { "Graves/JUNGLE": graves, "LeeSin/JUNGLE": leeSin },
    status,
    names,
    backups: backups(),
  },
  "pages-full": {
    steps: rankedJungle,
    plans: { "Graves/JUNGLE": graves, "LeeSin/JUNGLE": leeSin },
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
      case "icons.get": {
        // Like the client: an icon for every id it has a name for, none for the others.
        const names = this.scenario.names;
        if (!names || isError(names) || this.scenario.icons === false) {
          return err("unavailable", "no icons") as Out;
        }
        const asked = params as Commands["icons.get"]["params"];
        const icons: GameIcons = { champions: {}, rune_styles: {}, runes: {}, spells: {}, items: {} };
        for (const kind of KINDS) {
          for (const id of asked[kind] ?? []) {
            const name = names[kind][String(id)];
            if (name) icons[kind][String(id)] = placeholderIcon(kind, id, name);
          }
        }
        return ok(icons) as Out;
      }
      case "build.plan": {
        const { champion, role, enemies } = params as Commands["build.plan"]["params"];
        const plan = this.scenario.plans[`${champion}/${role}`];
        if (!plan) return err("not_found", `no build for ${champion} ${role}`) as Out;
        // Three enemies or more: the core reads their damage; here, always a magic team.
        const against = (enemies?.length ?? 0) >= 3 && "boots" in plan && plan.boots;
        return result(against ? { ...plan, boots: { value: 3111, label: "popular" }, boots_against: "magic" } : plan) as Out;
      }
      case "build.import": {
        if (isError(current) || !current.champion || !current.role) {
          return err("invalid_params", "no champion select to import for") as Out;
        }
        const picks = params as Commands["build.import"]["params"];
        const name = `Stronk: ${current.champion} ${current.role}`;
        const label = (picked: unknown) => (picked ? ("picked" as const) : ("popular" as const));
        const imported: Imported = {
          champion: current.champion,
          role: current.role,
          runes: this.scenario.runes ?? { status: "imported", name, label: label(picks.runes) },
          item_set: { status: "imported", name, label: label(picks.items?.length) },
          item_set_backup: "backups/item-sets-1.json",
          spells: { status: "imported", name: "4 11", label: label(picks.spells) },
        };
        return ok(imported) as Out;
      }
      default:
        return err("unknown_command", `unknown command ${String(id)}`) as Out;
    }
  }
}
