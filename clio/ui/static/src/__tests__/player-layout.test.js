import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('player viewport sizing', () => {
  const css = readFileSync(resolve('clio/ui/static/style.css'), 'utf8');

  it('keeps a stable canvas while source metadata reloads', () => {
    expect(css).toMatch(/\.player-wrap\s*\{[^}]*aspect-ratio:\s*16\s*\/\s*9;/s);
    expect(css).toMatch(/#player\s*\{[^}]*height:\s*100%;[^}]*object-fit:\s*contain;/s);
  });
});
