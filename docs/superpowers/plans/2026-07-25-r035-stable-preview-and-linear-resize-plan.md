# R-035 Stable Preview and Linear Resize Plan

**Date:** 2026-07-25  
**Status:** Complete  
**Scope:** Plan preview player sizing and the left/right panel resize handles.

## Goal

Prevent the plan preview window from shrinking and expanding when switching segment media, and make both panel resize handles track pointer movement linearly.

## Root Causes

1. The player wrapper derives its height from the video's current intrinsic dimensions. Replacing `video.src` temporarily removes usable metadata, so the wrapper reflows before the next video's dimensions are known.
2. The resize handler recalculates from the current width while also applying the full displacement from the original pointer position on every mousemove. This repeatedly adds prior movement and accelerates the resize.

## Implementation

1. Give the preview wrapper a stable 16:9 aspect ratio and render source media with `object-fit: contain` so portrait and non-16:9 clips use letterboxing instead of changing the layout.
2. Capture the panel width once at drag start and calculate every frame from that fixed width plus or minus the pointer displacement.
3. Track maximum displacement only for distinguishing a drag from a collapse click.
4. Add focused tests for left/right resize direction, clamping, non-accumulating movement, and the stable player viewport CSS contract.

## Verification

- Run the focused layout tests.
- Run the complete Vitest suite.
- Run `git diff --check`.
