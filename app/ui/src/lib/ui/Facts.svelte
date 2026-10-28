<script lang="ts">
  // Short facts side by side ("Jungle", "Locked in"), a thin rule between them instead of a
  // separator character (ADR-057). Empty facts are left out.
  type Fact = { text: string; title?: string };
  let { facts }: { facts: (string | Fact | null | false | undefined)[] } = $props();
  const shown = $derived(
    facts.flatMap((f): Fact[] => (!f ? [] : typeof f === "string" ? [{ text: f }] : [f])),
  );
</script>

<span class="facts">
  {#each shown as f, n (n)}<span title={f.title}>{f.text}</span>{/each}
</span>

<style>
  .facts {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 2px 0;
    align-items: baseline;
  }
  .facts > span + span {
    margin-left: var(--space-2);
    padding-left: var(--space-2);
    border-left: 1px solid var(--color-border);
  }
</style>
