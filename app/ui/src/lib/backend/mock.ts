// MockBackend: scripted scenarios in a plain browser (`just app-mock`) and in tests. The
// `ranked-jungle` scenario follows the same steps as tools/lcu_mock's session; its builds are
// the signed fixture data the core verifies (fixtures/data).

import graves from "../../../../../fixtures/data/16.20/all/master_plus/Graves/JUNGLE.json";
import leeSin from "../../../../../fixtures/data/16.20/all/master_plus/LeeSin/JUNGLE.json";
import {
  type Backend,
  type Build,
  type ChampSelectState,
  type CommandError,
  type CommandId,
  type Commands,
  type DataStatus,
  err,
  ok,
  type Result,
} from "./backend.ts";

export interface Scenario {
  steps: (ChampSelectState | CommandError)[];
  builds: Record<string, Build | CommandError>;
  status: DataStatus | CommandError;
}

const lobby: ChampSelectState = { session: null, champion: null, role: null };
const status: DataStatus = { patch: "16.20", run_id: "fixture", key_id: "036EAC4B585E4DCA", files: 80 };

function selecting(champion: string, champion_id: number, phase: string, locked = false): ChampSelectState {
  return { session: { champion_id, locked, role: "JUNGLE", phase }, champion, role: "JUNGLE" };
}

/** JSON imports widen tuples (rune pages) to arrays; these are the signed fixture files the
 * core verifies against build.v1 in its own tests, so the cast stays at this one boundary. */
const fixture = (json: unknown): Build => json as Build;

export const scenarios = {
  "ranked-jungle": {
    steps: [
      lobby,
      selecting("Graves", 104, "PLANNING"),
      selecting("LeeSin", 64, "BAN_PICK"),
      selecting("LeeSin", 64, "FINALIZATION", true),
    ],
    builds: { "Graves/JUNGLE": fixture(graves), "LeeSin/JUNGLE": fixture(leeSin) },
    status,
  },
  "no-client": {
    steps: [{ code: "unavailable", message: "no lockfile: is the League client running?" }],
    builds: {},
    status,
  },
  "bad-data": {
    steps: [selecting("LeeSin", 64, "FINALIZATION", true)],
    builds: { "LeeSin/JUNGLE": { code: "invalid_data", message: "16.20 all/master_plus/LeeSin/JUNGLE.json: hash mismatch" } },
    status,
  },
} satisfies Record<string, Scenario>;

export type ScenarioName = keyof typeof scenarios;

const isError = (v: object): v is CommandError => "code" in v && "message" in v;
const result = <T extends object>(v: T | CommandError): Result<T> =>
  isError(v) ? { ok: false, error: v } : ok(v);

export class MockBackend implements Backend {
  #step = 0;
  readonly calls: { id: CommandId; params: unknown }[] = [];

  constructor(readonly scenario: Scenario) {}

  /** Moves to the next champion-select step; stays on the last one. */
  step(): void {
    this.#step = Math.min(this.#step + 1, this.scenario.steps.length - 1);
  }

  get stepIndex(): number {
    return this.#step;
  }

  async run<K extends CommandId>(id: K, params: Commands[K]["params"]): Promise<Result<Commands[K]["result"]>> {
    this.calls.push({ id, params });
    type Out = Result<Commands[K]["result"]>;
    switch (id) {
      case "data.status":
        return result(this.scenario.status) as Out;
      case "champselect.state": {
        const current = this.scenario.steps[this.#step] ?? lobby;
        return result(current) as Out;
      }
      case "build.get": {
        const { champion, role } = params as Commands["build.get"]["params"];
        const build = this.scenario.builds[`${champion}/${role}`];
        return (build ? result(build) : err("not_found", `no build for ${champion} ${role}`)) as Out;
      }
      default:
        return err("unknown_command", `unknown command ${String(id)}`) as Out;
    }
  }
}
