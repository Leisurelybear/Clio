/**
 * Pure helpers for the sidebar video list: per-file stage status, filter chips,
 * bottom stage count bar and search matching. DOM rendering lives in
 * sidebar-data.js so this module stays unit-testable.
 */
import { isCompressStepDone } from './video-menu.js';

/** Exact 4 per-file stages shown in rows, chips and the bottom count bar. */
export const STAGE_CELLS = [
  { key: 'compress', label: '压缩' },
  { key: 'analyze', label: '分析' },
  { key: 'voiceover', label: '口播' },
  { key: 'transcribe', label: '转录' },
];

/** True if the given per-file stage is complete for `video` in `source`. */
export function videoStageDone(video, source, key) {
  if (!video) return false;
  if (video.missing) return false;
  switch (key) {
    case 'compress':
      return source === 'compressed' ? true : isCompressStepDone(video, 'original');
    case 'analyze':
      return !!video.text_json;
    case 'voiceover':
      return !!video.script_json;
    case 'transcribe':
      return !!video.transcript_file;
    default:
      return false;
  }
}

/** Map of stage key → done flag. */
export function buildVideoStageStatuses(video, source) {
  const out = {};
  for (const c of STAGE_CELLS) out[c.key] = videoStageDone(video, source, c.key);
  return out;
}

/** True when `video` is missing stage `key` (or offline for key==='offline'). */
export function videoMissingStage(video, source, key) {
  if (key === 'offline') return !!video?.missing;
  return !videoStageDone(video, source, key);
}

const CHIP_DEFS = {
  original: [
    { key: 'compress', label: '未压缩' },
    { key: 'analyze', label: '缺分析' },
    { key: 'voiceover', label: '缺口播' },
    { key: 'transcribe', label: '缺转录' },
    { key: 'offline', label: '离线' },
  ],
  compressed: [
    { key: 'analyze', label: '缺分析' },
    { key: 'voiceover', label: '缺口播' },
    { key: 'transcribe', label: '缺转录' },
    { key: 'offline', label: '离线' },
  ],
};

/** Chip definitions valid for a source view (未压缩 only exists for original). */
export function chipDefsForSource(source) {
  return source === 'original' ? CHIP_DEFS.original : CHIP_DEFS.compressed;
}

/** [{ key, label, count }] over a full video list (counts always match the whole view). */
export function countChipStats(videos, source) {
  return chipDefsForSource(source).map((d) => ({
    key: d.key,
    label: d.label,
    count: videos.filter((v) => videoMissingStage(v, source, d.key)).length,
  }));
}

/** 4 cells { key, label, done, total } for the bottom count bar. */
export function countStageSummary(videos, source) {
  const total = videos.length;
  return STAGE_CELLS.map((c) => ({
    key: c.key,
    label: c.label,
    done: videos.filter((v) => videoStageDone(v, source, c.key)).length,
    total,
  }));
}

/** True when a query needle (trimmed-lowercased) appears in index/name/title. */
export function matchVideoSearch(video, q) {
  const needle = String(q || '').trim().toLowerCase();
  if (!needle) return true;
  const hay = [
    String(video?.index ?? ''),
    String(video?.file ?? '').replace(/^\d+_/, ''),
    String(video?.title ?? ''),
  ].join(' ').toLowerCase();
  return hay.includes(needle);
}