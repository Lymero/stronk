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

/** The facts of a line, one per item: "Jungle", "Locked in"... */
const facts = (el: HTMLElement) => [...el.querySelectorAll(".facts > span")].map((s) => s.textContent);

/** The sheet's tab for a slot: "Item 2", "Runes", "Spells". */
const tab = (slot: string) => screen.getByRole("tab", { name: new RegExp(`^${slot.replace("+", "\\+")}:`) });
/** Opens a slot from the sheet; its options, in the panel beside it. */
async function open(slot: string) {
  await fireEvent.click(tab(slot));
  return within(screen.getByRole("tabpanel", { name: slot === "Spells" ? "Summoner spells" : slot }));
}
/** An option's row in the open slot. */
const option = (panel: ReturnType<typeof within>, name: string) =>
  panel.getByRole("radio", { name: new RegExp(`^${name.replace(/[+.()]/g, "\\$&")},`) });

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
    expect(await screen.findByText("Locked in")).toBeInTheDocument();
    expect(facts(screen.getByLabelText("Champion select"))).toEqual(["Jungle", "Locked in", "Final changes"]);
    const planned = backend.calls.filter((c) => c.id === "build.plan").map((c) => c.params);
    expect(planned).toEqual([
      { champion: "Graves", role: "JUNGLE" },
      { champion: "LeeSin", role: "JUNGLE" },
    ]);
  });

  it("shows the build by name and one slot's options against its baseline, coloured only when clear", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    const build = screen.getByLabelText("Build");
    expect(await within(build).findByText("Patch 16.20")).toBeInTheDocument();
    expect(facts(within(build).getByText("Patch 16.20").parentElement as HTMLElement)).toEqual([
      "Patch 16.20",
      "1,840 games",
      "Master+",
      "All regions",
    ]);
    expect(within(build).getByTitle(/Stronk imports the most played options, except where another one is ahead of it: clearly better, or its best bet when not yet proven\./)).toBeInTheDocument();
    // The sheet: every slot's pick by name, Stronk's change marked with its gain.
    expect(screen.getAllByRole("tab").map((t) => t.getAttribute("aria-label"))).toEqual([
      "Runes: Conqueror",
      "Spells: Smite + Flash",
      "Start: Scorchclaw Pup",
      "Item 1: Eclipse",
      "Item 2: Sundered Sky, Stronk's change +2.1",
      "Item 3: Guardian Angel, Stronk's best bet +1.2",
      "Items 4+: Sterak's Gage",
    ]);
    // It opens on the slot Stronk changes.
    expect(tab("Item 2")).toHaveAttribute("aria-selected", "true");
    const item2 = within(screen.getByRole("tabpanel", { name: "Item 2" }));
    const better = item2.getByText("▲ +2.1 wins per 100 vs Black Cleaver"); // the only clear one
    expect(better).toHaveClass("positive");
    expect(better).toHaveAttribute(
      "title",
      "+2.1 wins per 100 games against the most played option. Likely between +0.8 and +3.4 (95%). Clearly better: the difference holds once false discoveries are controlled.",
    );
    const sky = option(item2, "Sundered Sky");
    expect(sky).toHaveAttribute("aria-checked", "true");
    expect(sky).toHaveTextContent("▲ +2.1");
    expect(sky).not.toHaveTextContent("±");
    expect(sky).toHaveTextContent("640 games"); // the games behind it
    const cleaver = option(item2, "Black Cleaver");
    expect(cleaver).toHaveTextContent("baseline");
    expect(cleaver.querySelector(".num")).toHaveTextContent(/^0$/);
    expect(option(item2, "Death's Dance").querySelector(".num")).not.toHaveClass("positive"); // unclear: grey
    // Spells have no estimates: their header says so, as no lack of games is meant.
    expect((await open("Spells")).getByText("Not measured yet")).toBeInTheDocument();
    const spellNumbers = [...screen.getByRole("tabpanel").querySelectorAll(".row .num")].map((n) => n.textContent);
    expect(spellNumbers).toEqual(["", ""]); // no estimates, no numbers
    // Item 3: Guardian Angel is ahead of Sterak's Gage, not yet clearly: Stronk's best bet.
    const item3 = await open("Item 3");
    expect(item3.getByText("▼ −1.8")).toHaveClass("negative");
    expect(item3.getByText("Best bet +1.2 wins per 100 vs Sterak's Gage")).toHaveClass("bet");
    expect(option(item3, "Guardian Angel")).toHaveTextContent("Best bet");
    expect(option(item3, "Guardian Angel")).toHaveAttribute("aria-checked", "true");
    expect(option(item3, "Guardian Angel").querySelector(".num")).not.toHaveClass("positive"); // not proven: no green
    expect(screen.getByRole("tab", { name: /^Item 3:/ })).toHaveTextContent("Best bet +1.2");
    expect(within(build).queryByText(/Popular|Most played|No clear difference/)).toBeNull();
    // No summary of the changes: each is marked on its slot in the sheet.
    expect(within(build).queryByLabelText("What Stronk changes")).toBeNull();
    // The rows come with the plan: nothing else is asked for them.
    expect(backend.calls.filter((c) => c.id === "build.get")).toEqual([]);
  });

  it("lays the rune page out as the client does, the focused row's options beside it", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    await open("Runes");
    const tree = within(screen.getByLabelText("Build")).getByLabelText("Rune page");
    const precision = within(tree).getByRole("region", { name: "Precision, primary" });
    expect(precision.querySelectorAll(".line")).toHaveLength(4);
    expect(precision.querySelector(".line")?.querySelectorAll(".rune")).toHaveLength(4); // keystones
    expect(within(tree).getByRole("region", { name: "Inspiration, secondary" }).querySelectorAll(".line")).toHaveLength(3);
    expect(within(tree).getByRole("region", { name: "Shards" }).querySelectorAll(".line")).toHaveLength(3);
    expect(tree.querySelectorAll(".rune.on")).toHaveLength(9); // the page's nine choices
    // The keystones are in focus first, as a list read like the item lists.
    const row = (title: string) => within(within(tree).getByRole("region", { name: title }));
    expect(option(row("Precision, keystone"), "Conqueror")).toHaveAttribute("aria-checked", "true");
    // Clicking a rune brings its row into focus.
    await fireEvent.click(within(precision).getByRole("button", { name: "Triumph" }));
    expect(option(row("Precision, row 1"), "Triumph")).toHaveTextContent("baseline");
    expect(option(row("Precision, row 1"), "Presence of Mind").querySelector(".num")).toHaveTextContent("−0.6");
    await fireEvent.click(within(precision).getByRole("button", { name: "Coup de Grace" }));
    expect(option(row("Precision, row 3"), "Last Stand").querySelector(".num")).toHaveTextContent(/^$/); // short of games
    await fireEvent.click(within(tree).getByRole("button", { name: "Adaptive Force", pressed: true }));
    expect(option(row("Flex shard"), "Move Speed").querySelector(".num")).toHaveTextContent("−1.1");
    // Secondary runes are measured as a pair: the tree's pairs, each with both runes. No other pair
    // has enough games to compare with, so no 0 either.
    await fireEvent.click(within(tree).getByRole("button", { name: "Magical Footwear" }));
    const pairs = row("Inspiration, pairs");
    expect(pairs.getAllByRole("radio").map((r) => r.getAttribute("aria-label")?.split(",")[0])).toEqual([
      "Magical Footwear + Cosmic Insight",
      "Biscuit Delivery + Cosmic Insight",
    ]);
    expect(option(pairs, "Magical Footwear + Cosmic Insight")).toHaveAttribute("aria-checked", "true");
    expect(option(pairs, "Magical Footwear + Cosmic Insight").querySelectorAll(".icon")).toHaveLength(2);
    expect(option(pairs, "Magical Footwear + Cosmic Insight").querySelector(".num")).toHaveTextContent(/^$/);
    // Picking a pair sets both runes.
    await fireEvent.click(option(pairs, "Biscuit Delivery + Cosmic Insight"));
    const inspiration = within(within(tree).getByRole("region", { name: "Inspiration, secondary" }));
    expect(inspiration.getByRole("button", { name: "Biscuit Delivery" })).toHaveAttribute("aria-pressed", "true");
    expect(inspiration.getByRole("button", { name: "Magical Footwear" })).toHaveAttribute("aria-pressed", "false");
    const asked = backend.calls.filter((c) => c.id === "icons.get").flatMap((c) => (c.params as { runes?: number[] }).runes ?? []);
    expect(asked).toContain(8021); // Fleet Footwork: in no published page, its icon still asked for
  });

  it("moves the secondary runes to any two rows, replacing the one picked first", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    await open("Runes");
    const secondary = () =>
      within(within(screen.getByLabelText("Build")).getByRole("region", { name: "Inspiration, secondary" }));
    const lit = () => secondary().getAllByRole("button", { pressed: true }).map((b) => /^[^,+−]*?(?=,| [+−]|$)/.exec(b.getAttribute("aria-label") ?? "")?.[0]);
    expect(lit()).toEqual(["Magical Footwear", "Cosmic Insight"]); // rows 1 and 3
    await fireEvent.click(secondary().getByRole("button", { name: /^Biscuit Delivery/ })); // row 2: the upper one goes
    expect(lit()).toEqual(["Biscuit Delivery", "Cosmic Insight"]);
    await fireEvent.click(secondary().getByRole("button", { name: /^Hextech Flashtraption/ })); // row 1: Cosmic Insight goes
    expect(lit()).toEqual(["Hextech Flashtraption", "Biscuit Delivery"]);
  });

  it("builds a rune page by clicking runes, as the client does", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    await open("Runes");
    const build = screen.getByLabelText("Build");
    const tree = () => within(build).getByLabelText("Rune page");
    const click = async (name: RegExp) => fireEvent.click(within(tree()).getByRole("button", { name }));
    await click(/^Lethal Tempo/); // a keystone with no published page
    await click(/^Presence of Mind/); // row 1
    await click(/^Biscuit Delivery/); // secondary row 2: replaces the one picked first
    await click(/^Approach Velocity/); // secondary row 3: replaces Cosmic Insight, in its row
    await click(/^Move Speed/); // flex shard
    expect(within(tree()).getByRole("button", { name: /^Lethal Tempo/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(tree()).getByRole("button", { name: /^Conqueror/ }).classList).toContain("stronk"); // Stronk's, marked
    // A pair nobody played is still listed, picked, with no number.
    await click(/^Approach Velocity/); // picked already: brings the secondary tree into focus
    const focused = within(within(tree()).getByRole("region", { name: "Inspiration, pairs" }));
    expect(option(focused, "Biscuit Delivery + Approach Velocity")).toHaveAttribute("aria-checked", "true");
    expect(option(focused, "Biscuit Delivery + Approach Velocity").querySelector(".num")).toHaveTextContent(/^$/);
    // Another secondary tree: its most played pair; another primary: its most played page.
    const switcher = (which: string) => within(within(tree()).getByRole("group", { name: `${which} tree` }));
    await fireEvent.click(switcher("Secondary").getByRole("button", { name: "Resolve" }));
    expect(within(tree()).getByRole("region", { name: "Resolve, secondary" })).toBeInTheDocument();
    await fireEvent.click(screen.getByRole("button", { name: "Use Stronk's picks" }));
    await click(/^Biscuit Delivery/);
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent).toEqual([
      // Magical Footwear (row 1) was picked before Cosmic Insight (row 3): Biscuit Delivery (row 2) replaces it.
      { runes: { primary_style: 8000, sub_style: 8300, perks: [8010, 9111, 9104, 8014, 8345, 8347, 5005, 5008, 5001] } },
    ]);
    await fireEvent.click(switcher("Primary").getByRole("button", { name: "Domination" }));
    expect(within(tree()).getByRole("region", { name: "Domination, primary" })).toBeInTheDocument();
    expect(within(tree()).getByRole("button", { name: /^Electrocute/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("picks whole pages when the client gives no tree layout", async () => {
    const backend = new MockBackend({ ...scenarios["ranked-jungle"], names: { code: "unavailable", message: "no names" } });
    const app = createApp(backend, memory(), memoryPicks());
    render(App, { app });
    await app.refresh();
    for (let i = 0; i < 3; i++) {
      backend.step();
      await app.refresh();
    }
    const runes = await open("Runes");
    expect(runes.queryByLabelText("Rune page")).toBeNull();
    expect(runes.getAllByRole("radio", { checked: true })).toHaveLength(1);
  });

  it("imports the option the player clicks instead of Stronk's, until reset", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next(); // Lee Sin, locked in
    const item2 = await open("Item 2");
    await fireEvent.click(option(item2, "Black Cleaver"));
    expect(option(item2, "Black Cleaver")).toHaveAttribute("aria-checked", "true");
    expect(item2.getByText(/^Your pick/)).toBeInTheDocument();
    expect(option(item2, "Sundered Sky")).toHaveTextContent("Stronk's pick");
    expect(tab("Item 2")).toHaveAccessibleName(/^Item 2: Black Cleaver, your pick$/);
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = () => backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent()).toEqual([{ items: [{ slot: 2, item: 3071 }] }]);
    expect(await screen.findByRole("status")).toHaveTextContent("Imported: Rune page, Item set, Spells.");

    // Changing a pick after the import says so; Stronk's picks come back with one click.
    const spells = await open("Spells");
    await fireEvent.click(option(spells, "Smite + Ignite"));
    expect(screen.getByRole("status")).toHaveTextContent("Your picks changed since: import again to use them.");
    await fireEvent.click(screen.getByRole("button", { name: "Use Stronk's picks" }));
    expect(option(spells, "Smite + Ignite")).toHaveAttribute("aria-checked", "false");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(sent().at(-1)).toEqual({});
  });

  it("lists the late items as one slot, its pick first, then the most played others", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    // In Stronk's order: Maw, ahead of Sterak's Gage; then those it knows nothing against, most
    // played first; Death's Dance, behind, last. Guardian Angel, Stronk's item 3, is left out,
    // and Trinity Force, under 2%.
    expect(tab("Items 4+")).toHaveTextContent("then Maw of Malmortius, Serylda's Grudge, Black Cleaver, Death's Dance");
    const late = await open("Items 4+");
    expect(screen.getByRole("tabpanel", { name: "Items 4+" })).toBeInTheDocument();
    expect(option(late, "Sterak's Gage")).toHaveTextContent("baseline");
    expect(option(late, "Guardian Angel")).toHaveTextContent("in item 3");
    // The player's pick overrules Stronk: Maw at the head, Stronk's Sterak's Gage next.
    await fireEvent.click(option(late, "Maw of Malmortius"));
    expect(tab("Items 4+")).toHaveTextContent("then Sterak's Gage, Serylda's Grudge, Black Cleaver, Death's Dance");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(backend.calls.filter((c) => c.id === "build.import").at(-1)?.params).toEqual({ items: [{ slot: 4, item: 3156 }] });
  });

  it("shows the start, potions and wards aside, and imports the one picked", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    const start = await open("Start");
    expect(option(start, "Scorchclaw Pup")).toHaveTextContent("baseline");
    expect(option(start, "Gustwalker Hatchling").querySelector(".num")).toHaveTextContent("−0.4");
    expect(screen.getByRole("tabpanel", { name: "Start" })).toHaveTextContent("Before leaving base, potions and wards aside");
    await fireEvent.click(option(start, "Gustwalker Hatchling"));
    expect(tab("Start")).toHaveTextContent("Your pick");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    expect(backend.calls.filter((c) => c.id === "build.import").at(-1)?.params).toEqual({ start: [1102] });
  });

  it("marks an item picked for two slots", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    await fireEvent.click(option(await open("Item 2"), "Death's Dance"));
    const item3 = await open("Item 3");
    await fireEvent.click(option(item3, "Death's Dance"));
    expect(item3.getByText("Also in item 2")).toBeInTheDocument();
    expect(option(item3, "Death's Dance")).toHaveTextContent("in item 2");
    expect((await open("Item 2")).getByText("Also in item 3")).toBeInTheDocument();
  });

  it("shows rarely played options on request, and imports one", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    const item1 = await open("Item 1");
    expect(option(item1, "The Collector")).toBeInTheDocument(); // 5%: shown
    expect(item1.queryByRole("radio", { name: /^Trinity Force/ })).toBeNull(); // 1%: behind "Show 1 more"
    const more = item1.getByRole("button", { name: "Show 1 more, rarely played" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await fireEvent.click(more);
    await fireEvent.click(option(item1, "Trinity Force"));
    expect(option(item1, "Trinity Force")).toHaveAttribute("aria-checked", "true");
    await fireEvent.click(screen.getByRole("button", { name: "Import" }));
    const sent = backend.calls.filter((c) => c.id === "build.import").map((c) => c.params);
    expect(sent).toEqual([{ items: [{ slot: 1, item: 3078 }] }]);
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
    // A board this thin says so first.
    expect(screen.getByRole("note")).toHaveTextContent("Only 140 games for this champion and role: too few to measure");
  });

  it("shows names from the client instead of ids, and readable phases", async () => {
    const { app, next } = setup("ranked-jungle");
    await app.refresh();
    await next();
    await next();
    expect(await screen.findByText("Bans and picks")).toBeInTheDocument();
    expect(facts(screen.getByLabelText("Champion select"))).toEqual(["Jungle", "Hovering", "Bans and picks"]);
    expect(tab("Runes")).toHaveTextContent("Precision + Inspiration");
    await open("Runes");
    const tree = screen.getByLabelText("Rune page");
    for (const rune of ["Conqueror", "Triumph", "Legend: Alacrity", "Coup de Grace", "Magical Footwear", "Cosmic Insight"]) {
      expect(within(tree).getByRole("button", { name: new RegExp(`^${rune}`), pressed: true })).toBeInTheDocument();
    }
    expect(within(tree).getByRole("heading", { name: "Precision" })).toBeInTheDocument();
    expect(option(await open("Spells"), "Smite + Flash")).toHaveAttribute("aria-checked", "true");
    expect(document.body.textContent).not.toContain("·"); // no middle dots anywhere
    expect(tab("Item 2")).toHaveTextContent("Sundered Sky");
  });

  it("asks the client for each icon on screen once", async () => {
    const { backend, app, next } = setup("ranked-jungle");
    await app.refresh();
    for (let i = 0; i < 3; i++) await next();
    const asked = backend.calls.filter((c) => c.id === "icons.get").map((c) => c.params as Record<string, number[]>);
    const ids = (kind: string) => asked.flatMap((p) => p[kind] ?? []);
    expect(ids("champions")).toEqual([104, 64]); // Graves, then Lee Sin
    expect(ids("items")).toContain(6610);
    expect(ids("items")).toEqual(expect.arrayContaining([1101, 1102, 1103])); // the starts
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
