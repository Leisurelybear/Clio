// Pure helpers for plan-preview floating subtitles. No DOM.

const SENTENCE_BREAKS = '。！？；…!?;';
const BREAK_SET = new Set(SENTENCE_BREAKS.split(''));
const MAX_PLUS_CARRY = 4; // allow punctuation to overflow maxLen slightly

/**
 * Split narration text into subtitle lines by Chinese/ASCII sentence
 * punctuation and newlines; further break lines longer than maxLen.
 * @param {string} text
 * @param {number} [maxLen=16]
 * @returns {string[]}
 */
export function splitSubtitleLines(text, maxLen = 16) {
  const normalized = String(text || '').trim();
  if (!normalized) return [];
  const tokens = [];
  let buf = '';
  for (const ch of normalized) {
    buf += ch;
    if (BREAK_SET.has(ch) || ch === '\n') {
      tokens.push(buf);
      buf = '';
    }
  }
  if (buf.trim()) tokens.push(buf);
  const sentences = tokens.map((t) => t.trim()).filter(Boolean);

  const lines = [];
  for (const sentence of sentences) {
    if (sentence.length <= maxLen + MAX_PLUS_CARRY) {
      lines.push(sentence);
      continue;
    }
    let start = 0;
    while (start < sentence.length) {
      lines.push(sentence.slice(start, start + maxLen));
      start += maxLen;
    }
  }
  return lines;
}