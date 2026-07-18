import { describe, it, expect } from 'vitest';
import { mediaStepsNeedFfmpeg } from '../runner.js';

describe('mediaStepsNeedFfmpeg', () => {
  it('true for compress/label/transcribe', () => {
    expect(mediaStepsNeedFfmpeg(['analyze', 'compress'])).toBe(true);
    expect(mediaStepsNeedFfmpeg(['label'])).toBe(true);
    expect(mediaStepsNeedFfmpeg(['transcribe'])).toBe(true);
  });
  it('false for analyze/voiceover/plan only', () => {
    expect(mediaStepsNeedFfmpeg(['analyze', 'voiceover', 'plan'])).toBe(false);
  });
  it('false for empty', () => {
    expect(mediaStepsNeedFfmpeg([])).toBe(false);
    expect(mediaStepsNeedFfmpeg(null)).toBe(false);
  });
});
