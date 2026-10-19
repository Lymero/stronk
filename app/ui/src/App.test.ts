import { fireEvent, render, screen, within } from "@testing-library/svelte";
import { describe, expect, it } from "vitest";
import App from "./App.svelte";
import { MockBackend, scenarios } from "./lib/backend/mock.ts";
import { createApp, type Settings, type SettingsStore } from "./lib/state/app.svelte.ts";
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

const imports = (backend: MockBackend) => backend.calls.filter((c) => c.id === "build.import").length;

describe("App with MockBackend", () => {
  it("waits outside champion select", async () => {
    const { app } = setup("ranked-jungle");
    await app.refresh();
    expect(await screen.findByText("Waiting for champion select")).toBeInTheDocument();
    expect(screen.getByText("Data 16.20")).toBeInTheDocument();
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

  it("labels each choice Popular or Clearly better with its win impact", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    expect(await screen.findAllByText("Popular")).toHaveLength(4); // runes, spells, items 1 and 3
    const better = screen.getByText("Clearly better · +2.1% win");
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
    expect(await within(build).findByText("Patch 16.20 · 1,840 games · Master+ · All regions")).toBeInTheDocument();
    expect(within(build).getByText("Electrocute · Domination + Precision")).toBeInTheDocument();
    expect(within(build).getAllByText("Death's Dance", { selector: ".name" })).toHaveLength(2); // slots 2 and 3
    expect(within(build).getAllByText("Clearly worse")).toHaveLength(1); // Death's Dance at slot 3
    expect(within(build).getAllByText("Too few games").length).toBeGreaterThan(0);
    expect(within(build).getByText(/Stronk imports the most played options, except where another one is clearly better\./)).toBeInTheDocument();
    // Sundered Sky, the pick at slot 2: 640 of 1,790 picks, +2.1% against Black Cleaver.
    const pick = within(build).getAllByText("Stronk's pick").map((el) => el.closest("li")?.textContent ?? "");
    expect(pick.some((t) => t.includes("Sundered Sky") && t.includes("36% · 640 games") && t.includes("+2.1% win"))).toBe(true);
    // The rows come with the plan: nothing else is asked for them.
    expect(backend.calls.filter((c) => c.id === "build.get")).toEqual([]);
  });

  it("imports the option the player clicks instead of Stronk's, until reset", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next(); // Lee Sin, locked in
    const build = screen.getByLabelText("Build");
    const cleaver = within(build).getByRole("button", { name: /^Black Cleaver/ }); // slot 2
    await fireEvent.click(cleaver);
    expect(cleaver).toHaveAttribute("aria-pressed", "true");
    expect(within(cleaver).getByText("Your pick")).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = () => backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent()).toEqual([{ items: [{ slot: 2, item: 3071 }] }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Imported: Rune page, Item set, Spells.");

    // Changing a pick after the import says so; Stronk's picks come back with one click.
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
    expect(within(build).getByText("2 more options, each played less")).toBeInTheDocument(); // rune pages
    expect(within(build).getAllByText("1 more option, each played less")).toHaveLength(3); // items
    const deathsDance = () => within(build).getAllByRole("button", { name: /^Death's Dance/ });
    await fireEvent.click(deathsDance()[0] as HTMLElement); // slot 2
    await fireEvent.click(deathsDance()[1] as HTMLElement); // slot 3
    expect(within(build).getByText("Also in item 3")).toBeInTheDocument();
    expect(within(build).getByText("Also in item 2")).toBeInTheDocument();
  });

  it("lists every option on request, and imports one past the short list", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    const build = screen.getByLabelText("Build");
    expect(within(build).queryByRole("button", { name: /^The Collector/ })).toBeNull();
    const slot1 = within(build).getAllByRole("button", { name: "1 more option, each played less" })[0] as HTMLElement;
    expect(slot1).toHaveAttribute("aria-expanded", "false");
    await fireEvent.click(slot1);
    const collector = within(build).getByRole("button", { name: /^The Collector/ });
    expect(collector).toHaveTextContent("Too few games");
    await fireEvent.click(collector);
    // Picked, it joins the short list: nothing is left out of that slot any more.
    expect(collector).toHaveAttribute("aria-pressed", "true");
    expect(within(build).getAllByRole("button", { name: "1 more option, each played less" })).toHaveLength(2);
    expect(within(build).queryByRole("button", { name: "Fewer options" })).toBeNull();
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
    expect(await screen.findByText(/No option beats the most played one clearly yet/)).toBeInTheDocument();
  });

  it("shows names from the client instead of ids, and readable phases", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    expect(await screen.findByText("Jungle · Hovering · Bans and picks")).toBeInTheDocument();
    expect(screen.getByText("Conqueror · Triumph · Legend: Alacrity · Coup de Grace")).toBeInTheDocument();
    expect(screen.getByText("Magical Footwear · Cosmic Insight")).toBeInTheDocument();
    expect(screen.getByText("Attack Speed · Adaptive Force · Health Scaling")).toBeInTheDocument();
    expect(screen.getByText("Smite · Flash")).toBeInTheDocument();
    expect(screen.getByText("Sundered Sky")).toBeInTheDocument();
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

  it("says when the League client isn't running", async () => {
    const { app } = setup("no-client");
    await app.refresh();
    expect(await screen.findByRole("alert")).toHaveTextContent("is the League client running?");
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
