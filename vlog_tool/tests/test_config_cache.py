"""Tests for vlog_tool/ui/services/config_cache.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vlog_tool.ui.services.config_cache import ConfigCache

# ===========================================================================
# __init__
# ===========================================================================


class TestInit:
    def test_stores_attributes(self):
        def on_load(c):
            return None

        cache = ConfigCache(Path("/cfg.yaml"), maxsize=10, on_load=on_load)
        assert cache._config_path == Path("/cfg.yaml")
        assert cache._maxsize == 10
        assert cache._on_load is on_load
        assert cache._cache == {}
        assert cache._meta == {}
        assert cache._lock is not None


# ===========================================================================
# _read_mtime
# ===========================================================================


class TestReadMtime:
    def test_none_returns_zero(self):
        assert ConfigCache._read_mtime(None) == 0.0

    def test_nonexistent_path_returns_zero(self):
        assert ConfigCache._read_mtime(Path("/nonexistent/12345")) == 0.0

    def test_existing_path(self, tmp_path: Path):
        f = tmp_path / "test.yaml"
        f.write_text("key: val", encoding="utf-8")
        mtime = ConfigCache._read_mtime(f)
        assert isinstance(mtime, float)
        assert mtime > 0


# ===========================================================================
# get — basic
# ===========================================================================


class TestGet:
    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_get_global_key(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)
        result = cache.get(None)
        mock_load.assert_called_once_with(None, project_dir=None)
        assert result is not mock_cfg  # deep copy

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_get_project_key(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)
        proj = Path("/my/project")
        result = cache.get(proj)
        mock_load.assert_called_once_with(None, project_dir=proj)
        assert result is not mock_cfg

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_returns_deep_copy(self, mock_load):
        """Each call should return a different object (deep copy)."""
        orig = MagicMock()
        orig.some_attr = "value"
        mock_load.return_value = orig
        cache = ConfigCache(None)
        r1 = cache.get(None)
        r2 = cache.get(None)
        assert r1 is not r2
        assert r1 is not orig

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_on_load_called(self, mock_load):
        on_load = MagicMock()
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None, on_load=on_load)
        cache.get(None)
        on_load.assert_called_once_with(mock_cfg)

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_on_load_not_called_on_cache_hit(self, mock_load):
        on_load = MagicMock()
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None, on_load=on_load)
        cache.get(None)
        cache.get(None)
        assert on_load.call_count == 1  # only called on first load


# ===========================================================================
# get — cache hit/miss based on mtime
# ===========================================================================


class TestCacheHitMiss:
    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_cache_hit_returns_cached(self, mock_load):
        """When config_path is None, _read_mtime always returns 0.0 → cache hit on 2nd call."""
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)
        cache.get(None)
        cache.get(None)
        assert mock_load.call_count == 1

    @patch("vlog_tool.ui.services.config_cache.load_config")
    @patch.object(Path, "stat")
    def test_cache_miss_on_mtime_change(self, mock_stat, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        mock_stat.return_value.st_mtime = 100.0
        cache = ConfigCache(Path("/fake/config.yaml"))
        cache.get(None)  # loads once
        mock_stat.return_value.st_mtime = 200.0  # mtime changes
        cache.get(None)  # reloads
        assert mock_load.call_count == 2

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_cache_miss_on_project_yaml_change(self, mock_load):
        """Simulate project.yaml mtime change by using config_path=None (all 0 mtimes)
        and checking that a different project_input triggers reload."""
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)

        cache.get(None)
        cache.get(Path("/different/proj"))
        assert mock_load.call_count == 2

    @patch("vlog_tool.ui.services.config_cache.load_config")
    @patch.object(Path, "stat")
    def test_cache_hit_when_mtime_unchanged(self, mock_stat, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        mock_stat.return_value.st_mtime = 100.0
        cache = ConfigCache(Path("/fake/config.yaml"))
        cache.get(None)  # loads
        cache.get(None)  # cache hit
        assert mock_load.call_count == 1

    @patch("vlog_tool.ui.services.config_cache.load_config")
    @patch.object(Path, "stat")
    def test_project_key_cache_independence(self, mock_stat, mock_load):
        """Different project keys should not interfere."""
        mock_cfg_a = MagicMock()
        mock_cfg_b = MagicMock()
        mock_load.return_value = mock_cfg_a
        mock_stat.return_value.st_mtime = 100.0
        cache = ConfigCache(Path("/fake/config.yaml"))
        cache.get(Path("/proj/a"))
        mock_load.return_value = mock_cfg_b
        cache.get(Path("/proj/b"))
        assert mock_load.call_count == 2


# ===========================================================================
# invalidate_all / invalidate_key / keys
# ===========================================================================


class TestInvalidation:
    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_keys(self, mock_load):
        mock_load.return_value = MagicMock()
        cache = ConfigCache(None)
        assert cache.keys() == []
        cache.get(None)
        assert cache.keys() == ["__global__"]
        cache.get(Path("/proj/x"))
        keys = set(cache.keys())
        assert keys == {"__global__", str(Path("/proj/x").resolve())}

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_invalidate_all(self, mock_load):
        mock_load.return_value = MagicMock()
        cache = ConfigCache(None)
        cache.get(None)
        cache.get(Path("/proj/x"))
        assert len(cache.keys()) == 2
        cache.invalidate_all()
        assert cache.keys() == []

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_invalidate_key(self, mock_load):
        mock_load.return_value = MagicMock()
        cache = ConfigCache(None)
        cache.get(None)
        assert "__global__" in cache.keys()
        cache.invalidate_key("__global__")
        assert "__global__" not in cache.keys()

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_invalidate_key_nonexistent(self, mock_load):
        """Removing a non-existent key should not raise."""
        mock_load.return_value = MagicMock()
        cache = ConfigCache(None)
        cache.invalidate_key("nope")  # should not raise


# ===========================================================================
# LRU eviction
# ===========================================================================


class TestLRUEviction:
    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_evicts_when_over_maxsize(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None, maxsize=2)

        p1 = Path("/proj/1")
        p2 = Path("/proj/2")
        p3 = Path("/proj/3")

        cache.get(p1)
        cache.get(p2)
        assert len(cache.keys()) == 2

        cache.get(p3)  # should evict p1
        keys = cache.keys()
        assert len(keys) == 2
        assert str(p1.resolve()) not in keys
        assert str(p2.resolve()) in keys
        assert str(p3.resolve()) in keys

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_global_key_evicted_too(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None, maxsize=1)

        cache.get(None)  # fills cache
        cache.get(Path("/proj/x"))  # evicts global

        keys = cache.keys()
        assert "__global__" not in keys
        assert str(Path("/proj/x").resolve()) in keys

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_cache_grows_under_maxsize(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None, maxsize=20)

        for i in range(10):
            cache.get(Path(f"/proj/{i}"))
        assert len(cache.keys()) == 10


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_reload_after_config_path_changes(self, mock_load):
        """If config_path is a real file and both cfg and proj mtimes are 0,
        the second call should still be a cache hit when config is None."""
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)

        # Two requests with the same parameters
        r1 = cache.get(None)
        r2 = cache.get(None)
        assert mock_load.call_count == 1
        assert r1 is not r2  # deep copy

    @patch("vlog_tool.ui.services.config_cache.load_config")
    def test_meta_cleared_on_invalidate_all(self, mock_load):
        mock_cfg = MagicMock()
        mock_load.return_value = mock_cfg
        cache = ConfigCache(None)
        cache.get(None)
        assert len(cache._meta) == 1
        cache.invalidate_all()
        assert len(cache._meta) == 0
