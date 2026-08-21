<script lang="ts">
  import { onMount } from 'svelte';
  import { activeTab, pushToast } from '$lib/stores/appStore';
  import {
    glossaryLibrary,
    selectedGlossaryEntries,
    mergedGlossary,
    fetchGlossaryLibrary,
    fetchGlossaryEntries,
    fetchMergedGlossary,
    fetchGlossaryPreview,
    toggleGlossaryItem,
    deleteGlossaryItem,
  } from '$lib/stores/glossaryStore';
  import { fetchApi } from '$lib/api/client';
  import { importUrl } from '$lib/services/glossaryService';
  import { reportError } from '$lib/utils/error';
  import type { GlossaryFormat, GlossaryImportJobResponse } from '$lib/types/api';
  import Card from '../ui/Card.svelte';
  import Button from '../ui/Button.svelte';
  import Input from '../ui/Input.svelte';
  import Select from '../ui/Select.svelte';
  import Badge from '../ui/Badge.svelte';
  import Modal from '../ui/Modal.svelte';
  import SegmentedControl from '../ui/SegmentedControl.svelte';

  let activeTabMode: 'library' | 'entries' | 'merged' = 'library';
  let isImportModalOpen = false;

  // Import form inputs
  let importName = '';
  let importFormat = 'json_pairs';
  let importText = '';
  // Renamed from ``importUrl`` to ``importUrlValue`` to avoid the
  // name clash with the typed ``importUrl`` service wrapper.
  let importUrlValue = '';
  let importFile: File | null = null;
  let isSubmittingImport = false;

  onMount(() => {
    fetchGlossaryLibrary();
    fetchMergedGlossary();
    fetchGlossaryPreview();
  });

  async function handleFileImport() {
    if (!importFile && !importText.trim()) {
      pushToast('error', 'Select a file or paste inline text content.', 3000);
      return;
    }

    isSubmittingImport = true;
    try {
      let inline_bytes_b64: string | undefined = undefined;
      let textContent: string | undefined = undefined;

      if (importFile) {
        inline_bytes_b64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const dataUrl = reader.result as string;
            const base64 = dataUrl.split(',')[1] || '';
            resolve(base64);
          };
          reader.onerror = () => reject(reader.error || new Error('Failed to read file'));
          reader.readAsDataURL(importFile as File);
        });
      } else {
        textContent = importText;
      }

      const payload = {
        source: {
          format: importFormat,
          name: importName || undefined,
          text: textContent,
          inline_bytes_b64,
        },
      };

      // /glossary/import is invoked with a custom JSON body shape (inline_bytes_b64 / textContent); the typed importFile() wrapper uses FormData, which is a different wire format. Keep this as a raw fetchApi until the server accepts both.
      const res = await fetchApi<GlossaryImportJobResponse>('/glossary/import', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      pushToast('success', `Glossary imported: ${res.name || 'Success'} (${res.entry_count} entries)`, 4000);
      isImportModalOpen = false;
      resetImportForm();
      await fetchGlossaryLibrary();
      await fetchMergedGlossary();
    } catch (err: unknown) {
      reportError(err, 'Import failed');
    } finally {
      isSubmittingImport = false;
    }
  }

  async function handleUrlImport() {
    if (!importUrlValue.trim()) {
      pushToast('error', 'Provide a valid URL.', 3000);
      return;
    }

    isSubmittingImport = true;
    try {
      const res = await importUrl(
        importUrlValue,
        importFormat as GlossaryFormat,
        importName || undefined
      );

      pushToast('success', `URL imported: ${res.name} (${res.entry_count} entries)`, 4000);
      isImportModalOpen = false;
      resetImportForm();
      await fetchGlossaryLibrary();
      await fetchMergedGlossary();
    } catch (err: unknown) {
      reportError(err, 'URL import failed');
    } finally {
      isSubmittingImport = false;
    }
  }

  function resetImportForm() {
    importName = '';
    importFormat = 'json_pairs';
    importText = '';
    importUrlValue = '';
    importFile = null;
  }

  const importFormats = [
    { value: 'json_pairs', label: 'JSON Pairs / Paired Text' },
    { value: 'csv', label: 'CSV (Comma Separated)' },
    { value: 'tsv', label: 'TSV (Tab Separated)' },
    { value: 'xliff', label: 'XLIFF Translation File' },
    { value: 'tbx', label: 'TBX Glossary File' },
    { value: 'tmx', label: 'TMX Memory File' }
  ];

  const subTabs: { id: 'library' | 'entries' | 'merged'; label: string }[] = [
    { id: 'library', label: 'Library list' },
    { id: 'entries', label: 'Entries view' },
    { id: 'merged', label: 'Merged lexicon' }
  ];
</script>

<section id="view-glossary" data-view="glossary" hidden={$activeTab !== 'glossary'} class="flex-1 flex flex-col min-h-0 p-6 space-y-6">
  <!-- Header -->
  <header class="flex flex-col lg:flex-row lg:items-end justify-between border-b border-border pb-4 gap-3">
    <div class="space-y-1.5 min-w-0">
      <div class="flex items-center gap-2.5 flex-wrap">
        <h2 class="text-2xl font-semibold font-display text-foreground">Terminology glossary</h2>
        <Badge variant="success" size="md" dot>
          {$glossaryLibrary.length} {($glossaryLibrary.length === 1 ? 'library' : 'libraries')} active
        </Badge>
      </div>
      <p class="text-xs text-foreground-muted">Manage term mappings, domain lexicons, and strict translation overrides</p>
    </div>

    <div class="flex items-center gap-2 flex-wrap">
      <!-- Sub-view navigation -->
      <SegmentedControl
        bind:value={activeTabMode}
        ariaLabel="Sub-view"
        options={subTabs.map((t) => ({ value: t.id, label: t.label }))}
      />

      <Button variant="primary" on:click={() => isImportModalOpen = true}>
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        <span>Import glossary</span>
      </Button>
    </div>
  </header>

  <!-- Sub-view content -->
  {#if activeTabMode === 'library'}
    <Card padding="none" className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div class="overflow-x-auto flex-1">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="border-b border-border bg-card-raised">
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Priority</th>
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Name</th>
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Format</th>
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Entries</th>
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted">Status</th>
              <th class="py-2.5 px-4 font-display text-[11px] font-semibold uppercase tracking-wider text-foreground-muted text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-border">
            {#if $glossaryLibrary.length === 0}
              <tr>
                <td colspan="6" class="py-12 text-center text-foreground-muted italic">
                  No glossaries imported. Click "Import glossary" to add CSV, JSON, or XLIFF term banks.
                </td>
              </tr>
            {:else}
              {#each $glossaryLibrary as item (item.id)}
                <tr class="hover:bg-muted/50 transition-colors">
                  <td class="py-2.5 px-4 font-mono text-xs text-foreground-muted">#{item.priority}</td>
                  <td class="py-2.5 px-4 font-semibold text-brand">{item.name}</td>
                  <td class="py-2.5 px-4 text-foreground-muted font-mono text-xs uppercase">{item.format}</td>
                  <td class="py-2.5 px-4 font-mono text-xs text-foreground">{item.entry_count}</td>
                  <td class="py-2.5 px-4">
                    <button
                      type="button"
                      on:click={() => toggleGlossaryItem(item.id, !item.enabled)}
                    >
                      {#if item.enabled}
                        <Badge variant="success" size="sm" dot>Enabled</Badge>
                      {:else}
                        <Badge variant="neutral" size="sm">Disabled</Badge>
                      {/if}
                    </button>
                  </td>
                  <td class="py-2.5 px-4 text-right space-x-3">
                    <button
                      type="button"
                      on:click={() => { fetchGlossaryEntries(item.id); activeTabMode = 'entries'; }}
                      class="text-xs font-medium text-brand hover:underline"
                    >
                      View entries
                    </button>
                    <button
                      type="button"
                      on:click={() => deleteGlossaryItem(item.id)}
                      class="text-xs font-medium text-danger hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </Card>

  {:else if activeTabMode === 'entries'}
    <Card padding="md" className="flex-1 flex flex-col min-h-0 space-y-3 overflow-hidden">
      {#if $selectedGlossaryEntries}
        <div class="flex items-center justify-between border-b border-border pb-2">
          <h3 class="text-sm font-display font-semibold text-brand">
            {$selectedGlossaryEntries.name}
            <span class="text-foreground-muted text-xs font-mono font-normal">
              ({$selectedGlossaryEntries.entries.length} entries)
            </span>
          </h3>
        </div>

        <div class="overflow-y-auto flex-1">
          <table class="w-full text-left text-sm font-mono">
            <thead>
              <tr class="border-b border-border text-foreground-muted">
                <th class="py-2 px-3 font-display text-[11px] font-semibold uppercase tracking-wider">Source term</th>
                <th class="py-2 px-3 font-display text-[11px] font-semibold uppercase tracking-wider">Target term</th>
                <th class="py-2 px-3 font-display text-[11px] font-semibold uppercase tracking-wider">Note / context</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              {#each $selectedGlossaryEntries.entries as entry (`${entry.source}::${entry.target}`)}
                <tr class="hover:bg-muted/30">
                  <td class="py-2 px-3 text-foreground font-semibold">{entry.source}</td>
                  <td class="py-2 px-3 text-brand">{entry.target}</td>
                  <td class="py-2 px-3 text-foreground-muted italic">{entry.note || '—'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else}
        <div class="flex-1 flex items-center justify-center text-foreground-muted text-sm italic">
          Select a glossary from the Library list tab to view its individual entries.
        </div>
      {/if}
    </Card>

  {:else if activeTabMode === 'merged'}
    <Card padding="md" className="flex-1 flex flex-col min-h-0 space-y-3 overflow-hidden">
      <div class="flex items-center justify-between border-b border-border pb-2">
        <h3 class="text-sm font-display font-semibold text-foreground">Active merged lexicon</h3>
        <Badge variant="neutral" size="sm">
          {Object.keys($mergedGlossary).length} unique terms
        </Badge>
      </div>

      <div class="overflow-y-auto flex-1">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 text-sm font-mono">
          {#each Object.entries($mergedGlossary) as [source, target] (source)}
            <div class="p-2.5 surface-inset rounded-md flex items-center justify-between gap-2">
              <span class="text-foreground font-semibold truncate" title={source}>{source}</span>
              <span class="text-foreground-subtle">→</span>
              <span class="text-success truncate" title={String(target)}>{String(target)}</span>
            </div>
          {/each}
        </div>
      </div>
    </Card>
  {/if}

  <!-- Import modal -->
  <Modal
    open={isImportModalOpen}
    on:close={() => isImportModalOpen = false}
    title="Import glossary lexicon"
    description="Upload a term bank file or import from a URL"
    maxWidth="lg"
  >
    <div class="space-y-3">
      <Input
        id="import-name"
        label="Display name (optional)"
        bind:value={importName}
        placeholder="e.g. Legal Terms EN-FR"
      />
      <Select
        id="import-format"
        label="Format"
        options={importFormats}
        bind:value={importFormat}
      />

      <div>
        <label for="import-file" class="form-label">Upload file or paste inline text</label>
        <input
          id="import-file"
          type="file"
          on:change={(e) => {
            const target = e.target as HTMLInputElement;
            if (target.files) importFile = target.files[0];
          }}
          class="block w-full text-foreground-muted surface-inset p-2 rounded-md border border-border file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-brand file:text-brand-foreground hover:file:bg-brand-600 cursor-pointer"
        />
      </div>

      <div>
        <label for="import-text" class="form-label">Inline content (if no file chosen)</label>
        <textarea
          id="import-text"
          bind:value={importText}
          rows="3"
          placeholder="source = target&#10;hello = bonjour"
          class="w-full surface-inset rounded-md p-2 text-sm font-mono text-foreground placeholder:text-foreground-subtle focus:outline-none focus:ring-2 focus:ring-brand/20 resize-none"
        ></textarea>
      </div>

      <div class="pt-2 border-t border-border">
        <label for="import-url" class="form-label">Or import via URL</label>
        <div class="flex items-center gap-2">
          <input
            id="import-url"
            type="url"
            bind:value={importUrlValue}
            placeholder="https://example.com/glossary.csv"
            class="flex-1 h-9 px-3 rounded-md text-sm bg-card text-foreground border border-input focus:outline-none focus:ring-2 focus:ring-brand/20 focus:border-brand"
          />
          <Button size="sm" variant="secondary" on:click={handleUrlImport} loading={isSubmittingImport}>
            Fetch URL
          </Button>
        </div>
      </div>
    </div>

    <svelte:fragment slot="footer">
      <Button variant="ghost" on:click={() => isImportModalOpen = false}>
        Cancel
      </Button>
      <Button variant="primary" on:click={handleFileImport} loading={isSubmittingImport}>
        {isSubmittingImport ? 'Importing…' : 'Submit import'}
      </Button>
    </svelte:fragment>
  </Modal>
</section>
