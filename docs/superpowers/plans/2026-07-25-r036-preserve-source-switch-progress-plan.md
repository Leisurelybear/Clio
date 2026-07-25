# R-036 Preserve Source Switch Progress Plan

**Date:** 2026-07-25  
**Status:** Complete  
**Scope:** Compressed/original source switching in normal video and plan views.

## Goal

Keep the viewer at the same logical playback position when switching between compressed and original media, and continue playback only when the previous source was playing.

## Time Domains

1. Normal video view stores progress as segment-local time. Original legacy segment entries add `offset_sec`; compressed segment media starts at local zero.
2. Plan view stores progress as `previewGlobalSec`, independent of the currently loaded source and its media offset.

## Implementation

1. Capture current player time and playing state before changing `state.source`.
2. For normal videos, subtract the old original-source offset and add the new original-source offset.
3. Allow `selectVideo()` to seek and optionally resume after target metadata loads.
4. For plan view, restore the captured global second with `seekToGlobal()` after the new video list is loaded.
5. Keep missing/offline counterpart behavior unchanged.

## Verification

- Cover compressed-to-original and original-to-compressed time conversion.
- Cover plan global-time preservation and playing-state capture.
- Run focused source-switch tests and the complete Vitest suite.
- Run `git diff --check`.
