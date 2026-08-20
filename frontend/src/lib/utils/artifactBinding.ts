/**
 * Reactive binding helper for the ``$documentStore`` text artifact.
 *
 * The Workstation publishes a token-bound text artifact id (and the
 * matching access token) whenever a document finishes OCR. The
 * Translation and Extraction views need to copy that id/token into
 * local state so they can build their request payloads — but they
 * also need to **clear** the local state when the store transitions
 * to falsy (e.g. the user picks a new document without a text
 * artifact, or the artifact expires). The original
 * ``lastSyncedArtifactId`` flag (audit F3.9) tracks whether a value
 * was previously held so the clear only fires on a real transition,
 * not on every store update with a still-falsy id.
 *
 * Two views implemented this by hand (TranslationView, ExtractionView)
 * and the inline ``$:`` blocks were drifting in the details. This
 * module centralises the F3.9 invariant in a Svelte-readable store
 * so both views subscribe to the same source of truth.
 */

import { readable, type Readable } from 'svelte/store';

export interface ArtifactStoreSlice {
  textArtifactId?: string | null | undefined;
  textArtifactToken?: string | null | undefined;
}

export interface ArtifactBinding {
  id: string;
  token: string;
}

const EMPTY: ArtifactBinding = { id: '', token: '' };

/**
 * Build a Svelte-readable store that mirrors the text artifact id
 * and token from ``store``, clearing both to empty strings when the
 * source id transitions from truthy to falsy (F3.9 invariant).
 *
 * Usage in a Svelte component:
 *
 *   import { documentStore } from '$lib/stores/appStore';
 *   import { bindArtifactToText } from '$lib/utils/artifactBinding';
 *
 *   const artifact = bindArtifactToText(documentStore);
 *   $: selectedArtifactId = $artifact.id;
 *   $: selectedArtifactToken = $artifact.token;
 *
 * The store is a thin read-only projection: every subscriber gets
 * the same derived value (F3.9 doesn't depend on per-view memory),
 * so a single shared instance per source store is enough.
 */
export function bindArtifactToText(
  store: Readable<ArtifactStoreSlice>
): Readable<ArtifactBinding> {
  return readable<ArtifactBinding>(EMPTY, (set) => {
    // The F3.9 ``lastSynced`` guard lives here so every subscriber
    // sees the same clear-on-falsy-transition behaviour. The guard
    // is per-source-store, not per-subscriber, so re-subscriptions
    // share the same memory — this is intentional and matches the
    // original inline pattern.
    let lastSynced: string | null = null;
    const update = (slice: ArtifactStoreSlice) => {
      const incoming = slice.textArtifactId;
      if (incoming) {
        lastSynced = incoming;
        set({ id: incoming, token: slice.textArtifactToken || '' });
      } else if (lastSynced) {
        // F3.9: only clear when we previously held a value. Without
        // this guard, every store update with a still-falsy id would
        // re-clear and the user's manual selection would not stick.
        lastSynced = null;
        set(EMPTY);
      }
    };
    return store.subscribe((next) => update(next));
  });
}
