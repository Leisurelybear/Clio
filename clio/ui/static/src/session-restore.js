const VALID_ENTITIES = new Set(['video', 'plan', 'run', 'config', 'logs', 'tokens']);

/**
 * Decide which entity/video to open after project load.
 * Pure helper — no DOM / network.
 */
export function resolveSessionRestore({ lastEntity, lastVideo, videos = [] } = {}) {
  const list = Array.isArray(videos) ? videos : [];
  const available = list.filter(v => v && !v.missing && v.file);
  const byFile = (name) => list.find(v => v && v.file === name && !v.missing) || null;

  const entity = VALID_ENTITIES.has(lastEntity) ? lastEntity : 'video';

  let video = null;
  if (lastVideo) {
    const match = byFile(lastVideo);
    if (match) video = match.file;
  }
  if (!video && available.length) {
    video = available[0].file;
  }

  return { entity, video };
}
