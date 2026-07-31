import { beforeEach, describe, expect, it, vi } from 'vitest';

const elements = new Map();

function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id,
      classList: { add() {}, remove() {}, toggle() {} },
      currentTime: 0,
      duration: 0,
      play: vi.fn(() => Promise.resolve()),
      removeAttribute: vi.fn(),
      textContent: '',
    });
  }
  return elements.get(id);
}

vi.mock('../api.js', () => ({ api: vi.fn(), icon: vi.fn(() => '') }));
vi.mock('../utils.js', () => ({
  $: vi.fn((id) => element(id)),
  $$: vi.fn(() => []),
  setStatus: vi.fn(),
  fmtTime: vi.fn((value) => String(value)),
  updateSidebarDay: vi.fn(),
  updateEntityUI: vi.fn(),
  clearDirty: vi.fn(),
}));
vi.mock('../viewer.js', () => ({ playVideoSegment: vi.fn(), stopPreview: vi.fn() }));
vi.mock('../waveform.js', () => ({ loadWaveformForCurrentVideo: vi.fn() }));
vi.mock('../sidebar-rerun.js', () => ({ showRerunProgress: vi.fn(), hideRerunProgress: vi.fn() }));
vi.mock('../sidebar-video-manage.js', () => ({ openVideoManager: vi.fn() }));
vi.mock('../sidebar-data.js', () => ({
  loadProjects: vi.fn(), loadConfig: vi.fn(), loadFfmpegDeps: vi.fn(), loadPlans: vi.fn(),
  loadProject: vi.fn(), loadVideos: vi.fn(), saveProject: vi.fn(), updateSelectBtnVisibility: vi.fn(),
  renderSteps: vi.fn(), renderVideoList: vi.fn(),
}));
vi.mock('../select-btn.js', () => ({ selectVideosButtonHtml: vi.fn(() => '') }));
vi.mock('../editor.js', () => ({ renderActiveTab: vi.fn() }));

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

describe('selectVideo request ordering', () => {
  beforeEach(async () => {
    elements.clear();
    const { state } = await import('../state.js');
    Object.assign(state, {
      currentProjectName: null,
      currentVideo: null,
      currentEntity: 'video',
      currentDay: 'day1',
      dirty: false,
      plan: {},
      previewActive: false,
      source: 'compressed',
      texts: null,
      voiceover: null,
      transcript: null,
      videos: [
        { file: 'a.mp4', text_json: 'a.json' },
        { file: 'b.mp4', text_json: 'b.json' },
      ],
    });
  });

  it('ignores a slower response from the previously selected video', async () => {
    const a = deferred();
    const b = deferred();
    const { api } = await import('../api.js');
    api.mockImplementation((_method, url) => url.includes('a.json') ? a.promise : b.promise);
    const { selectVideo } = await import('../sidebar.js');
    const { state } = await import('../state.js');

    const first = selectVideo('a.mp4');
    const second = selectVideo('b.mp4');
    b.resolve({ title: 'B' });
    await second;
    expect(state.texts).toEqual({ title: 'B' });

    a.resolve({ title: 'A' });
    await first;
    expect(state.currentVideo).toBe('b.mp4');
    expect(state.texts).toEqual({ title: 'B' });
  });

  it('restores the requested time and playback after metadata loads', async () => {
    const { state } = await import('../state.js');
    state.source = 'original';
    state.videos = [{ file: 'a.mp4', offset_sec: 120 }];

    const { selectVideo } = await import('../sidebar.js');
    await selectVideo('a.mp4', { seekSec: 135, play: true });

    const player = element('player');
    player.duration = 300;
    player.onloadedmetadata();

    expect(player.currentTime).toBe(135);
    expect(player.play).toHaveBeenCalledOnce();
  });
});
