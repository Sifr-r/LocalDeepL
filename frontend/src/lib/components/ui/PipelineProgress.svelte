<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { jobStore } from '../../stores/appStore';
  import Card from './Card.svelte';
  import Button from './Button.svelte';

  const dispatch = createEventDispatcher<{ cancel: void }>();

  // Mirror the backend stage weights in
  // omniscribe/api/services/progress.py (_STAGE_WEIGHTS): the overall
  // percent already encodes the stage windows, so thresholds must match.
  const stages = [
    { key: 'convert', label: 'Convert', lo: 0, hi: 15 },
    { key: 'detect', label: 'Detect', lo: 15, hi: 25 },
    { key: 'ocr', label: 'OCR', lo: 25, hi: 75 },
    { key: 'refine', label: 'Refine', lo: 75, hi: 90 },
    { key: 'embed', label: 'Embed', lo: 90, hi: 100 }
  ];

  $: currentPercent = $jobStore.percent || 0;
  $: currentStage = $jobStore.stage || 'idle';
  $: statusMessage = $jobStore.statusMessage || '';
  $: warnings = $jobStore.warnings || [];
  $: isCancelling = currentStage === 'cancelling';

  function getStageStatus(stage: { key: string; lo: number; hi: number }): 'pending' | 'processing' | 'complete' {
    if (currentStage === 'complete' || currentPercent >= stage.hi) {
      return 'complete';
    }
    if (currentStage === stage.key || (currentPercent >= stage.lo && currentPercent < stage.hi && currentPercent > 0)) {
      return 'processing';
    }
    return 'pending';
  }
</script>

<Card padding="lg" className="w-full max-w-2xl shadow-2xl">
  <div class="space-y-5">
    <!-- Title + percent -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2.5">
        <span class="relative flex h-2.5 w-2.5">
          <span class="absolute inline-flex h-full w-full rounded-full bg-brand opacity-60 animate-ping"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand"></span>
        </span>
        <h3 class="font-display font-semibold text-sm tracking-wide uppercase text-foreground">
          Pipeline execution
        </h3>
      </div>
      <span class="font-mono text-base font-bold text-brand">
        {Math.round(currentPercent)}%
      </span>
    </div>

    <!-- Progress bar -->
    <div class="w-full h-2 rounded-full bg-muted overflow-hidden" role="progressbar" aria-valuenow={Math.round(currentPercent)} aria-valuemin="0" aria-valuemax="100">
      <div
        class="h-full bg-brand transition-all duration-300 ease-out"
        style="width: {currentPercent}%;"
      ></div>
    </div>

    <!-- Stage indicators -->
    <div class="grid grid-cols-5 gap-2 pt-1">
      {#each stages as stage (stage.key)}
        {@const status = getStageStatus(stage)}
        <div class="flex flex-col items-center gap-1.5 text-center">
          <div
            class={[
              'w-5 h-5 rounded-full border flex items-center justify-center transition-colors',
              status === 'complete'
                ? 'bg-success border-success text-white'
                : status === 'processing'
                ? 'bg-warning/15 border-warning text-warning'
                : 'bg-card-raised border-border text-foreground-muted'
            ].join(' ')}
          >
            {#if status === 'complete'}
              <svg class="w-3 h-3 stroke-[3]" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            {:else if status === 'processing'}
              <span class="block w-1.5 h-1.5 rounded-full bg-current animate-pulse"></span>
            {/if}
          </div>
          <span
            class={[
              'font-mono text-[10px] uppercase tracking-wider font-medium truncate w-full',
              status === 'complete' ? 'text-success' :
              status === 'processing' ? 'text-warning' : 'text-foreground-muted'
            ].join(' ')}
          >
            {stage.label}
          </span>
        </div>
      {/each}
    </div>

    <!-- Live status line from the progress stream -->
    <div class="text-center text-xs font-mono text-foreground-muted pt-1" aria-live="polite">
      {#if statusMessage}
        <span class="text-foreground">{statusMessage}</span>
      {:else}
        Stage: <span class="text-foreground capitalize">{currentStage.replace(/_/g, ' ')}</span>
      {/if}
    </div>

    <!-- Audit P2-10: cancel is honored between blocks, so an in-flight
         VLM call can delay shutdown. Tell the user why it isn't instant. -->
    {#if isCancelling}
      <div class="text-center text-[11px] font-mono text-warning" role="status">
        Waiting for the current model call to finish — cancel takes effect
        once the in-flight block completes.
      </div>
    {/if}

    <!-- Warnings surfaced by the worker (per-page OCR failures etc.) -->
    {#if warnings.length > 0}
      <div class="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 max-h-24 overflow-y-auto">
        <p class="text-[10px] font-medium uppercase tracking-wider text-warning mb-1">
          {warnings.length} warning{warnings.length === 1 ? '' : 's'}
        </p>
        <ul class="space-y-0.5 text-xs text-foreground-muted font-mono">
          {#each warnings as warning (warning)}
            <li class="truncate" title={warning}>{warning}</li>
          {/each}
        </ul>
      </div>
    {/if}

    <!-- Cancel affordance -->
    <div class="flex justify-center pt-1">
      <Button
        variant="danger"
        size="sm"
        disabled={isCancelling}
        on:click={() => dispatch('cancel')}
      >
        {#if isCancelling}
          <span>Cancelling…</span>
        {:else}
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          <span>Cancel run</span>
        {/if}
      </Button>
    </div>
  </div>
</Card>
