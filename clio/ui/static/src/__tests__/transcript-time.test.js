import { describe, expect, it } from 'vitest';

import { _transcriptTimeFromPlayer } from '../editor-texts.js';

describe('_transcriptTimeFromPlayer', () => {
  it('subtracts the original-video segment offset', () => {
    expect(_transcriptTimeFromPlayer(125, 120)).toBe(5);
  });

  it('never returns a negative timestamp', () => {
    expect(_transcriptTimeFromPlayer(5, 10)).toBe(0);
  });
});
