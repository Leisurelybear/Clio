import { describe, expect, it } from 'vitest';

import { _calculateResizeWidth } from '../layout.js';

describe('panel resize calculation', () => {
  it('uses the drag-start width without accumulating previous moves', () => {
    expect(_calculateResizeWidth(240, 100, 110, true, 160, 400)).toBe(250);
    expect(_calculateResizeWidth(240, 100, 120, true, 160, 400)).toBe(260);
  });

  it('moves the right editor edge in the opposite direction', () => {
    expect(_calculateResizeWidth(400, 100, 130, false, 280, 600)).toBe(370);
    expect(_calculateResizeWidth(400, 100, 70, false, 280, 600)).toBe(430);
  });

  it('clamps both panels to their configured limits', () => {
    expect(_calculateResizeWidth(240, 100, -100, true, 160, 400)).toBe(160);
    expect(_calculateResizeWidth(400, 100, -200, false, 280, 600)).toBe(600);
  });
});
