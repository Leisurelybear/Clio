from __future__ import annotations

from unittest.mock import patch

import pytest

from clio.session_log import _logs, clear, read, write


@pytest.fixture(autouse=True)
def _clear_logs():
    _logs.clear()
    yield
    _logs.clear()


def test_write_adds_entry_with_ts_and_text():
    write("hello")
    assert len(_logs) == 1
    entry = _logs[0]
    assert entry["text"] == "hello"
    assert isinstance(entry["ts"], float)
    assert entry["ts"] > 0


def test_write_adds_multiple_entries():
    write("a")
    write("b")
    write("c")
    assert [e["text"] for e in _logs] == ["a", "b", "c"]
    assert _logs[0]["ts"] <= _logs[1]["ts"] <= _logs[2]["ts"]


def test_read_returns_all_objects():
    write("x")
    write("y")
    result = read()
    assert result["total"] == 2
    assert result["logs"][0]["text"] == "x"
    assert result["logs"][1]["text"] == "y"
    assert isinstance(result["logs"][0]["ts"], float)


def test_read_empty():
    result = read()
    assert result == {"logs": [], "total": 0}


def test_read_with_offset():
    write("a")
    write("b")
    write("c")
    result = read(offset=1)
    assert result["total"] == 3
    assert [e["text"] for e in result["logs"]] == ["b", "c"]


def test_read_with_offset_beyond_length():
    write("a")
    result = read(offset=10)
    assert result == {"logs": [], "total": 1}


def test_write_enforces_max_limit():
    with patch("clio.session_log._MAX", 5):
        for i in range(10):
            write(str(i))
    assert [e["text"] for e in _logs] == ["5", "6", "7", "8", "9"]


def test_write_does_not_remove_below_limit():
    with patch("clio.session_log._MAX", 5):
        for i in range(5):
            write(str(i))
    assert [e["text"] for e in _logs] == ["0", "1", "2", "3", "4"]


def test_clear_empties_logs():
    write("a")
    write("b")
    assert len(read()["logs"]) == 2
    clear()
    assert read() == {"logs": [], "total": 0}


def test_read_returns_copy_not_reference():
    write("a")
    result = read()
    result["logs"].append({"ts": 0.0, "text": "bogus"})
    assert len(_logs) == 1
    assert _logs[0]["text"] == "a"


def test_write_uses_time_time_for_ts():
    with patch("clio.session_log.time.time", return_value=1721606400.5):
        write("clocked")
    assert _logs[0]["ts"] == 1721606400.5
    assert _logs[0]["text"] == "clocked"
