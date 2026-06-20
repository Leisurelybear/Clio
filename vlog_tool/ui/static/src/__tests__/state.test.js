import { describe, it, expect } from 'vitest';
import { state } from '../state.js';

describe('state', () => {
  it('has correct default values', () => {
    expect(state.source).toBe('compressed');
    expect(state.currentEntity).toBe('video');
    expect(state.currentTab).toBe('texts');
    expect(state.dirty).toBe(false);
    expect(state.previewActive).toBe(false);
    expect(state.previewIndex).toBe(-1);
    expect(state.currentDay).toBe('day1');
  });

  it('is mutable', () => {
    const original = state.dirty;
    state.dirty = !original;
    expect(state.dirty).toBe(!original);
    state.dirty = original;
  });

  it('accepts new properties', () => {
    state._testProp = 'hello';
    expect(state._testProp).toBe('hello');
    delete state._testProp;
  });
});
