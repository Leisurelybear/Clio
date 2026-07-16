import { describe, it, expect } from 'vitest';
import { shouldReloadTextsAfterRerun, shouldReloadVoiceoverAfterRerun } from '../sidebar-rerun.js';

describe('shouldReloadTextsAfterRerun', () => {
  it('reloads after analyze, texts alias, and all', () => {
    expect(shouldReloadTextsAfterRerun('analyze')).toBe(true);
    expect(shouldReloadTextsAfterRerun('texts')).toBe(true);
    expect(shouldReloadTextsAfterRerun('all')).toBe(true);
  });

  it('does not reload texts after voiceover-only or compress', () => {
    expect(shouldReloadTextsAfterRerun('voiceover')).toBe(false);
    expect(shouldReloadTextsAfterRerun('compress')).toBe(false);
    expect(shouldReloadTextsAfterRerun('transcribe')).toBe(false);
  });
});

describe('shouldReloadVoiceoverAfterRerun', () => {
  it('reloads voiceover for voiceover and all only', () => {
    expect(shouldReloadVoiceoverAfterRerun('voiceover')).toBe(true);
    expect(shouldReloadVoiceoverAfterRerun('all')).toBe(true);
    expect(shouldReloadVoiceoverAfterRerun('analyze')).toBe(false);
  });
});
