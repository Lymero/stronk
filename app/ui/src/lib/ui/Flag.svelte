<script lang="ts">
  import type { BuildV1 } from "@stronk/contracts";

  let { flag }: { flag: BuildV1.Flag } = $props();

  const labels: Record<BuildV1.Flag, string> = {
    low_sample: "Few games",
    low_overlap: "No comparison",
    no_clear_difference: "No clear difference",
    fragile: "Fragile",
  };
</script>

<span class="flag" title={flag}>{labels[flag]}</span>

<style>
  .flag {
    display: inline-block;
    padding: 0 var(--space-2);
    border-radius: var(--radius);
    background: var(--color-warning-bg);
    color: var(--color-warning);
    font-size: var(--text-sm);
  }
</style>
