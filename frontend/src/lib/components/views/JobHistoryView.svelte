<script lang="ts">
  import { onMount } from 'svelte';
  import { activeTab, pushToast } from '$lib/stores/appStore';
  import { fetchApi } from '$lib/api/client';
  import { reportError } from '$lib/utils/error';
  import type { JobRecord } from '$lib/types/api';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Badge, { type BadgeVariant } from '../ui/Badge.svelte';
  import Modal from '../ui/Modal.svelte';

  let jobs: JobRecord[] = [];
  let isLoading = false;
  // F3.8 audit fix: a typed modal confirmation replaces the
  // global ``window.confirm`` for destructive actions. The native
  // confirm has no theming, no focus trap, no aria-labelledby, and
  // is blocked by browser "prevent additional dialogs" settings.
  // The Modal component is the project's design-system primitive;
  // it already wires Escape-to-close, focus trap, and click-outside
  // dismissal.
  let showClearAllModal = false;

  async function loadJobs() {
    isLoading = true;
    try {
      const data = await fetchApi<JobRecord[]>('/jobs');
      jobs = data || [];
    } catch (err) {
      console.warn('Failed to load job history:', err);
    } finally {
      isLoading = false;
    }
  }

  onMount(() => {
    loadJobs();
  });

  $: if ($activeTab === 'jobs') {
    loadJobs();
  }

  async function cancelJob(jobId: string) {
    try {
      await fetchApi(`/jobs/${jobId}/cancel`, { method: 'POST' });
      pushToast('info', `Job ${jobId} cancellation requested.`, 3000);
      await loadJobs();
    } catch (err: unknown) {
      reportError(err, 'Cancel failed');
    }
  }

  function requestClearAll() {
    showClearAllModal = true;
  }

  async function confirmClearAll() {
    showClearAllModal = false;
    try {
      await fetchApi('/jobs', { method: 'DELETE' });
      jobs = [];
      pushToast('success', 'Job history cleared.', 3000);
    } catch (err: unknown) {
      reportError(err, 'Clear failed');
    }
  }

  function statusVariant(status: string): BadgeVariant {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'danger';
      case 'processing':
      case 'pending': return 'warning';
      case 'cancelled': return 'neutral';
      default: return 'neutral';
    }
  }
</script>

<section id="view-jobs" data-view="jobs" hidden={$activeTab !== 'jobs'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col sm:flex-row sm:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5">
      <div class="flex items-center gap-2.5">
        <h2 class="text-2xl font-semibold font-display text-foreground">Job execution history</h2>
        <Badge variant="brand" size="md" dot>
          {jobs.length} {jobs.length === 1 ? 'job' : 'jobs'}
        </Badge>
      </div>
      <p class="text-xs text-foreground-muted">Audit log of previous OCR, Translation, and Extraction pipeline executions</p>
    </div>

    <div class="flex items-center gap-2">
      <Button variant="secondary" size="sm" on:click={loadJobs}>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <span>Refresh</span>
      </Button>
      <Button variant="danger" size="sm" disabled={jobs.length === 0} on:click={requestClearAll}>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3" />
        </svg>
        <span>Clear all</span>
      </Button>
    </div>
  </header>

  <!-- Jobs table -->
  <Card padding="none" class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <div class="overflow-x-auto flex-1">
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="border-b border-border bg-card-raised">
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Job ID</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Status</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">File name</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Pipeline / model</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Duration</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Failed pages</th>
            <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted text-right">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-border">
          {#if isLoading}
            <tr>
              <td colspan="7" class="py-12 text-center text-foreground-muted font-mono animate-pulse">
                Loading job execution history…
              </td>
            </tr>
          {:else if jobs.length === 0}
            <tr>
              <td colspan="7" class="py-12 text-center text-foreground-muted italic">
                No past execution jobs recorded yet.
              </td>
            </tr>
          {:else}
            {#each jobs as job (job.id)}
              <tr class="hover:bg-muted/50 transition-colors">
                <td class="py-2.5 px-4 font-mono text-xs font-semibold text-foreground truncate max-w-[120px]" title={job.id}>
                  {job.id}
                </td>
                <td class="py-2.5 px-4">
                  <Badge variant={statusVariant(job.status)} size="sm">
                    {job.status}
                  </Badge>
                </td>
                <td class="py-2.5 px-4 text-foreground truncate max-w-[200px]" title={job.filename || 'Document'}>
                  {job.filename || 'Document'}
                </td>
                <td class="py-2.5 px-4 text-foreground-muted font-mono text-xs">
                  {job.pipeline_mode || 'hybrid'} / {job.model || 'default'}
                </td>
                <td class="py-2.5 px-4 text-foreground-muted font-mono text-xs">
                  {job.duration_s ? `${job.duration_s.toFixed(1)}s` : '—'}
                </td>
                <td class="py-2.5 px-4">
                  {#if job.failed_pages && job.failed_pages.length > 0}
                    <Badge variant="danger" size="sm">
                      Pages: {job.failed_pages.join(', ')}
                    </Badge>
                  {:else}
                    <span class="text-foreground-subtle text-xs">None</span>
                  {/if}
                </td>
                <td class="py-2.5 px-4 text-right">
                  {#if job.status === 'processing' || job.status === 'pending'}
                    <Button variant="danger" size="sm" on:click={() => cancelJob(job.id)}>
                      Cancel
                    </Button>
                  {:else}
                    <span class="text-foreground-subtle text-xs">—</span>
                  {/if}
                </td>
              </tr>
            {/each}
          {/if}
        </tbody>
      </table>
    </div>
  </Card>
</section>

<Modal
  bind:open={showClearAllModal}
  title="Clear all job history?"
  description="This removes every past OCR, Translation, and Extraction job from the local history. Cached text artifacts are also dropped. This action cannot be undone."
  maxWidth="md"
>
  <p class="text-sm text-foreground-muted">
    A total of <strong class="text-foreground">{jobs.length}</strong>
    {jobs.length === 1 ? 'job' : 'jobs'} will be removed from the history table.
    Cached text and metadata are deleted from the server.
  </p>
  <div slot="footer" class="flex justify-end gap-2">
    <Button variant="secondary" size="sm" on:click={() => (showClearAllModal = false)}>
      Cancel
    </Button>
    <Button variant="danger" size="sm" on:click={confirmClearAll}>
      Clear all
    </Button>
  </div>
</Modal>
