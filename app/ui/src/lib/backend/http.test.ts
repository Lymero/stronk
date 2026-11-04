import { describe, expect, it } from "vitest";
import { HttpBackend, type WebCore } from "./http.ts";

const DATA = "https://data.test/";
const GAME = "https://game.test/";
const DOCS = `${GAME}16.21/plugins/rcp-be-lol-game-data/global/default/v1/`;

/** A core that trusts any manifest and returns what it was asked, so the backend's own work shows. */
function fakeCore(calls: string[], fail?: string): WebCore {
  return {
    open: (key, patch) => {
      calls.push(`open ${key} ${patch}`);
      if (fail === "open") throw new Error("signature rejected");
      return {
        elos: () => ["master_plus", "diamond_plus"],
        windows: () => ["pooled", "patch"],
        builds: () => JSON.stringify([{ champion: "LeeSin", role: "JUNGLE" }, { champion: "Zed", role: "MIDDLE" }]),
        // Lee Sin in every bracket but Emerald+, which reads Diamond+, the patch's alone.
        found: (champion, _role, wanted, window) => {
          if (champion !== "LeeSin") return undefined;
          const elo = wanted === "emerald_plus" ? "diamond_plus" : wanted;
          return JSON.stringify({ elo, window: elo === "diamond_plus" ? "patch" : window });
        },
        plan: (champion, role, bracket, window, data) => {
          if (fail === "plan") throw new Error("hash mismatch");
          return JSON.stringify({ champion, role, elo: bracket, window, bytes: data.length });
        },
      };
    },
    file: (champion, role, bracket, window) => `all/${bracket}/${window === "pooled" ? "pooled/" : ""}${champion}/${role}.json`,
    gameNames: () =>
      JSON.stringify({
        names: { champions: { 64: "Lee Sin" } },
        icons: { champions: { 64: "/lol-game-data/assets/v1/Champion-Icons/64.png" }, items: { 1: "https://elsewhere.test/x.png" } },
      }),
    abilityIcons: (champion, document) => {
      calls.push(`abilities ${champion}`);
      const spells = (JSON.parse(document) as { spells: { abilityIconPath: string }[] }).spells;
      return JSON.stringify(Object.fromEntries(spells.map((s, i) => [champion * 10 + i + 1, s.abilityIconPath])));
    },
  };
}

function backend(routes: Record<string, string | number | Error>, fail?: string) {
  const calls: string[] = [];
  const fetched: string[] = [];
  const http = new HttpBackend({
    data: "https://data.test",
    publicKey: "KEY",
    gameData: GAME,
    core: async () => fakeCore(calls, fail),
    fetch: async (input) => {
      const url = String(input);
      fetched.push(url);
      const route = routes[url];
      if (route instanceof Error) throw route;
      if (route === undefined || typeof route === "number") return new Response("", { status: route ?? 404 });
      return new Response(route);
    },
  });
  return { http, calls, fetched };
}

const PUBLISHED = {
  [`${DATA}index.json`]: JSON.stringify({ patches: ["16.20", "16.21"], schemaVersion: 1 }),
  [`${DATA}16.21/manifest.json`]: JSON.stringify({ runId: "run-1", keyId: "ABCD", files: [{}, {}, {}] }),
  [`${DATA}16.21/manifest.json.minisig`]: "sig",
  [`${DATA}16.21/all/master_plus/LeeSin/JUNGLE.json`]: "{build}",
  [`${DATA}16.21/all/master_plus/pooled/LeeSin/JUNGLE.json`]: "{pooled build}",
  [`${DATA}16.21/all/diamond_plus/LeeSin/JUNGLE.json`]: "{diamond build!}",
  [`${DOCS}champion-summary.json`]: JSON.stringify([{ id: 64, alias: "LeeSin", name: "Lee Sin" }]),
  [`${DOCS}perkstyles.json`]: "{}",
  [`${DOCS}perks.json`]: "[]",
  [`${DOCS}summoner-spells.json`]: "[]",
  [`${DOCS}items.json`]: "[]",
  [`${DOCS}champions/64.json`]: JSON.stringify({
    spells: [{ abilityIconPath: "/lol-game-data/assets/ASSETS/LeeSinQ1.png" }, { abilityIconPath: "https://elsewhere.test/w.png" }],
  }),
};

describe("HttpBackend", () => {
  it("reads the newest patch in the index, its manifest checked by the core once", async () => {
    const { http, calls } = backend(PUBLISHED);
    expect(await http.run("data.status", {})).toEqual({
      ok: true,
      value: {
        patch: "16.21",
        elos: ["master_plus", "diamond_plus"],
        windows: ["pooled", "patch"],
        files: 3,
        run_id: "run-1",
        key_id: "ABCD",
      },
    });
    await http.run("data.status", {});
    expect(calls).toEqual(["open KEY 16.21"]);
  });

  it("plans the build of the bracket and window the core chooses, from the patch's directory", async () => {
    const { http, fetched } = backend(PUBLISHED);
    const plan = await http.run("build.plan", { champion: "LeeSin", role: "JUNGLE", elo: "emerald_plus" });
    expect(plan).toEqual({ ok: true, value: { champion: "LeeSin", role: "JUNGLE", elo: "diamond_plus", window: "patch", bytes: 16 } });
    expect(fetched).toContain(`${DATA}16.21/all/diamond_plus/LeeSin/JUNGLE.json`);
    // Pooled unless asked otherwise (ADR-088).
    const popular = await http.run("build.plan", { champion: "LeeSin", role: "JUNGLE" });
    expect(popular.ok && popular.value).toMatchObject({ elo: "master_plus", window: "pooled" });
    expect(fetched).toContain(`${DATA}16.21/all/master_plus/pooled/LeeSin/JUNGLE.json`);
    const alone = await http.run("build.plan", { champion: "LeeSin", role: "JUNGLE", window: "patch" });
    expect(alone.ok && alone.value).toMatchObject({ elo: "master_plus", window: "patch" });
    expect(fetched).toContain(`${DATA}16.21/all/master_plus/LeeSin/JUNGLE.json`);
  });

  it("says why a build can't be shown: missing, unreachable, or refused", async () => {
    const missing = await backend(PUBLISHED).http.run("build.plan", { champion: "Zed", role: "MIDDLE" });
    expect(missing.ok || missing.error.code).toBe("not_found");
    const down = backend({ ...PUBLISHED, [`${DATA}index.json`]: new TypeError("Failed to fetch") });
    const unreachable = await down.http.run("data.status", {});
    expect(unreachable.ok || unreachable.error.code).toBe("unavailable");
    const refused = await backend(PUBLISHED, "open").http.run("data.status", {});
    expect(refused.ok || refused.error).toMatchObject({ code: "invalid_data", message: expect.stringContaining("signature rejected") });
    const tampered = await backend(PUBLISHED, "plan").http.run("build.plan", { champion: "LeeSin", role: "JUNGLE" });
    expect(tampered.ok || tampered.error.code).toBe("invalid_data");
    const failing = backend({ ...PUBLISHED, [`${DATA}16.21/manifest.json`]: 500 });
    const server = await failing.http.run("data.status", {});
    expect(server.ok || server.error.code).toBe("unavailable");
  });

  it("reports the champion and role picked as a locked-in champion select", async () => {
    const { http } = backend(PUBLISHED);
    expect(await http.run("champselect.state", {})).toEqual({ ok: true, value: { champion: null, role: null, session: null } });
    http.viewer.select("LeeSin", "JUNGLE");
    const state = await http.run("champselect.state", {});
    expect(state.ok && state.value).toMatchObject({ champion: "LeeSin", role: "JUNGLE", session: { champion_id: 64, locked: true } });
    expect(await http.viewer.builds()).toEqual({
      ok: true,
      value: [
        { champion: "LeeSin", role: "JUNGLE", id: 64 },
        { champion: "Zed", role: "MIDDLE", id: 0 },
      ],
    });
  });

  it("gives icons as CommunityDragon addresses of the patch, only for the client's own paths", async () => {
    const { http } = backend(PUBLISHED);
    const icons = await http.run("icons.get", { champions: [64, 65], items: [1] });
    expect(icons.ok && icons.value).toEqual({
      champions: { 64: `${GAME}16.21/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/64.png` },
      rune_styles: {},
      runes: {},
      spells: {},
      items: {},
      abilities: {},
    });
  });

  it("gives a champion's ability icons from its own document, read once", async () => {
    const { http, calls, fetched } = backend(PUBLISHED);
    const icons = await http.run("icons.get", { abilities: [641, 642, 643, 651] });
    expect(icons.ok && icons.value.abilities).toEqual({ 641: `${GAME}16.21/plugins/rcp-be-lol-game-data/global/default/assets/leesinq1.png` });
    await http.run("icons.get", { abilities: [644] });
    expect(calls.filter((c) => c.startsWith("abilities"))).toEqual(["abilities 64"]); // 65 has no document
    expect(fetched.filter((u) => u.includes("/champions/"))).toEqual([`${DOCS}champions/64.json`, `${DOCS}champions/65.json`]);
  });

  it("writes nothing: imports and settings belong to the app", async () => {
    const { http } = backend(PUBLISHED);
    const imported = await http.run("build.import", {});
    expect(imported.ok || imported.error.code).toBe("unsupported");
  });
});
