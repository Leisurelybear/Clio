from __future__ import annotations

from pathlib import Path, PureWindowsPath
from unittest.mock import MagicMock

from clio.ui.routes.fs import _is_allowed_path, handle_get_fs_dirs, handle_get_fs_videos, handle_post_fs_mkdir


class TestIsAllowedPath:
    def test_home_dir_returns_true(self):
        home = Path.home()
        p = home / "subdir" / "project"
        assert _is_allowed_path(p) is True

    def test_non_home_returns_false_on_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        p = Path("/nonexistent_test_path_xyz")
        assert _is_allowed_path(p) is False

    def test_root_drive_win32_returns_true(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        p = PureWindowsPath("C:\\")
        assert _is_allowed_path(p) is True

    def test_root_drive_linux_returns_false(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        p = Path("/")
        assert _is_allowed_path(p) is False


class TestHandleGetFsDirs:
    def test_empty_path_win32_returns_drives(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("clio.ui.routes.fs._list_drives", lambda: ["C:\\", "D:\\"])
        handler = MagicMock()

        handle_get_fs_dirs(handler, {"path": [""]})

        handler._send_json.assert_called_once_with(
            {"path": "", "dirs": ["C:\\", "D:\\"], "parent": None, "is_drive_list": True}
        )

    def test_empty_path_linux_returns_root(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")
        handler = MagicMock()

        handle_get_fs_dirs(handler, {"path": [""]})

        handler._send_json.assert_called_once_with({"path": "/", "dirs": ["/"], "parent": None, "is_drive_list": True})

    def test_valid_path_returns_sorted_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)
        (tmp_path / "b_dir").mkdir()
        (tmp_path / "a_dir").mkdir()
        (tmp_path / ".hidden").mkdir()
        f = tmp_path / "file.txt"
        f.write_bytes(b"")

        handler = MagicMock()
        handle_get_fs_dirs(handler, {"path": [str(tmp_path)]})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args.args[0]
        assert payload["dirs"] == [
            str(tmp_path / "a_dir"),
            str(tmp_path / "b_dir"),
        ]
        assert payload["is_drive_list"] is False
        assert payload["path"] == str(tmp_path.resolve())
        assert payload["parent"] == str(tmp_path.parent)

    def test_path_traversal_returns_403(self, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: False)
        handler = MagicMock()

        handle_get_fs_dirs(handler, {"path": [".."]})

        handler._send_json.assert_called_once_with({"error": "access denied"}, 403)

    def test_non_directory_returns_400(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)
        f = tmp_path / "file.txt"
        f.write_bytes(b"")

        handler = MagicMock()
        handle_get_fs_dirs(handler, {"path": [str(f)]})

        handler._send_json.assert_called_once_with({"error": "not a directory"}, 400)

    def test_scandir_permission_error_returns_empty_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)

        def mock_scandir(_path):
            raise PermissionError("access denied")

        monkeypatch.setattr("os.scandir", mock_scandir)

        handler = MagicMock()
        handle_get_fs_dirs(handler, {"path": [str(tmp_path)]})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args.args[0]
        assert payload["dirs"] == []

    def test_permission_error_returns_403(self, monkeypatch):
        def mock_is_allowed(resolved):
            raise PermissionError("access denied")

        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", mock_is_allowed)

        handler = MagicMock()
        handle_get_fs_dirs(handler, {"path": ["some/path"]})

        handler._send_json.assert_called_once_with({"error": "access denied"}, 403)

    def test_os_error_returns_500(self, monkeypatch):
        def mock_resolve(self, strict=False):
            raise OSError("disk failure")

        monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)

        handler = MagicMock()
        handle_get_fs_dirs(handler, {"path": ["some/path"]})

        handler._send_json.assert_called_once_with({"error": "disk failure"}, 500)


class TestHandleGetFsVideos:
    def test_requires_path(self):
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": [""]})
        handler._send_json.assert_called_once_with({"error": "path is required"}, 400)

    def test_access_denied(self, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: False)
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": ["C:\\Windows"]})
        handler._send_json.assert_called_once_with({"error": "access denied"}, 403)

    def test_non_directory_returns_400(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)
        f = tmp_path / "file.txt"
        f.write_bytes(b"")
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": [str(f)]})
        handler._send_json.assert_called_once_with({"error": "not a directory"}, 400)

    def test_lists_video_files_only(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)
        (tmp_path / "a.mp4").write_bytes(b"")
        (tmp_path / "b.mov").write_bytes(b"")
        (tmp_path / "c.txt").write_bytes(b"")
        (tmp_path / ".hidden.mp4").write_bytes(b"")

        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": [str(tmp_path)]})

        handler._send_json.assert_called_once()
        payload = handler._send_json.call_args.args[0]
        assert payload["path"] == str(tmp_path.resolve())
        assert len(payload["files"]) == 2
        assert [f["name"] for f in payload["files"]] == ["a.mp4", "b.mov"]
        assert payload["parent"] == str(tmp_path.parent)

    def test_includes_file_sizes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x" * 1234)
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": [str(tmp_path)]})
        payload = handler._send_json.call_args.args[0]
        assert payload["files"][0]["size"] == 1234

    def test_permission_error_returns_403(self, monkeypatch):
        def mock_is_allowed(resolved):
            raise PermissionError("access denied")

        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", mock_is_allowed)
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": ["some/path"]})
        handler._send_json.assert_called_once_with({"error": "access denied"}, 403)

    def test_os_error_returns_500(self, monkeypatch):
        def mock_resolve(self, strict=False):
            raise OSError("disk failure")

        monkeypatch.setattr("pathlib.Path.resolve", mock_resolve)
        handler = MagicMock()
        handle_get_fs_videos(handler, {"path": ["some/path"]})
        handler._send_json.assert_called_once_with({"error": "disk failure"}, 500)

    def test_drive_subdir_win32_returns_true(self, monkeypatch):
        """Any path on a Windows drive letter is allowed (not just drive root)."""
        monkeypatch.setattr("sys.platform", "win32")
        p = PureWindowsPath(r"D:\GoPro\trip1")
        assert _is_allowed_path(p) is True


class TestHandlePostFsMkdir:
    def test_missing_parent_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"name": "newdir"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "parent and name required"}, 400)

    def test_missing_name_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "parent and name required"}, 400)

    def test_empty_name_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": "  "})
        handler._send_json.assert_called_once_with({"ok": False, "error": "parent and name required"}, 400)

    def test_name_with_slash_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": "a/b"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "invalid name"}, 400)

    def test_name_with_backslash_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": "a\\b"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "invalid name"}, 400)

    def test_name_with_dotdot_returns_400(self):
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": ".."})
        handler._send_json.assert_called_once_with({"ok": False, "error": "invalid name"}, 400)

    def test_parent_not_allowed_returns_403(self, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: False)
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": "newdir"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "access denied"}, 403)

    def test_new_dir_not_allowed_returns_403(self, tmp_path, monkeypatch):
        """New dir resolves outside the allowed tree after symlink."""
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: p == tmp_path.resolve())
        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": str(tmp_path), "name": "newdir"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "access denied"}, 403)

    def test_os_error_returns_500(self, monkeypatch):
        monkeypatch.setattr("clio.ui.routes.fs._is_allowed_path", lambda p: True)

        def mock_mkdir(*a, **kw):
            raise OSError("permission denied")

        monkeypatch.setattr("pathlib.Path.mkdir", mock_mkdir)

        handler = MagicMock()
        handle_post_fs_mkdir(handler, {"parent": "/tmp", "name": "newdir"})
        handler._send_json.assert_called_once_with({"ok": False, "error": "permission denied"}, 500)
