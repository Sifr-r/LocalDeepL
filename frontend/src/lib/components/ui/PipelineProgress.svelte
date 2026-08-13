<script lang="ts">
  import { jobStore } from '../../stores/appStore';
  import Card from './Card.svelte';
  import Badge from './Badge.svelte';

  const stages = [
    { key: 'detection', label: 'Detection' },
    { key: 'ocr', label: 'OCR' },
    { key: 'alignment', label: 'Alignment' },
    { key: 'refinement', label: 'Refinement' },
    { key: 'post_processing', label: 'Post-processing' },
    { key: 'embed', label: 'Embed' }
  ];

  $: currentPercent = $jobStore.percent || 0;
  $: currentStage = $jobStore.stage || 'idle';

  function getStageStatus(stageKey: string, index: number): 'pending' | 'processing' | 'complete' {
    const stagePercentStep = 100 / stages.length;
    const stageThreshold = (index + 1) * stagePercentStep;

    if (currentPercent >= stageThreshold || currentStage === 'complete') {
      return 'complete';
    }
    if (currentPercent > index * stagePercentStep || currentStage.includes(stageKey)) {
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
    <div class="w-full h-2 rounded-full bg-muted overflow-hidden">
      <div
        class="h-full bg-brand transition-all duration-300 ease-out"
        style="width: {currentPercent}%;"
      ></div>
    </div>

    <!-- Stage indicators -->
    <div class="grid grid-cols-6 gap-2 pt-1">
      {#each stages as stage, idx}
        {@const status = getStageStatus(stage.key, idx)}
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

    <!-- Status footer -->
    <div class="text-center text-xs font-mono text-foreground-muted pt-1">
      Status: <span class="text-foreground capitalize">{currentStage.replace(/_/g, ' ')}</span>
    </div>
  </div>
</Card>
