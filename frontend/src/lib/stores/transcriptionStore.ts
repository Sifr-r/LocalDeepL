import { writable } from 'svelte/store';
import type { TranscriptionJobResponse } from '../types/api';
import { transcriptionApi } from '../api/endpoints';

export interface TranscriptionProgressState {
  percent: number;
  stage: string;
  isTranscribing: boolean;
  error?: string | null;
}

export const transcriptionResult = writable<TranscriptionJobResponse | null>(null);
export const isTranscribing = writable<boolean>(false);
export const activeSegmentId = writable<number | null>(null);
export const audioCurrentTime = writable<number>(0);

export const transcriptionProgress = writable<TranscriptionProgressState>({
  percent: 0,
  stage: 'idle',
  isTranscribing: false,
  error: null,
});
export const transcriptionFile = writable<File | null>(null);

export async function transcribeAudio(
  file: File,
  options?: Record<string, unknown>,
  channelId?: string
): Promise<TranscriptionJobResponse> {
  transcriptionFile.set(file);
  isTranscribing.set(true);
  transcriptionProgress.set({
    percent: 10,
    stage: 'uploading',
    isTranscribing: true,
    error: null,
  });

  const formData = new FormData();
  formData.append('file', file);

  if (channelId) {
    formData.append('channel_id', channelId);
  }

  if (options) {
    Object.entries(options).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        formData.append(key, String(value));
      }
    });
  }

  try {
    transcriptionProgress.update((curr) => ({
      ...curr,
      percent: 30,
      stage: 'transcribing',
    }));

    const result = await transcriptionApi.transcribe(formData);
    transcriptionResult.set(result);
    isTranscribing.set(false);
    transcriptionProgress.set({
      percent: 100,
      stage: 'complete',
      isTranscribing: false,
      error: null,
    });

    return result;
  } catch (err: unknown) {
    const errMsg = err instanceof Error ? err.message : 'Transcription failed';
    isTranscribing.set(false);
    transcriptionProgress.set({
      percent: 0,
      stage: 'error',
      isTranscribing: false,
      error: errMsg,
    });
    throw err;
  }
}

export function resetTranscription(): void {
  transcriptionResult.set(null);
  isTranscribing.set(false);
  activeSegmentId.set(null);
  audioCurrentTime.set(0);
  transcriptionProgress.set({
    percent: 0,
    stage: 'idle',
    isTranscribing: false,
    error: null,
  });
  transcriptionFile.set(null);
}
