<script lang="ts">
  /**
   * TrustPanel — Phase 2.18 read-only trust score summary.
   *
   * Renders a distribution histogram and flagged-block count sourced
   * from the `X-Document-Trust` response header (parsed and stored in
   * ``documentStore.trustSummary``). When the trust layer is disabled
   * (no orchestrator, no submodules enabled) the header is omitted by
   * the backend and the panel hides itself entirely — matching the
   * "hidden when absent" Phase 2 spec.
   *
   * Read-only by design: there is no toggle or settings surface here.
   * Enabling/disabling the trust layer lives in the quality router /
   * settings view (Phase 2.19).
   */
  import { documentStore } from '../../stores/appStore';
  import type { TrustSummary } from '../../types/api';
  import Card from '../ui/Card.svelte';
  import SectionHeader from '../ui/SectionHeader.svelte';
  import Badge from '../ui/Badge.svelte';

  $: trustSummary = ($documentStore.trustSummary as TrustSummary | null | undefined) ?? null;
  $: hasTrust = trustSummary !== null && trustSummary.scored_count > 0;

  // Histogram bars (left → right): 0.0–0.2, 0.2–0.4, 0.4–0.6, 0.6–0.8, 0.8–1.0.
  const BUCKET_ORDER: Array<{ key: string; label: string; tone: 'danger' | 'warning' | 'neutral' | 'success' }> = [
    { key: '0.0-0.2', label: '0.0–0.2', tone: 'danger' },
    { key: '0.2-0.4', label: '0.2–0.4', tone: 'warning' },
    { key: '0.4-0.6', label: '0.4–0.6', tone: 'neutral' },
    { key: '0.6-0.8', label: '0.6–0.8', tone: 'neutral' },
    { key: '0.8-1', label: '0.8–1.0', tone: 'success' },
  ];

  $: buckets = BUCKET_ORDER.map(({ key, label, tone }) => {
    const count = (trustSummary?.histogram?.[key] ?? 0) as number;
    return { key, label, tone, count };
  });

  $: maxBucket = Math.max(1, ...buckets.map((b) => b.count));

  $: flaggedPercent =
    trustSummary && trustSummary.scored_count > 0
      ? Math.round((trustSummary.flagged_count / trustSummary.scored_count) * 100)
      : 0;

  $: averagePercent = Math.round((trustSummary?.average ?? 0) * 100);

  type BadgeTone = 'success' | 'warning' | 'danger';
  $: averageTone = (averagePercent >= 90
    ? 'success'
    : averagePercent >= 70
    ? 'warning'
    : 'danger') as BadgeTone;

  $: flagEntries = Object.entries(trustSummary?.flag_counts ?? {})
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1]);
</script>

{#if hasTrust}
  <Card padding="md" class="flex flex-col gap-4">
    <SectionHeader
      title="OCR trust"
      description="Read-only summary of the trust-layer run for this document."
    />

    <!-- Average score -->
    <div class="surface-inset p-3 space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs text-foreground-muted">Average score</span>
        <Badge variant={averageTone} size="md" dot>
          {averagePercent}%
        </Badge>
      </div>
      <div class="w-full h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          class={[
            'h-full transition-all duration-300',
            averageTone === 'success' ? 'bg-success' :
            averageTone === 'warning' ? 'bg-warning' :
            'bg-danger'
          ].join(' ')}
          style="width: {averagePercent}%;"
        ></div>
      </div>
    </div>

    <!-- Distribution histogram -->
    <div>
      <div class="flex items-center justify-between mb-2">
        <p class="form-label">Score distribution</p>
        <span class="text-xs text-foreground-subtle font-mono">
          {trustSummary?.scored_count ?? 0} blocks
        </span>
      </div>
      <div class="surface-inset p-3 space-y-2">
        {#each buckets as bucket (bucket.key)}
          {@const pct = Math.round((bucket.count / maxBucket) * 100)}
          <div class="flex items-center gap-2">
            <span class="w-16 shrink-0 text-[10px] font-mono text-foreground-muted">
              {bucket.label}
            </span>
            <div class="flex-1 h-2 rounded-full bg-muted overflow-hidden">
              <div
                class={[
                  'h-full transition-all duration-300',
                  bucket.tone === 'success' ? 'bg-success' :
                  bucket.tone === 'warning' ? 'bg-warning' :
                  bucket.tone === 'danger' ? 'bg-danger' :
                  'bg-brand/70'
                ].join(' ')}
                style="width: {pct}%;"
              ></div>
            </div>
            <span class="w-8 shrink-0 text-[10px] font-mono text-foreground text-right">
              {bucket.count}
            </span>
          </div>
        {/each}
      </div>
    </div>

    <!-- Flagged block summary -->
    <div class="surface-inset p-3 space-y-2">
      <div class="flex items-center justify-between">
        <span class="text-xs text-foreground-muted">Flagged blocks</span>
        <Badge
          variant={(flaggedPercent > 20 ? 'danger' : flaggedPercent > 5 ? 'warning' : 'success') as BadgeTone}
          size="md"
        >
          {trustSummary?.flagged_count ?? 0} · {flaggedPercent}%
        </Badge>
      </div>
      {#if flagEntries.length > 0}
        <ul class="font-mono text-[11px] text-foreground-muted space-y-1 pt-1">
          {#each flagEntries as [flag, count] (flag)}
            <li class="flex justify-between gap-2">
              <span class="truncate">{flag}</span>
              <span class="text-foreground shrink-0">{count}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-[11px] italic text-foreground-subtle pt-1">
          No flagged blocks in this run.
        </p>
      {/if}
    </div>
  </Card>
{/if}
