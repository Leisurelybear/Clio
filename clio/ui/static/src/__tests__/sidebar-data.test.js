import { beforeEach, describe, it, expect, vi } from 'vitest';

vi.mock('../api.js', async () => {
  const actual = await vi.importActual('../api.js');
  return {
    ...actual,
    api: vi.fn(),
  };
});

vi.mock('../utils.js', async () => {
  const actual = await vi.importActual('../utils.js');
  return {
    ...actual,
    setStatus: vi.fn(),
    $: vi.fn().mockReturnValue(document.createElement('div')),
    $$: vi.fn().mockReturnValue([]),
    escapeHtml: actual.escapeHtml,
  };
});

beforeEach(() => {
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe('relinkVideo', () => {
  it('calls api with correct params when user provides new path', async () => {
    const { api } = await import('../api.js');
    api.mockResolvedValue({ ok: true, path: 'D:/new/video.mp4' });
    vi.spyOn(window, 'prompt').mockReturnValue('D:/new/video.mp4');

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(api).toHaveBeenCalledWith('PUT', '/api/videos/relink', {
      old_path: 'D:/old/video.mp4',
      new_path: 'D:/new/video.mp4',
    });
  });

  it('does not call api when prompt is cancelled', async () => {
    const { api } = await import('../api.js');
    vi.spyOn(window, 'prompt').mockReturnValue(null);

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(api).not.toHaveBeenCalled();
  });

  it('does not call api when new path is same as old path', async () => {
    const { api } = await import('../api.js');
    vi.spyOn(window, 'prompt').mockReturnValue('D:/old/video.mp4');

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(api).not.toHaveBeenCalled();
  });

  it('shows error status when api returns error', async () => {
    const { api } = await import('../api.js');
    const { setStatus } = await import('../utils.js');
    api.mockResolvedValue({ ok: false, error: '文件不存在' });
    vi.spyOn(window, 'prompt').mockReturnValue('D:/new/video.mp4');

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(setStatus).toHaveBeenCalledWith('重新关联失败: 文件不存在', 'err');
  });

  it('shows error status when api call throws', async () => {
    const { api } = await import('../api.js');
    const { setStatus } = await import('../utils.js');
    api.mockRejectedValue(new Error('网络错误'));
    vi.spyOn(window, 'prompt').mockReturnValue('D:/new/video.mp4');

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', 'D:/old/video.mp4');

    expect(setStatus).toHaveBeenCalledWith('重新关联失败: 网络错误', 'err');
  });

  it('falls back to file name when absPath is not provided', async () => {
    const { api } = await import('../api.js');
    api.mockResolvedValue({ ok: true, path: 'D:/new/video.mp4' });
    vi.spyOn(window, 'prompt').mockReturnValue('D:/new/video.mp4');

    const { relinkVideo } = await import('../sidebar-data.js');
    await relinkVideo('video.mp4', null);

    expect(api).toHaveBeenCalledWith('PUT', '/api/videos/relink', {
      old_path: 'video.mp4',
      new_path: 'D:/new/video.mp4',
    });
  });
});
