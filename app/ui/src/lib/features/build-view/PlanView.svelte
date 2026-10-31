<script lang="ts">
  // The build Stronk would import (ADR-062): on the left the build sheet, every slot's pick by name,
  // Stronk's changes from the most played build marked on their slots; on the right the slot opened from it: the
  // rune page built by clicking runes, or a slot's options against its baseline. Opens on the first
  // slot Stronk changes, else the runes. The start and the first components sit before the items
  // (ADR-071, ADR-072), each a set of items without potions and wards (and boots); boots are
  // their own slot after the first item (ADR-073). The late items are one slot, "Items 4+" (ADR-067): its
  // pick first, then the most played others, as the import lists them.
  import type { GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import Facts from "../../ui/Facts.svelte";
  import { elo, games, type Icons, icon, name, region, runePage } from "../../ui/labels.ts";
  import { type Pick, type Picks, PURCHASES, type Purchase } from "../../state/picks.ts";
  import Loadout from "./Loadout.svelte";
  import OptionTable from "./OptionTable.svelte";
  import RunePage from "./RunePage.svelte";
  import {
    allPopular,
    changes,
    compared,
    explain,
    figure,
    mostPlayed,
    options as ranked,
    selected,
    type Slot,
    verdict,
    wins,
  } from "./options.ts";

  let {
    plan,
    names,
    icons,
    picks,
    imported,
    changed,
    onpick,
  }: {
    plan: Plan;
    names: GameNames | null;
    icons: Icons;
    picks: Picks;
    imported: Imported | null;
    /** The picks changed since that import. */
    changed: boolean;
    onpick: (pick: Pick) => void;
  } = $props();

  const source = $derived([`Patch ${plan.patch}`, games(plan.games), elo(plan.elo), region(plan.region)]);
  const how = $derived(
    (allPopular(plan)
      ? "No option beats the most played one clearly yet, so Stronk imports the most played build."
      : "Stronk imports the most played options, except where another one is ahead of it: clearly better, or its best bet when not yet proven.") +
      " Open a slot and click any option to import it instead.",
  );
  /** Fewer games than this behind a whole build: the board says so before anything else. */
  const THIN = 300;
  /** Items in the late slot's block, and the share an alternative needs to be in a block, as the
   * core's `LATE_ITEMS` and `BLOCK_MIN_SHARE`. */
  const LATE_ITEMS = 6;
  const BLOCK_MIN_SHARE = 0.02;
  const options = $derived(ranked(plan, picks));
  const stronkChanges = $derived(changes(options, plan.alternatives.rune_rows));
  /** The page the import writes: the player's, else Stronk's. */
  const shownPage = $derived(picks.runes ?? plan.runes?.value ?? null);
  /** The client's layout of that page's trees, without which pages are picked whole. */
  const laidOut = $derived(!!names && !!shownPage && !!names.rune_trees[String(shownPage.primary_style)]);

  const page = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return `${primary?.runes[0] ?? ""} (${primary?.title ?? ""} + ${secondary?.title ?? ""})`;
  };
  const spells = (pair: [number, number]) => pair.map((id) => name(names, "spells", id)).join(" + ");
  const item = (id: number) => name(names, "items", id);
  const shown = (kind: "rune_styles" | "runes" | "spells" | "items", id: number) => ({
    src: icon(icons, kind, id),
    name: name(names, kind, id),
  });
  const pageIcons = (p: Page) => [
    ...(p.perks[0] !== undefined ? [shown("runes", p.perks[0])] : []),
    shown("rune_styles", p.sub_style),
  ];
  const spellIcons = (pair: [number, number]) => pair.map((id) => shown("spells", id));
  const itemIcons = (id: number) => [shown("items", id)];

  /** The item each slot imports: the player's pick, else Stronk's. */
  const slotItem = (slot: number) => picks.items[slot] ?? plan.items.find((i) => i.slot === slot)?.value;
  /** "Item 2", or "Items 4+" for the late items (ADR-067). */
  const slotName = (slot: number) => (slot === plan.late_slot ? `Items ${slot}+` : `Item ${slot}`);
  const alsoIn = (slot: number, id: number) =>
    plan.items.filter((i) => i.slot !== slot && slotItem(i.slot) === id).map((i) => slotName(i.slot).toLowerCase());
  /** The late slot's other items as the import lists them after its pick: the core's list
   * (`then`, each with 2% of the slot's games, in Stronk's order: its choice, then its judgement)
   * refilled the same way when the player's picks take some (ADR-069, ADR-070). */
  const lateThen = $derived.by(() => {
    const late = plan.items.find((i) => i.slot === plan.late_slot);
    if (!late) return [];
    const count = Math.max(late.then?.length ?? 0, LATE_ITEMS - 1);
    const taken = new Set(plan.items.map((i) => slotItem(i.slot)));
    const rows = options.items.find((s) => s.slot === late.slot)?.rows ?? [];
    return rows
      .filter((r) => r.share >= BLOCK_MIN_SHARE && !taken.has(r.value))
      .sort((a, b) => Number(b.chosen) - Number(a.chosen) || b.judged - a.judged)
      .map((r) => r.value)
      .slice(0, count);
  });

  const changedKey = (part: "runes" | "rune" | "spells" | Purchase | "boots" | number) =>
    typeof part === "number" ? `item-${part}` : part === "rune" ? "runes" : part;
  const changedKeys = $derived(new Set(stronkChanges.map((c) => changedKey(c.part))));
  const spellPair = $derived(picks.spells ?? plan.spells?.value ?? null);
  /** The boots the import writes: the player's, else Stronk's (ADR-073). */
  const bootsItem = $derived(picks.boots ?? plan.boots?.value ?? null);
  const bootsSlot = (id: number) => ({
    key: "boots",
    name: "Boots",
    value: item(id),
    icons: [shown("items", id)],
    changed: picks.boots !== undefined ? null : gain("boots"), // the gain is Stronk's pick's, not the player's
    yours: picks.boots !== undefined,
  });
  /** The purchases made as a set of items, each named and explained. */
  const PURCHASE: Record<Purchase, { name: string; title: string; about: string }> = {
    start: { name: "Start", title: "Start", about: "Before leaving base, potions and wards aside" },
    // "First back" in the sheet, where "First components" doesn't fit beside a badge.
    components: { name: "First back", title: "First components", about: "The first planned trip back (not after a death), potions, wards and boots aside" },
  };
  const isPurchase = (key: string): key is Purchase => (PURCHASES as readonly string[]).includes(key);
  const set = (items: number[]) => items.map(item).join(" + ");
  const setIcons = (items: number[]) => items.map((id) => shown("items", id));
  /** What the import writes for a purchase: the player's pick, else Stronk's. */
  const bought = (key: Purchase) => picks[key] ?? plan[key]?.value ?? null;
  const pickPurchase = (key: Purchase, items: number[]): Pick => (key === "start" ? { start: items } : { components: items });

  /** Stronk's change in a slot, as its badge reads: proven ("▲ +2.1") or its best bet ("Best bet
   * +2.7"); the largest when a rune page changes in several rows. */
  const gain = (key: string) => {
    const found = stronkChanges
      .filter((x) => changedKey(x.part) === key && x.row.wpa != null)
      .sort((a, b) => (b.row.wpa ?? 0) - (a.row.wpa ?? 0))[0];
    return found ? { text: wins(found.row.wpa ?? 0), bet: found.row.confidence === "best_bet" } : null;
  };
  const slots = $derived([
    ...(shownPage
      ? [
          {
            key: "runes",
            name: "Runes",
            value: name(names, "runes", shownPage.perks[0] ?? 0),
            detail: `${name(names, "rune_styles", shownPage.primary_style)} + ${name(names, "rune_styles", shownPage.sub_style)}`,
            icons: [shown("runes", shownPage.perks[0] ?? 0)],
            changed: picks.runes !== undefined ? null : gain("runes"), // the gain is Stronk's pick's, not the player's
            yours: picks.runes !== undefined,
          },
        ]
      : []),
    ...(spellPair
      ? [
          {
            key: "spells",
            name: "Spells",
            value: spells(spellPair),
            icons: spellPair.map((id) => shown("spells", id)),
            changed: picks.spells !== undefined ? null : gain("spells"), // the gain is Stronk's pick's, not the player's
            yours: picks.spells !== undefined,
          },
        ]
      : []),
    ...PURCHASES.flatMap((key) => {
      const items = bought(key);
      if (!items) return [];
      return [
        {
          key,
          name: PURCHASE[key].name,
          value: set(items),
          icons: setIcons(items),
          changed: picks[key] !== undefined ? null : gain(key), // the gain is Stronk's pick's, not the player's
          yours: picks[key] !== undefined,
        },
      ];
    }),
    ...plan.items.flatMap((c) => {
      const id = slotItem(c.slot) ?? c.value;
      const then = c.slot === plan.late_slot ? lateThen : [];
      const slot = {
        key: `item-${c.slot}`,
        name: slotName(c.slot),
        value: item(id),
        ...(then.length ? { detail: `then ${then.map(item).join(", ")}` } : {}),
        icons: [shown("items", id)],
        changed: picks.items[c.slot] !== undefined ? null : gain(`item-${c.slot}`), // the gain is Stronk's pick's, not the player's
        yours: picks.items[c.slot] !== undefined,
      };
      // Boots after the first item, when they're usually bought (ADR-073).
      return c === plan.items[0] && bootsItem !== null ? [slot, bootsSlot(bootsItem)] : [slot];
    }),
  ]);

  let chosenFocus = $state<string | null>(null);
  const firstKey = $derived(stronkChanges[0] ? changedKey(stronkChanges[0].part) : shownPage ? "runes" : "item-1");
  const focus = $derived(chosenFocus ?? firstKey);
  const focusedItem = $derived(focus.startsWith("item-") ? Number(focus.slice(5)) : null);
  const itemSlot = $derived(
    focusedItem === null ? null : (options.items.find((s) => s.slot === focusedItem) ?? { slot: focusedItem, rows: [], more: 0 }),
  );

  /** What a slot's header says: what its numbers are compared with, a clear result against it,
   * and "Your pick" when the import writes the player's choice (ADR-060). */
  function note<T>(slot: Slot<T>, label: (value: T) => string): { text: string; tone: string; title: string } | null {
    const row = selected(slot);
    if (!row) return null;
    // Spells have no estimates at all: their blanks aren't a lack of games.
    if (slot.rows.every((r) => r.wpa === null && (r.confidence === "most_played" || r.confidence === "not_estimated")))
      return row.chosen
        ? { text: "Not measured yet", tone: "muted", title: "No win impact is estimated for these yet" }
        : { text: "Your pick", tone: "picked", title: "" };
    const clear = verdict(row);
    const base = mostPlayed(slot);
    const against = base && compared(slot) ? label(base.value) : null;
    if (row.chosen && clear && base !== row && against)
      return { text: `${clear.text} vs ${against}`, tone: clear.tone, title: explain(row) };
    if (row.chosen) return against ? { text: `Compared with ${against}`, tone: "muted", title: explain(row) } : null;
    const number = figure(row);
    const text = number && against ? `Your pick: ${number} vs ${against}` : "Your pick";
    return { text, tone: "picked", title: explain(row) };
  }

  const panel = $derived.by(() => {
    if (focus === "runes") return { title: "Runes", note: laidOut ? null : note(options.runes, page), extra: "" };
    if (focus === "spells") return { title: "Summoner spells", note: note(options.spells, spells), extra: "" };
    if (focus === "boots") return { title: "Boots", note: note(options.boots, item), extra: "The first upgrade" };
    if (isPurchase(focus)) return { title: PURCHASE[focus].title, note: note(options[focus], set), extra: PURCHASE[focus].about };
    const slotNo = focusedItem ?? 0;
    const also = alsoIn(slotNo, slotItem(slotNo) ?? 0);
    return {
      title: slotName(slotNo),
      note: itemSlot ? note(itemSlot, item) : null,
      extra: also.length ? `Also in ${also.join(" and ")}` : "",
    };
  });

  const parts = $derived(
    imported
      ? ([
          ["Rune page", imported.runes],
          ["Item set", imported.item_set],
          ["Spells", imported.spells],
        ] as [string, Outcome][])
      : [],
  );
  const done = $derived(parts.filter(([, o]) => o.status === "imported").map(([part]) => part));
  const skipped = $derived(parts.flatMap(([part, o]) => (o.status === "skipped" ? [{ part, reason: o.reason }] : [])));
</script>

<section class="plan" aria-label="Build">
  {#if imported}
    {#each skipped as s (s.part)}
      <p class="skipped" role="alert">{s.part} not imported: {s.reason}</p>
    {/each}
    <p class="result" class:stale={changed} role="status">
      {done.length ? `Imported: ${done.join(", ")}.` : "Nothing imported."}
      {#if imported.item_set_backup}<span title={imported.item_set_backup}>Your item sets were backed up first.</span>{/if}
      {#if changed}<strong>Your picks changed since: import again to use them.</strong>{/if}
    </p>
  {/if}

  <div class="columns">
  <div class="card loadout-card">
    {#if plan.games < THIN}
      <p class="thin" role="note">
        Only {games(plan.games)} for this champion and role: too few to measure, so Stronk imports the most played build.
      </p>
    {/if}
    <Loadout {slots} {focus} onfocus={(k) => (chosenFocus = k)} />
  </div>

  <div class="card panel" id="slot-panel" role="tabpanel" tabindex="-1" aria-label={panel.title}>
    <!-- The rune trees head themselves: the panel's title would only take height. -->
    <header class:quiet={focus === "runes" && laidOut}>
      <h3>{panel.title}</h3>
      {#if panel.extra}<span class="also">{panel.extra}</span>{/if}
      {#if panel.note}<span class="note {panel.note.tone}" title={panel.note.title}>{panel.note.text}</span>{/if}
    </header>

    {#if focus === "runes"}
      {#if shownPage && laidOut && names}
        <RunePage {plan} page={shownPage} stronk={plan.runes?.value ?? null} {names} {icons} onpage={(p) => onpick({ runes: p })} />
      {:else}
        <OptionTable slot={options.runes} label={page} icons={pageIcons} onpick={(p) => onpick({ runes: p })} />
      {/if}
    {:else if focus === "boots"}
      <OptionTable slot={options.boots} label={item} icons={itemIcons} onpick={(id) => onpick({ boots: id })} />
    {:else if isPurchase(focus)}
      {@const key = focus}
      {#key key}
        <OptionTable slot={options[key]} label={set} icons={setIcons} onpick={(items) => onpick(pickPurchase(key, items))} />
      {/key}
    {:else if focus === "spells"}
      <OptionTable slot={options.spells} label={spells} icons={spellIcons} onpick={(pair) => onpick({ spells: pair })} />
    {:else if itemSlot}
      {#key itemSlot.slot}
        <OptionTable
          slot={itemSlot}
          label={item}
          icons={itemIcons}
          onpick={(id) => onpick({ slot: itemSlot.slot, item: id })}
          elsewhere={(id) => {
            const also = alsoIn(itemSlot.slot, id);
            return also.length ? `in ${also.join(" and ")}` : null;
          }}
        />
      {/key}
    {/if}

    <p class="meta">
      <Facts facts={source} />
      <span class="how" title={how} aria-label={how}>How Stronk picks</span>
    </p>
    <p class="legend">
      <span>Numbers are wins per 100 games against the baseline, the most played option (0)</span>
      <span><span class="clear">▲</span> colour only when clearly better or worse</span>
      <span><span class="bet">Best bet</span>: ahead on the numbers so far, not yet proven</span>
      <span>%: share of games</span>
      <span>No number: too few games</span>
    </p>
  </div>
  </div>
</section>

<style>
  .plan {
    display: grid;
    gap: var(--space-3);
  }
  .card {
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .columns {
    display: grid;
    grid-template-columns: 340px minmax(0, 1fr);
    gap: var(--space-3);
    /* Both cards as tall as the taller one: their bottoms line up. */
    align-items: stretch;
  }
  .thin {
    margin: 0;
    padding: var(--space-1) var(--space-2) 0;
    color: var(--color-warning);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .loadout-card {
    display: grid;
    align-content: start;
    gap: var(--space-3);
    padding: var(--space-3);
  }
  @media (max-width: 900px) {
    .columns {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    align-items: baseline;
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .how {
    border-bottom: 1px dotted var(--color-muted);
    cursor: help;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .panel header {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-3);
    align-items: baseline;
  }
  .quiet:not(:has(.note, .also)) {
    display: none;
  }
  h3 {
    margin: 0;
    font-size: var(--text-lg);
  }
  .also {
    color: var(--color-warning);
    font-size: var(--text-sm);
  }
  .note {
    margin-left: auto;
    font-size: var(--text-sm);
    font-variant-numeric: tabular-nums;
  }
  .note.muted {
    color: var(--color-muted);
  }
  .note.positive {
    color: var(--color-positive);
    font-weight: 600;
  }
  .note.negative {
    color: var(--color-negative);
    font-weight: 600;
  }
  .note.bet {
    color: var(--color-accent);
    font-weight: 600;
  }
  .note.picked {
    color: var(--color-accent);
    font-weight: 600;
  }
  /* The patch line and legend close the panel at its bottom, however short the slot. */
  .panel .meta {
    margin-top: auto;
    padding-top: var(--space-3);
    border-top: 1px solid var(--color-border);
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    margin: calc(-1 * var(--space-2)) 0 0;
    color: var(--color-muted);
    font-size: var(--text-xs);
  }
  .legend .bet {
    color: var(--color-accent);
    font-weight: 600;
  }
  .legend .clear {
    color: var(--color-positive);
  }
  .result {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-positive-bg);
  }
  .result.stale {
    background: var(--color-warning-bg);
  }
  .result strong {
    display: block;
    color: var(--color-warning);
  }
  .skipped {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
</style>
