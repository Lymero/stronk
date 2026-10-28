import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import App from "./App.svelte";
import { MockBackend, scenarios } from "./lib/backend/mock.ts";
import { createApp, ICONS_PER_CALL, type Settings, type SettingsStore } from "./lib/state/app.svelte.ts";
import type { PicksStore, SavedPicks } from "./lib/state/picks.ts";

function memory(initial: Settings | null = null): SettingsStore & { saved: Settings | null } {
  return {
    saved: initial,
    load() {
      return this.saved;
    },
    save(settings) {
      this.saved = settings;
    },
  };
}

/** Picks kept between runs, in memory: what a restart would read back. */
function memoryPicks(initial: SavedPicks = {}): PicksStore & { saved: SavedPicks } {
  return {
    saved: initial,
    load() {
      return JSON.parse(JSON.stringify(this.saved)) as SavedPicks;
    },
    save(saved) {
      this.saved = JSON.parse(JSON.stringify(saved)) as SavedPicks;
    },
  };
}

function setup(name: keyof typeof scenarios, store = memory(), picks = memoryPicks()) {
  const backend = new MockBackend(scenarios[name]);
  const app = createApp(backend, store, picks);
  const next = async () => {
    backend.step();
    await app.refresh();
  };
  render(App, { app, onstep: () => void next() });
  return { backend, app, next, store };
}

/** Opens a slot of the build (`Runes`, `Spells`, `Item 2`) to show its options. */
async function openSlot(build: HTMLElement, slot: string) {
  await fireEvent.click(within(build).getByRole("button", { name: new RegExp(`^${slot} `) }));
}

const imports = (backend: MockBackend) => backend.calls.filter((c) => c.id === "build.import").length;

describe("App with MockBackend", () => {
  it("shows Riot's legal notice", async () => {
    const { app } = setup("ranked-jungle");
    await app.refresh();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("Stronk isn't endorsed by Riot Games");
  });

  it("waits outside champion select", async () => {
    const { app } = setup("ranked-jungle");
    await app.refresh();
    expect(await screen.findByText("Waiting for champion select")).toBeInTheDocument();
    expect(screen.getByText("Builds for patch 16.20 are ready.")).toBeInTheDocument();
  });

  it("plans the hovered champion's build once, and lock-in reuses it", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    expect(await screen.findByRole("heading", { name: "Graves" })).toBeInTheDocument();
    await next();
    expect(await screen.findByRole("heading", { name: "Lee Sin" })).toBeInTheDocument();
    await next();
    expect(await screen.findByText("Jungle · Locked in · Final changes")).toBeInTheDocument();
    const planned = backend.calls.filter((c) => c.id === "build.plan").map((c) => c.params);
    expect(planned).toEqual([
      { champion: "Graves", role: "JUNGLE" },
      { champion: "LeeSin", role: "JUNGLE" },
    ]);
  });

  it("shows the build one slot a line, with a verdict only where an option is clearly better", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    const build = screen.getByLabelText("Build");
    for (const slot of ["Runes", "Spells", "Item 1", "Item 2", "Item 3"]) {
      expect(within(build).getByRole("button", { name: new RegExp(`^${slot} `) })).toHaveAttribute("aria-expanded", "false");
    }
    expect(within(build).queryByRole("button", { pressed: true })).toBeNull(); // options stay closed
    expect(within(build).queryByText(/Popular|Most played|No clear difference/)).toBeNull();
    const better = within(build).getByText("▲ +2.1% vs Black Cleaver"); // item 2, the only one
    expect(better).toHaveAttribute(
      "title",
      "Win impact +2.1% against the most played option (95% interval +0.8% to +3.4%), from 640 games",
    );
  });

  it("shows each slot's alternatives with their share, win impact and confidence", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    const build = screen.getByLabelText("Build");
    expect(await within(build).findByText(/16\.20 · 1,840 games · Master\+ · All regions/)).toBeInTheDocument();
    expect(within(build).getByTitle(/Stronk imports the most played options, except where another one is clearly better\./)).toBeInTheDocument();
    for (const slot of ["Runes", "Item 2", "Item 3"]) await openSlot(build, slot);
    expect(within(build).getByText("Electrocute · Domination + Precision")).toBeInTheDocument();
    expect(within(build).getAllByRole("button", { name: /^Death's Dance/ })).toHaveLength(2); // slots 2 and 3
    expect(within(build).getAllByText("▼ −1.8%")).toHaveLength(1); // Death's Dance at slot 3
    expect(within(build).getAllByText("· few games").length).toBeGreaterThan(0);
    // Sundered Sky, the pick at slot 2: 640 of 1,790 picks, +2.1% against Black Cleaver.
    const pick = within(build).getByRole("button", { name: /^Sundered Sky/, pressed: true });
    expect(pick).toHaveTextContent("36% · 640 games");
    expect(pick).toHaveTextContent("▲ +2.1%");
    // The rows come with the plan: nothing else is asked for them.
    expect(backend.calls.filter((c) => c.id === "build.get")).toEqual([]);
  });

  it("imports the option the player clicks instead of Stronk's, until reset", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next(); // Lee Sin, locked in
    const build = screen.getByLabelText("Build");
    await openSlot(build, "Item 2");
    const cleaver = within(build).getByRole("button", { name: /^Black Cleaver/ });
    await fireEvent.click(cleaver);
    expect(cleaver).toHaveAttribute("aria-pressed", "true");
    expect(within(build).getByRole("button", { name: /^Item 2 Black Cleaver/ })).toHaveTextContent("Your pick");
    expect(within(build).getByRole("button", { name: /^Sundered Sky/ })).toHaveTextContent("Stronk's pick");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = () => backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent()).toEqual([{ items: [{ slot: 2, item: 3071 }] }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Imported: Rune page, Item set, Spells.");

    // Changing a pick after the import says so; Stronk's picks come back with one click.
    await openSlot(build, "Spells");
    const smiteIgnite = within(build).getByRole("button", { name: /^Smite · Ignite/ });
    await fireEvent.click(smiteIgnite);
    expect(screen.getByRole("status")).toHaveTextContent("Your picks changed since: import again to use them.");
    await fireEvent.click(screen.getByRole("button", { name: "Use Stronk's picks" }));
    expect(smiteIgnite).toHaveAttribute("aria-pressed", "false");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(sent().at(-1)).toEqual({});
  });

  it("counts the options left out, and marks an item picked for two slots", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    const build = screen.getByLabelText("Build");
    for (const slot of ["Runes", "Item 1", "Item 2", "Item 3"]) await openSlot(build, slot);
    expect(within(build).getByText("Show 2 more")).toBeInTheDocument(); // rune pages
    expect(within(build).getAllByText("Show 1 more")).toHaveLength(3); // items
    const deathsDance = () => within(build).getAllByRole("button", { name: /^Death's Dance/ });
    await fireEvent.click(deathsDance()[0] as HTMLElement); // slot 2
    await fireEvent.click(deathsDance()[1] as HTMLElement); // slot 3
    // On the slot's line and on the option.
    expect(within(build).getAllByText("Also in item 3")).toHaveLength(2);
    expect(within(build).getAllByText("Also in item 2")).toHaveLength(2);
  });

  it("lists every option on request, and imports one past the short list", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    const build = screen.getByLabelText("Build");
    await openSlot(build, "Item 1");
    expect(within(build).queryByRole("button", { name: /^The Collector/ })).toBeNull();
    const more = within(build).getByRole("button", { name: "Show 1 more" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await fireEvent.click(more);
    const collector = within(build).getByRole("button", { name: /^The Collector/ });
    expect(collector).toHaveTextContent("few games");
    await fireEvent.click(collector);
    // Picked, it joins the short list: nothing is left out of that slot any more.
    expect(collector).toHaveAttribute("aria-pressed", "true");
    expect(within(build).queryByRole("button", { name: /^Show/ })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent).toEqual([{ items: [{ slot: 1, item: 6676 }] }]);
  });

  it("keeps picks across restarts, per champion and role, until the patch changes", async () => {
    const saved = memoryPicks();
    const lockIn = async (store: PicksStore) => {
      const backend = new MockBackend(scenarios["ranked-jungle"]);
      const app = createApp(backend, memory(), store);
      await app.refresh();
      for (let i = 0; i < 3; i++) {
        backend.step();
        await app.refresh();
      }
      return { app, backend };
    };
    const first = await lockIn(saved);
    first.app.pick({ slot: 1, item: 6676 });
    first.app.pick({ spells: [14, 11] });
    expect(saved.saved).toEqual({ "LeeSin/JUNGLE": { patch: "16.20", picks: { items: { 1: 6676 }, spells: [14, 11] } } });

    // A restart: the same picks, and the import sends them.
    const second = await lockIn(saved);
    expect(second.app.state.picks).toEqual({ key: "LeeSin/JUNGLE", value: { items: { 1: 6676 }, spells: [14, 11] } });
    await second.app.importBuild();
    expect(second.backend.calls.find((c) => c.id === "build.import")?.params).toEqual({
      spells: [14, 11],
      items: [{ slot: 1, item: 6676 }],
    });
    second.app.resetPicks();
    expect(saved.saved).toEqual({});

    // Picks from another patch, or no longer among the options, are dropped.
    const old = await lockIn(memoryPicks({ "LeeSin/JUNGLE": { patch: "16.19", picks: { items: { 1: 6676 } } } }));
    expect(old.app.state.picks).toBeNull();
    const gone = await lockIn(memoryPicks({ "LeeSin/JUNGLE": { patch: "16.20", picks: { items: { 1: 9999, 2: 6676 } } } }));
    expect(gone.app.state.picks).toEqual({ key: "LeeSin/JUNGLE", value: { items: { 2: 6676 } } });
  });

  it("says when nothing beats the most played build", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next(); // Graves: every choice popular
    expect(await screen.findByTitle(/No option beats the most played one clearly yet/)).toBeInTheDocument();
  });

  it("shows names from the client instead of ids, and readable phases", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    expect(await screen.findByText("Jungle · Hovering · Bans and picks")).toBeInTheDocument();
    expect(screen.getByText("Conqueror · Precision + Inspiration")).toBeInTheDocument();
    expect(screen.getByText("Triumph · Legend: Alacrity · Coup de Grace · Magical Footwear · Cosmic Insight")).toBeInTheDocument();
    expect(screen.getByText("Smite · Flash")).toBeInTheDocument();
    expect(screen.getByText("Sundered Sky")).toBeInTheDocument();
  });

  it("asks the client for each icon on screen once", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    const asked = backend.calls.filter((c) => c.id === "icons.get").map((c) => c.params as Record<string, number[]>);
    const ids = (kind: string) => asked.flatMap((p) => p[kind] ?? []);
    expect(ids("champions")).toEqual([104, 64]); // Graves, then Lee Sin
    expect(ids("items")).toContain(6610);
    expect(ids("runes")).toContain(8010);
    expect(new Set(ids("items")).size).toBe(ids("items").length); // never twice
    const lee = screen.getByLabelText("Champion select").querySelector("img");
    expect(lee?.getAttribute("src")).toMatch(/^data:image\/svg\+xml,/);
  });

  it("asks for many icons in calls of at most 200 ids", async () => {
    const scenario = scenarios["ranked-jungle"];
    const lee = scenario.plans["LeeSin/JUNGLE"];
    const slot = lee.alternatives.items[0];
    const first = slot?.rows[0];
    const many = first ? Array.from({ length: 250 }, (_, i) => ({ ...first, value: 10000 + i })) : [];
    const items = slot ? [{ ...slot, rows: [...slot.rows, ...many] }] : [];
    const plan = { ...lee, alternatives: { ...lee.alternatives, items } };
    const locked = scenario.steps.at(-1);
    const backend = new MockBackend({ ...scenario, steps: locked ? [locked] : [], plans: { "LeeSin/JUNGLE": plan } });
    const app = createApp(backend, memory());
    await app.refresh();
    const sizes = backend.calls
      .filter((c) => c.id === "icons.get")
      .map((c) => Object.values(c.params as Record<string, number[]>).flat().length);
    expect(sizes.length).toBeGreaterThan(1);
    expect(Math.max(...sizes)).toBeLessThanOrEqual(ICONS_PER_CALL);
    expect(app.state.icons.items["10249"]).toBeNull(); // asked; the client has none
  });

  it("loads icons only after an auto-import, so they never delay it", async () => {
    const locked = scenarios["ranked-jungle"].steps.at(-1);
    const backend = new MockBackend({ ...scenarios["ranked-jungle"], steps: locked ? [locked] : [] });
    const app = createApp(backend, memory({ autoImport: true }));
    await app.refresh();
    expect(backend.calls.map((c) => c.id).slice(-2)).toEqual(["build.import", "icons.get"]);
  });

  it("shows stand-ins with the name's first letter when the client gives no icons", async () => {
    const backend = new MockBackend({ ...scenarios["ranked-jungle"], icons: false });
    const app = createApp(backend, memory());
    render(App, { app });
    await app.refresh();
    backend.step();
    backend.step();
    await app.refresh();
    expect(await screen.findByRole("heading", { name: "Lee Sin" })).toBeInTheDocument();
    expect(document.querySelectorAll("img")).toHaveLength(0);
    const avatar = screen.getByLabelText("Champion select").querySelector(".stand-in");
    expect(avatar?.textContent).toBe("L");
    expect(app.state.error).toBeNull(); // cosmetic: never reported
  });

  it("says when every rune page is in use and the rune page was skipped", async () => {
    const { app, next } = setup("pages-full");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Rune page not imported: all your rune pages are in use: delete one in the client, then import again",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Imported: Item set, Spells.");
  });

  it("imports only when asked, unless auto-import is on", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next(); // locked in
    expect(imports(backend)).toBe(0);
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Imported: Rune page, Item set, Spells.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(imports(backend)).toBe(1);
  });

  it("auto-imports once on lock-in when the setting is on, and remembers it", async () => {
    const store = memory();
    const { backend, app, next } = setup("ranked-jungle", store);
    await fireEvent.click(screen.getByLabelText("Auto-import on lock-in"));
    expect(store.saved).toEqual({ autoImport: true });
    await app.refresh();
    await next();
    await next();
    expect(imports(backend)).toBe(0); // hovering only
    await next();
    await app.refresh();
    expect(imports(backend)).toBe(1); // once, not on every refresh
  });

  it("waits calmly for the League client instead of showing an error", async () => {
    const { app } = setup("no-client");
    await app.refresh();
    const waiting = await screen.findByRole("status");
    expect(waiting).toHaveTextContent("League of Legends isn't open");
    expect(waiting).toHaveAttribute("title", "no lockfile: is the League client running?");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("refuses data that failed verification", async () => {
    const { app } = setup("bad-data");
    await app.refresh();
    expect(await screen.findByRole("alert")).toHaveTextContent("hash mismatch");
    expect(screen.queryByLabelText("Build")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "LeeSin" })).toBeInTheDocument(); // no names: the key
  });
});

describe("settings", () => {
  async function openSettings() {
    await fireEvent.click(screen.getByText("Settings"));
    return screen.findAllByRole("radio");
  }

  it("lists item set backups newest first and restores the chosen one after confirming", async () => {
    const { backend } = setup("ranked-jungle");
    const radios = await openSettings();
    const [newest, older] = radios;
    expect(radios).toHaveLength(2);
    expect(newest).toBeChecked();
    await fireEvent.click(older as HTMLElement);
    await fireEvent.click(screen.getByRole("button", { name: "Restore this backup" }));
    expect(backend.calls.some((c) => c.id === "item_sets.restore")).toBe(false); // not before confirming
    const confirm = screen.getByRole("group", { name: "Confirm restore" });
    await fireEvent.click(within(confirm).getByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Restored 30 item sets. The sets they replaced were backed up first.",
    );
    const restores = backend.calls.filter((c) => c.id === "item_sets.restore").map((c) => c.params);
    expect(restores).toEqual([{ backup: "backups/item-sets-0001792318800000-000.json" }]);
    expect(await screen.findAllByRole("radio")).toHaveLength(3); // the replaced sets, backed up
  });

  it("cancelling a restore writes nothing", async () => {
    const { backend } = setup("ranked-jungle");
    await openSettings();
    await fireEvent.click(screen.getByRole("button", { name: "Restore this backup" }));
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(backend.calls.some((c) => c.id === "item_sets.restore")).toBe(false);
    expect(screen.getByRole("button", { name: "Restore this backup" })).toBeInTheDocument();
  });

  it("says when there is nothing to restore", async () => {
    setup("no-client");
    await fireEvent.click(screen.getByText("Settings"));
    expect(await screen.findByText("No backups yet: Stronk hasn't changed your item sets.")).toBeInTheDocument();
  });
});

describe("champion-select notices", () => {
  it("refresh the app without polling", async () => {
    const backend = new MockBackend(scenarios["ranked-jungle"]);
    const app = createApp(backend, memory());
    render(App, { app });
    await app.refresh();
    backend.subscribe(() => void app.refresh());
    backend.step(); // the watcher's notice, nothing else
    expect(await screen.findByRole("heading", { name: "Graves" })).toBeInTheDocument();
  });
});
