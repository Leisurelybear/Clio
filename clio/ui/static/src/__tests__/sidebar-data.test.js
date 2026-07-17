import { beforeEach, describe, it, expect, vi } from 'vitest';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual,
    api: vi.fn(),
  };
});

function mockEl() {
  return {
    textContent: '',
    innerHTML: '',
    style: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    appendChild() {},
    addEventListener() {},
    removeEventListener() {},
    closest() { return null; },
  };
}

vi.mock('../utils.js', async () => {
  const actual = await vi.importActual('../utils.js');
  return {
    ...actual,
    setStatus: vi.fn(),
    $: vi.fn(() => mockEl()),
    $$: vi.fn().mockReturnValue([]),
    escapeHtml: actual.escapeHtml,
    updateProjectSidebar: vi.fn(),
  };
});

vi.mock('../runner.js', () => ({
  updateRunFilesBadge: vi.fn(),
}));

vi.mock('../sidebar-relink.js', () => ({
  openRelinkModal: vi.fn(),
  closeRelinkModal: vi.fn(),
}));

beforeEach(() => {
  vi.resetModules();
});

describe('relinkVideo', () => {
  it('opens relink modal with old path instead of using prompt', async () => {
    const { openRelinkModal } = await import('../sidebar-relink.js');
    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(openRelinkModal).toHaveBeenCalledWith({
      oldPath: 'D:/old/video.mp4',
      displayName: 'video.mp4',
    });
  });

  it('falls back to file name when absPath is not provided', async () => {
    const { openRelinkModal } = await import('../sidebar-relink.js');
    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', null);

    expect(openRelinkModal).toHaveBeenCalledWith({
      oldPath: 'video.mp4',
      displayName: 'video.mp4',
    });
  });
});

describe('submitRelink', () => {
  it('calls api with correct params', async () => {
    const { api } = await import('../api.js');
    api.mockImplementation(async (method, url) => {
      if (method === 'PUT' && url === '/api/videos/relink') {
        return { ok: true, path: 'D:/new/video.mp4' };
      }
      if (method === 'GET' && String(url).startsWith('/api/videos')) {
        return { videos: [], groups: {} };
      }
      return {};
    });

    const { submitRelink } = await import('../sidebar-data.js');
    const r = await submitRelink('D:/old/video.mp4', 'D:/new/video.mp4');

    expect(api).toHaveBeenCalledWith('PUT', '/api/videos/relink', {
      old_path: 'D:/old/video.mp4',
      new_path: 'D:/new/video.mp4',
    });
    expect(r.ok).toBe(true);
  });

  it('shows error status when api returns error', async () => {
    const { api } = await import('../api.js');
    const { setStatus } = await import('../utils.js');
    api.mockResolvedValue({ ok: false, error: '文件不存在' });

    const { submitRelink } = await import('../sidebar-data.js');
    await submitRelink('D:/old/video.mp4', 'D:/new/video.mp4');

    expect(setStatus).toHaveBeenCalledWith('重新关联失败: 文件不存在', 'err');
  });

  it('propagates network errors from api', async () => {
    const { api } = await import('../api.js');
    api.mockRejectedValue(new Error('网络错误'));

    const { submitRelink } = await import('../sidebar-data.js');
    await expect(submitRelink('D:/old/video.mp4', 'D:/new/video.mp4')).rejects.toThrow('网络错误');
  });
});


describe('videoThumbHtml', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('renders icon placeholder when no cover_file', async () => {
    const { videoThumbHtml } = await import('../sidebar-data.js');
    const html = videoThumbHtml({ file: 'a.mp4' });
    expect(html).toContain('video-thumb');
    expect(html).not.toContain('has-cover');
    expect(html).not.toContain('/api/cover');
  });

  it('renders cover img with project params when cover_file set', async () => {
    const { state } = await import('../state.js');
    state.currentProjectName = 'France';
    state.currentProjectDir = 'D:/vlog/France';
    sessionStorage.setItem('api_token', 'tok123');

    const { videoThumbHtml } = await import('../sidebar-data.js');
    const html = videoThumbHtml({ cover_file: 'covers/001_title.jpg' });
    expect(html).toContain('has-cover');
    expect(html).toContain('/api/cover?');
    expect(html).toContain('file=001_title.jpg');
    expect(html).toContain('project=France');
    expect(html).toContain('token=tok123');
    expect(html).toContain('video-thumb-fallback');
  });
});
