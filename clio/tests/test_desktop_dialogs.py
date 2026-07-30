# clio/tests/test_desktop_dialogs.py
from __future__ import annotations

from clio.desktop import dialogs


def test_envelope_path_success_and_cancel():
    assert dialogs.envelope_path(r"D:\trip") == {"ok": True, "path": r"D:\trip"}
    assert dialogs.envelope_path(None) == {"ok": False, "cancelled": True}
    assert dialogs.envelope_path("") == {"ok": False, "cancelled": True}


def test_envelope_paths_success_and_cancel():
    assert dialogs.envelope_paths([r"D:\a.mp4"]) == {"ok": True, "paths": [r"D:\a.mp4"]}
    assert dialogs.envelope_paths([]) == {"ok": False, "cancelled": True}


def test_envelope_error():
    assert dialogs.envelope_error("boom") == {"ok": False, "error": "boom"}


def test_pick_folder_uses_initial_and_returns_abs(monkeypatch, tmp_path):
    chosen = tmp_path / "out"
    chosen.mkdir()
    seen = {}

    def fake_ask(initialdir=None, **kwargs):
        seen["initialdir"] = initialdir
        return str(chosen)

    monkeypatch.setattr(dialogs, "_askdirectory", fake_ask)
    assert dialogs.pick_folder(str(tmp_path)) == str(chosen.resolve())
    assert seen["initialdir"] == str(tmp_path)


def test_pick_folder_cancel(monkeypatch):
    monkeypatch.setattr(dialogs, "_askdirectory", lambda **kwargs: "")
    assert dialogs.pick_folder() is None


def test_pick_files_filters_and_multiple(monkeypatch, tmp_path):
    f1 = tmp_path / "a.mp4"
    f2 = tmp_path / "b.mov"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    monkeypatch.setattr(
        dialogs,
        "_askopenfilenames",
        lambda **kwargs: (str(f1), str(f2)),
    )
    paths = dialogs.pick_files(str(tmp_path), multiple=True)
    assert paths == [str(f1.resolve()), str(f2.resolve())]


def test_pick_file_single(monkeypatch, tmp_path):
    f1 = tmp_path / "a.mp4"
    f1.write_bytes(b"x")
    monkeypatch.setattr(dialogs, "_askopenfilename", lambda **kwargs: str(f1))
    assert dialogs.pick_file(str(tmp_path)) == str(f1.resolve())
