<script lang="ts">
  import type { Build, Choice, GameNames, Imported, Outcome, Page, Plan } from "../../backend/backend.ts";
  import { elo, games, name, region, runePage } from "../../ui/labels.ts";
  import OptionList from "./OptionList.svelte";
  import { allPopular, alternatives } from "./options.ts";

  let {
    plan,
    build,
    names,
    imported,
    onimport,
  }: {
    plan: Plan;
    /** The build file behind the plan, for the alternatives; the choices alone without it. */
    build: Build | null;
    names: GameNames | null;
    imported: Imported | null;
    onimport: () => void;
  } = $props();

  const percent = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  const why = (c: Choice<unknown>) =>
    c.label === "popular" ? "Popular" : `Clearly better · ${percent(c.wpa)} win`;
  /** The evidence behind "Clearly better": the interval and how many games it rests on. */
  const evidence = (c: Choice<unknown>) => {
    if (c.label === "popular") return "The most played option";
    const interval = c.ci ? ` (95% interval ${percent(c.ci[0])} to ${percent(c.ci[1])})` : "";
    return `Win impact ${percent(c.wpa)} against the most played option${interval}, from ${c.games.toLocaleString("en-US")} games`;
  };

  const source = $derived(
    [`Patch ${plan.patch}`, ...(build ? [games(build.games), elo(build.elo), region(build.region)] : [])].join(" · "),
  );
  const options = $derived(build ? alternatives(build, plan) : null);
  const popularOnly = $derived(allPopular(plan));

  const page = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return `${primary?.runes[0] ?? ""} · ${primary?.title ?? ""} + ${secondary?.title ?? ""}`;
  };
  const pageDetail = (p: Page) => {
    const [primary, secondary] = runePage(names, p);
    return [...(primary?.runes.slice(1) ?? []), ...(secondary?.runes ?? [])].join(" · ");
  };
  const spells = (pair: [number, number]) => pair.map((id) => name(names, "spells", id)).join(" · ");
  const item = (id: number) => name(names, "items", id);
  const itemSlot = (slot: number) => options?.items.find((s) => s.slot === slot);

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
  const skipped = $derived(
    parts.flatMap(([part, o]) => (o.status === "skipped" ? [{ part, reason: o.reason }] : [])),
  );
</script>

<section class="plan" aria-label="Build">
  <header>
    <div>
      <h2>Recommended build</h2>
      <p class="meta">{source}</p>
    </div>
    <button type="button" onclick={onimport}>Import</button>
  </header>

  <p class="note">
    {#if popularOnly}
      No option beats the most played one clearly yet, so Stronk imports the most played build. The
      alternatives below show what else is played and how far the numbers go.
    {:else}
      Stronk imports the most played options, except where another one is clearly better.
    {/if}
  </p>

  {#if imported}
    {#each skipped as s (s.part)}
      <p class="skipped" role="alert">{s.part} not imported: {s.reason}</p>
    {/each}
    <p class="result" role="status">
      {done.length ? `Imported: ${done.join(", ")}.` : "Nothing imported."}
      {#if imported.item_set_backup}<span title={imported.item_set_backup}>Your item sets were backed up first.</span>{/if}
    </p>
  {/if}

  <div class="cards">
    {#if plan.runes}
      <article class="card wide">
        <header>
          <h3>Runes</h3>
          <span class="label" class:better={plan.runes.label !== "popular"} title={evidence(plan.runes)}>{why(plan.runes)}</span>
        </header>
        <div class="page">
          {#each runePage(names, plan.runes.value) as line (line.title)}
            <p><span class="tree">{line.title}</span> {line.runes.join(" · ")}</p>
          {/each}
        </div>
        {#if options?.runes.rows.length}
          <h4>Pages played</h4>
          <OptionList slot={options.runes} label={page} detail={pageDetail} />
        {/if}
      </article>
    {/if}

    {#if plan.spells}
      <article class="card">
        <header>
          <h3>Spells</h3>
          <span class="label" class:better={plan.spells.label !== "popular"} title={evidence(plan.spells)}>{why(plan.spells)}</span>
        </header>
        {#if options?.spells.rows.length}
          <OptionList slot={options.spells} label={spells} />
        {:else}
          <p class="value">{spells(plan.spells.value)}</p>
        {/if}
      </article>
    {/if}

    {#each plan.items as choice (choice.slot)}
        {@const alts = itemSlot(choice.slot)}
        <article class="card">
          <header>
            <h3>Item {choice.slot}</h3>
            <span class="label" class:better={choice.label !== "popular"} title={evidence(choice)}>{why(choice)}</span>
          </header>
          {#if alts?.rows.length}
            <OptionList slot={alts} label={item} />
          {:else}
            <p class="value">{item(choice.value)}</p>
          {/if}
        </article>
      {/each}
  </div>
</section>

<style>
  .plan {
    display: grid;
    gap: var(--space-4);
  }
  .plan > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }
  h2 {
    margin: 0;
    font-size: var(--text-lg);
  }
  h3,
  h4 {
    margin: 0;
    font-size: var(--text-md);
  }
  h4 {
    color: var(--color-muted);
    font-size: var(--text-sm);
    font-weight: 600;
  }
  .card h4 + :global(.options) {
    margin-top: var(--space-1);
  }
  .meta {
    margin: var(--space-1) 0 0;
    color: var(--color-muted);
  }
  .note {
    margin: 0;
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: var(--space-3);
  }
  .card {
    display: grid;
    align-content: start;
    gap: var(--space-2);
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }
  .card > header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: 0 var(--space-1);
  }
  .card.wide {
    grid-column: 1 / -1;
  }
  .page {
    padding: 0 var(--space-1);
  }
  .page p,
  .value {
    margin: 0;
  }
  .value {
    padding: 0 var(--space-1);
  }
  .tree {
    color: var(--color-muted);
  }
  .result {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-positive-bg);
  }
  .skipped {
    margin: 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
  .label {
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-bg);
    color: var(--color-muted);
    font-size: var(--text-sm);
    white-space: nowrap;
  }
  .label.better {
    background: var(--color-positive-bg);
    color: var(--color-positive);
  }
  button {
    padding: var(--space-2) var(--space-6);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-surface);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
</style>
