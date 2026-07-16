/** Pure helpers for plan sequence structural edits (no DOM). */

export function reorderSequence(sequence, fromIndex, toIndex) {
  const arr = sequence.slice();
  if (fromIndex < 0 || toIndex < 0 || fromIndex >= arr.length || toIndex >= arr.length) {
    return arr;
  }
  const [item] = arr.splice(fromIndex, 1);
  arr.splice(toIndex, 0, item);
  return arr;
}

export function removeSegment(sequence, index) {
  return sequence.filter((_, i) => i !== index);
}

export function patchSegment(segment, fields) {
  return { ...segment, ...fields };
}
