import { writable } from 'svelte/store';
import type {
  GlossaryEntry,
  GlossaryFormat,
  GlossaryImportJobResponse,
  GlossaryListItem,
  GlossaryPreviewResponse,
} from '../types/api';
import { glossaryApi } from '../api/endpoints';

export interface SelectedGlossaryState {
  name?: string;
  entries: GlossaryEntry[];
}

export type { GlossaryEntry };

export const glossaryLibraries = writable<GlossaryListItem[]>([]);
export const glossaryLibrary = glossaryLibraries;
export const glossaryEntries = writable<GlossaryEntry[]>([]);
export const selectedGlossaryEntries = writable<SelectedGlossaryState>({ name: 'Selected Glossary', entries: [] });
export const mergedGlossary = writable<Record<string, string>>({});
export const glossaryPreview = writable<GlossaryPreviewResponse | null>(null);
export const importJobStatus = writable<GlossaryImportJobResponse | null>(null);
export const isGlossaryLoading = writable<boolean>(false);

export async function loadLibraries(): Promise<void> {
  isGlossaryLoading.set(true);
  try {
    const list = await glossaryApi.getLibraries();
    glossaryLibraries.set(Array.isArray(list) ? list : []);
  } catch (err) {
    console.error('Failed to fetch glossary library:', err);
  } finally {
    isGlossaryLoading.set(false);
  }
}
export const fetchGlossaryLibrary = loadLibraries;

export async function toggleLibrary(id: string, enabled: boolean): Promise<void> {
  try {
    await glossaryApi.toggle(id, enabled);
    await loadLibraries();
    await loadMerged();
  } catch (err) {
    console.error(`Failed to toggle glossary library ${id}:`, err);
  }
}
export const toggleGlossaryItem = toggleLibrary;

export async function deleteLibrary(id: string): Promise<void> {
  try {
    await glossaryApi.delete(id);
    await loadLibraries();
    await loadMerged();
  } catch (err) {
    console.error(`Failed to delete glossary library ${id}:`, err);
  }
}
export const deleteGlossaryItem = deleteLibrary;

export async function reorderLibraries(orderedIds: string[]): Promise<void> {
  try {
    await glossaryApi.reorder(orderedIds);
    await loadLibraries();
    await loadMerged();
  } catch (err) {
    console.error('Failed to reorder glossary libraries:', err);
  }
}

export async function loadEntries(id?: string, name?: string): Promise<void> {
  try {
    if (!id) return;
    const res = await glossaryApi.getEntries(id);
    const list: GlossaryEntry[] = Array.isArray(res) ? res : (res.entries || []);
    glossaryEntries.set(list);
    selectedGlossaryEntries.set({ name: name || `Glossary ${id}`, entries: list });
  } catch (err) {
    console.error('Failed to fetch glossary entries:', err);
  }
}
export const fetchGlossaryEntries = loadEntries;

export async function loadMerged(): Promise<void> {
  try {
    const res = await glossaryApi.getMerged();
    // Backend returns { entries: [{ source, target, ... }] }; the merged
    // view renders a flat term → translation map. Server-side merge is
    // already priority-deduped, so order here is display-only.
    const flat: Record<string, string> = {};
    for (const entry of res?.entries ?? []) {
      if (entry.source) flat[entry.source] = entry.target;
    }
    mergedGlossary.set(flat);
  } catch (err) {
    console.error('Failed to fetch merged glossary preview:', err);
  }
}
export const fetchMergedGlossary = loadMerged;

export async function fetchGlossaryPreview(): Promise<void> {
  try {
    const preview = await glossaryApi.getPreview();
    glossaryPreview.set(preview);
  } catch (err) {
    console.error('Failed to fetch glossary preview:', err);
  }
}

export async function importGlossary(formData: FormData): Promise<GlossaryImportJobResponse> {
  isGlossaryLoading.set(true);
  try {
    const result = await glossaryApi.importFile(formData);
    importJobStatus.set(result);
    await loadLibraries();
    await loadMerged();
    return result;
  } finally {
    isGlossaryLoading.set(false);
  }
}

export async function importGlossaryUrl(url: string, format: GlossaryFormat, name?: string): Promise<GlossaryImportJobResponse> {
  isGlossaryLoading.set(true);
  try {
    const result = await glossaryApi.importUrl(url, format, name);
    importJobStatus.set(result);
    await loadLibraries();
    await loadMerged();
    return result;
  } finally {
    isGlossaryLoading.set(false);
  }
}

