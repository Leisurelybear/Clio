/**
 * Offline media helpers (pure). Used by sidebar summary + batch relink.
 */

export function basenameLower(path) {
  const s = String(path || '');
  const leaf = s.replace(/^.*[\\/]/, '');
  return leaf.toLowerCase();
}

/** Strip optional leading index like "001_" from a filename for matching. */
export function stemKey(pathOrName) {
  const base = basenameLower(pathOrName);
  return base.replace(/^\d+_/, '');
}

export function summarizeOfflineVideos(videos = []) {
  const items = (videos || [])
    .filter(v => v && v.missing)
    .map(v => ({
      file: v.file,
      abs_path: v.abs_path || v.match?.abs_path || null,
    }));
  return { count: items.length, items };
}

/**
 * Match offline project entries to candidate files found under a directory.
 * @param {Array<{file: string, abs_path?: string|null}>} offline
 * @param {Array<{path: string, name?: string}>} candidates
 */
export function matchBatchRelink(offline = [], candidates = []) {
  const byKey = new Map(); // stemKey -> candidate[]
  for (const c of candidates) {
    const key = stemKey(c.name || c.path);
    if (!key) continue;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(c);
  }

  const matched = [];
  const unmatched = [];
  const ambiguous = [];
  const seenAmbiguous = new Set();

  for (const item of offline) {
    const key = stemKey(item.file || item.abs_path || '');
    const hits = byKey.get(key) || [];
    if (hits.length === 1) {
      matched.push({
        file: item.file,
        old_path: item.abs_path || item.file,
        new_path: hits[0].path,
      });
    } else if (hits.length > 1) {
      if (!seenAmbiguous.has(key)) {
        seenAmbiguous.add(key);
        ambiguous.push({ basename: key, candidates: hits.map(h => h.path) });
      }
      unmatched.push(item);
    } else {
      unmatched.push(item);
    }
  }

  return { matched, unmatched, ambiguous };
}
