<script lang="ts">
  import type { Choice, Imported, Outcome, Plan } from "../../backend/backend.ts";

  let {
    plan,
    imported,
    onimport,
  }: { plan: Plan; imported: Imported | null; onimport: () => void } = $props();

  const why = (c: Choice<unknown>) =>
    c.label === "popular" ? "Popular" : `Clearly better · ${c.wpa >= 0 ? "+" : ""}${(c.wpa * 100).toFixed(1)}% win`;
  const outcome = (part: string, o: Outcome) =>
    o.status === "imported" ? `${part} imported` : `${part} not imported: ${o.reason}`;
</script>

<section class="plan" aria-label="Build">
  <header>
    <p class="meta">Patch {plan.patch}</p>
    <button type="button" onclick={onimport}>Import</button>
  </header>

  {#if plan.runes}
    <h3>Runes</h3>
    <div class="row">
      <span class="mono">{plan.runes.value.perks.join(" · ")}</span>
      <span class="label" class:better={plan.runes.label !== "popular"}>{why(plan.runes)}</span>
    </div>
  {/if}

  {#if plan.spells}
    <h3>Spells</h3>
    <div class="row">
      <span class="mono">{plan.spells.value.join(" · ")}</span>
      <span class="label" class:better={plan.spells.label !== "popular"}>{why(plan.spells)}</span>
    </div>
  {/if}

  {#if plan.items.length}
    <h3>Items</h3>
    {#each plan.items as item (item.slot)}
      <div class="row">
        <span class="slot">Item {item.slot}</span>
        <span class="mono">{item.value}</span>
        <span class="label" class:better={item.label !== "popular"}>{why(item)}</span>
      </div>
    {/each}
  {/if}

  {#if imported}
    <p class="meta result" role="status">
      {outcome("Runes", imported.runes)} · {outcome("Item set", imported.item_set)} · {outcome("Spells", imported.spells)}
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
  .mono {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
  }
  .label {
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
