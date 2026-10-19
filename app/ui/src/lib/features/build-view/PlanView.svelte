<script lang="ts">
  import type { Choice, GameNames, Imported, Outcome, Plan } from "../../backend/backend.ts";
  import { name, runePage } from "../../ui/labels.ts";

  let {
    plan,
    names,
    imported,
    onimport,
  }: { plan: Plan; names: GameNames | null; imported: Imported | null; onimport: () => void } = $props();

  const percent = (v: number) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;
  const why = (c: Choice<unknown>) =>
    c.label === "popular" ? "Popular" : `Clearly better · ${percent(c.wpa)} win`;
  /** The evidence behind "Clearly better": the interval and how many games it rests on. */
  const evidence = (c: Choice<unknown>) => {
    if (c.label === "popular") return "The most played option";
    const interval = c.ci ? ` (95% interval ${percent(c.ci[0])} to ${percent(c.ci[1])})` : "";
    return `Win impact ${percent(c.wpa)} against the most played option${interval}, from ${c.games.toLocaleString("en-US")} games`;
  };
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
    <p class="meta">Patch {plan.patch}</p>
    <button type="button" onclick={onimport}>Import</button>
  </header>

  {#if plan.runes}
    <h3>Runes</h3>
    <div class="row">
      <div class="runes">
        {#each runePage(names, plan.runes.value) as line (line.title)}
          <p><span class="tree">{line.title}</span> {line.runes.join(" · ")}</p>
        {/each}
      </div>
      <span class="label" class:better={plan.runes.label !== "popular"} title={evidence(plan.runes)}>{why(plan.runes)}</span>
    </div>
  {/if}

  {#if plan.spells}
    <h3>Spells</h3>
    <div class="row">
      <span>{plan.spells.value.map((id) => name(names, "spells", id)).join(" · ")}</span>
      <span class="label" class:better={plan.spells.label !== "popular"} title={evidence(plan.spells)}>{why(plan.spells)}</span>
    </div>
  {/if}

  {#if plan.items.length}
    <h3>Items</h3>
    {#each plan.items as item (item.slot)}
      <div class="row">
        <span class="slot">Item {item.slot}</span>
        <span>{name(names, "items", item.value)}</span>
        <span class="label" class:better={item.label !== "popular"} title={evidence(item)}>{why(item)}</span>
      </div>
    {/each}
  {/if}

  {#if imported}
    {#each skipped as s (s.part)}
      <p class="skipped" role="alert">{s.part} not imported: {s.reason}</p>
    {/each}
    <p class="meta result" role="status">
      {done.length ? `Imported: ${done.join(", ")}.` : "Nothing imported."}
      {#if imported.item_set_backup}<span title={imported.item_set_backup}>Your item sets were backed up first.</span>{/if}
    </p>
  {/if}
</section>

<style>
  .plan {
    padding: var(--space-4);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-surface);
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h3 {
    margin: var(--space-4) 0 var(--space-2);
    font-size: var(--text-md);
  }
  .row {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-1) 0;
  }
  .meta,
  .slot {
    margin: 0;
    color: var(--color-muted);
  }
  .result {
    margin-top: var(--space-3);
  }
  .runes p {
    margin: 0;
  }
  .tree {
    color: var(--color-muted);
  }
  .skipped {
    margin: var(--space-3) 0 0;
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
  }
  .label {
    margin-left: auto;
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-bg);
    color: var(--color-muted);
    font-size: var(--text-sm);
  }
  .label.better {
    color: var(--color-positive);
  }
  button {
    padding: var(--space-1) var(--space-3);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-surface);
    font: inherit;
  }
</style>
