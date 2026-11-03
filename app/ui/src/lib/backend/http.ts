// The web build viewer's backend (ADR-018, ADR-086): read-only, no League client. Builds come
// from the published data over HTTP, checked by the viewer's WebAssembly core (`stronk-web`,
// `just web-core`) against the manifest's signature and planned by the app's own rule; names
// and icons come from CommunityDragon's mirror of the client's game data. What the app reads
// from champion select, the viewer reads from the champion and role the player picks.

import type { Backend, ChampSelectState, CommandId, Commands, DataStatus, GameNames, Result, Role } from "./backend.ts";
import { err, ok } from "./backend.ts";

/** A patch's verified data, as the core holds it. */
export interface CoreData {
  elos(): string[];
  /** `[{champion, role}]` as JSON: every build the manifest lists. */
  builds(): string;
  /** The bracket the app would read for `wanted`: that one, else the closest with a build. */
  bracket(champion: string, role: string, wanted: string): string | undefined;
  /** The plan for a build file's bytes, as `build.plan` returns it (JSON); throws on a bad file. */
  plan(champion: string, role: string, bracket: string, data: Uint8Array): string;
}

/** The viewer's core (`crates/web`). Every call may throw: the error's message says why. */
export interface WebCore {
  /** Verifies a patch's manifest against its signature and the public key. */
  open(publicKey: string, patch: string, manifest: Uint8Array, signature: Uint8Array): CoreData;
  /** A build's path inside its patch directory. */
  file(champion: string, role: string, bracket: string): string;
  /** `{names, icons}` as JSON, from the five game data documents. */
  gameNames(champions: string, perkStyles: string, perks: string, spells: string, items: string): string;
}

/** The core built by `just web-core`, loaded on first use. */
export async function loadCore(): Promise<WebCore> {
  const core = await import("./web/core/stronk_web.js");
  await core.default();
  return {
    open: (key, patch, manifest, signature) => new core.Data(key, patch, manifest, signature),
    file: (champion, role, bracket) => core.Data.file(champion, role, bracket),
    gameNames: (...docs) => core.game_names(...docs),
  };
}

export interface Listed {
  champion: string;
  role: Role;
}

/** The game data documents, as the client serves them under `/lol-game-data/assets/v1/`. */
const DOCUMENTS = ["champion-summary.json", "perkstyles.json", "perks.json", "summoner-spells.json", "items.json"] as const;
/** Where the client serves its game data; CommunityDragon mirrors it per patch. */
const ASSETS = "/lol-game-data/assets/";
const DEFAULT_ELO = "master_plus";

export interface HttpOptions {
  /** The published data's root, where `index.json` is (a `just serve-data` URL, or the CDN). */
  data: string;
  /** The minisign public key the data must be signed with. */
  publicKey: string;
  /** CommunityDragon's root (`https://raw.communitydragon.org/`). */
  gameData: string;
  core?: () => Promise<WebCore>;
  fetch?: typeof fetch;
}

type Out<K extends CommandId> = Result<Commands[K]["result"]>;
type Icons = { [kind: string]: { [id: string]: string } };

export class HttpBackend implements Backend {
  private readonly options: Required<HttpOptions>;
  private core: Promise<WebCore> | null = null;
  private patch: Promise<{ patch: string; data: CoreData; status: DataStatus }> | null = null;
  private game: Promise<{ names: GameNames; icons: Icons; ids: Map<string, number> }> | null = null;
  private selected: Listed | null = null;

  constructor(options: HttpOptions) {
    this.options = {
      core: loadCore,
      fetch: (input, init) => globalThis.fetch(input, init),
      ...options,
      data: options.data.replace(/\/?$/, "/"),
      gameData: options.gameData.replace(/\/?$/, "/"),
    };
  }

  /** The viewer's own commands: what it can show, and the champion and role to show. */
  readonly viewer = {
    builds: async (): Promise<Result<(Listed & { id: number })[]>> => {
      const loaded = await this.attempt(async () => (await this.data()).data.builds());
      if (!loaded.ok) return loaded;
      // Without names the champions have no ids: the picker shows their keys.
      const game = await this.attempt(() => this.gameData());
      const id = (champion: string) => (game.ok ? (game.value.ids.get(champion) ?? 0) : 0);
      return ok((JSON.parse(loaded.value) as Listed[]).map((b) => ({ ...b, id: id(b.champion) })));
    },
    select: (champion: string, role: Role): void => {
      this.selected = { champion, role };
    },
  };

  async run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Out<K>> {
    switch (id) {
      case "data.status":
        return (await this.attempt(async () => (await this.data()).status)) as Out<K>;
      case "champselect.state":
        return (await this.champSelect()) as Out<K>;
      case "names.get":
        return (await this.attempt(async () => (await this.gameData()).names)) as Out<K>;
      case "icons.get":
        return (await this.icons(params as Commands["icons.get"]["params"])) as Out<K>;
      case "build.plan":
        return (await this.plan(params as Commands["build.plan"]["params"])) as Out<K>;
      default:
        return err("unsupported", "the web viewer only shows builds: import them from the app") as Out<K>;
    }
  }

  /** The newest patch in the index, its manifest verified; loaded once. */
  private data(): Promise<{ patch: string; data: CoreData; status: DataStatus }> {
    this.patch ??= (async () => {
      const index = (await this.json(`${this.options.data}index.json`)) as { patches?: unknown };
      const patches = Array.isArray(index.patches) ? index.patches.filter((p): p is string => typeof p === "string") : [];
      const patch = patches.at(-1);
      if (!patch) throw new Error("the published data lists no patch");
      const [manifest, signature, core] = await Promise.all([
        this.bytes(`${this.options.data}${patch}/manifest.json`),
        this.bytes(`${this.options.data}${patch}/manifest.json.minisig`),
        this.loadedCore(),
      ]);
      const data = core.open(this.options.publicKey, patch, manifest, signature);
      const parsed = JSON.parse(new TextDecoder().decode(manifest)) as { runId?: string; keyId?: string; files?: unknown[] };
      const status: DataStatus = {
        patch,
        elos: data.elos(),
        files: parsed.files?.length ?? 0,
        run_id: parsed.runId ?? "",
        key_id: parsed.keyId ?? "",
      };
      return { patch, data, status };
    })();
    // A failure is retried on the next call rather than kept.
    this.patch.catch(() => (this.patch = null));
    return this.patch;
  }

  /** Names, icon paths and champion ids by key, from CommunityDragon's copy of the patch's game data. */
  private gameData(): Promise<{ names: GameNames; icons: Icons; ids: Map<string, number> }> {
    this.game ??= (async () => {
      const { patch } = await this.data();
      const base = `${this.options.gameData}${patch}/plugins/rcp-be-lol-game-data/global/default/v1/`;
      const docs = await Promise.all(DOCUMENTS.map(async (d) => new TextDecoder().decode(await this.bytes(base + d))));
      const [champions, styles, perks, spells, items] = docs as [string, string, string, string, string];
      const parsed = JSON.parse((await this.loadedCore()).gameNames(champions, styles, perks, spells, items)) as {
        names: GameNames;
        icons: Icons;
      };
      const ids = new Map<string, number>();
      for (const c of JSON.parse(champions) as { id?: unknown; alias?: unknown }[]) {
        if (typeof c.alias === "string" && typeof c.id === "number") ids.set(c.alias, c.id);
      }
      return { ...parsed, ids };
    })();
    this.game.catch(() => (this.game = null));
    return this.game;
  }

  /** The picked champion and role as a champion select the player is locked into. */
  private async champSelect(): Promise<Result<ChampSelectState>> {
    if (!this.selected) return ok({ champion: null, role: null, session: null });
    const { champion, role } = this.selected;
    // Without names the champion has no id: its icon and name fall back to the key.
    const game = await this.attempt(() => this.gameData());
    const champion_id = game.ok ? (game.value.ids.get(champion) ?? 0) : 0;
    return ok({
      champion,
      role,
      session: { champion_id, locked: true, role, phase: "VIEWER", spells: [0, 0], enemies: [] },
    });
  }

  /** Icon URLs on CommunityDragon for the ids asked, by kind; ids without an icon are left out. */
  private async icons(params: Commands["icons.get"]["params"]): Promise<Out<"icons.get">> {
    const game = await this.attempt(() => this.gameData());
    if (!game.ok) return game;
    const { patch } = await this.data();
    const root = `${this.options.gameData}${patch}/plugins/rcp-be-lol-game-data/global/default/`;
    const out = { champions: {}, rune_styles: {}, runes: {}, spells: {}, items: {} } as Commands["icons.get"]["result"];
    for (const kind of Object.keys(out) as (keyof typeof out)[]) {
      for (const id of params[kind] ?? []) {
        const path = game.value.icons[kind]?.[String(id)];
        if (path?.startsWith(ASSETS)) out[kind][String(id)] = root + path.slice(ASSETS.length).toLowerCase();
      }
    }
    return ok(out);
  }

  /** The build of the bracket the app would read, checked against the manifest and planned by the core. */
  private async plan(params: Commands["build.plan"]["params"]): Promise<Out<"build.plan">> {
    return this.attempt(async () => {
      const { patch, data } = await this.data();
      const bracket = data.bracket(params.champion, params.role, params.elo ?? DEFAULT_ELO);
      if (!bracket) throw new NotFound(`no build for ${params.champion} ${params.role}`);
      const core = await this.loadedCore();
      const path = core.file(params.champion, params.role, bracket);
      const bytes = await this.bytes(`${this.options.data}${patch}/${path}`);
      return JSON.parse(data.plan(params.champion, params.role, bracket, bytes)) as Commands["build.plan"]["result"];
    });
  }

  private loadedCore(): Promise<WebCore> {
    this.core ??= this.options.core();
    this.core.catch(() => (this.core = null));
    return this.core;
  }

  private async bytes(url: string): Promise<Uint8Array> {
    let response: Response;
    try {
      response = await this.options.fetch(url);
    } catch (e) {
      throw new Unavailable(`${url}: ${e instanceof Error ? e.message : String(e)}`);
    }
    if (response.status === 404) throw new NotFound(`${url}: not found`);
    if (!response.ok) throw new Unavailable(`${url}: HTTP ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  }

  private async json(url: string): Promise<unknown> {
    const bytes = await this.bytes(url);
    try {
      return JSON.parse(new TextDecoder().decode(bytes));
    } catch {
      throw new Error(`${url}: not JSON`);
    }
  }

  /** `run`'s result, its error coded as the core codes it: missing, unreachable, or refused. */
  private async attempt<T>(work: () => Promise<T>): Promise<Result<T>> {
    try {
      return ok(await work());
    } catch (e) {
      if (e instanceof NotFound) return err("not_found", e.message);
      if (e instanceof Unavailable) return err("unavailable", e.message);
      return err("invalid_data", `the published data was refused: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
}

class NotFound extends Error {}
class Unavailable extends Error {}
