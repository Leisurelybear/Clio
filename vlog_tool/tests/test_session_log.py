from __future__ import annotations

from unittest.mock import patch

import pytest

from vlog_tool.session_log import _logs, read, write


@pytest.fixture(autouse=True)
def _clear_logs():
    _logs.clear()
    yield
    _logs.clear()


def test_write_adds_line():
    write("hello")
    assert _logs == ["hello"]


def test_write_adds_multiple_lines():
    write("a")
    write("b")
    write("c")
    assert _logs == ["a", "b", "c"]


def test_read_returns_all():
    write("x")
    write("y")
    result = read()
    assert result == {"logs": ["x", "y"], "total": 2}


def test_read_empty():
    result = read()
    assert result == {"logs": [], "total": 0}


def test_read_with_offset():
    write("a")
    write("b")
    write("c")
    result = read(offset=1)
    assert result == {"logs": ["b", "c"], "total": 3}


def test_read_with_offset_beyond_length():
    write("a")
    result = read(offset=10)
    assert result == {"logs": [], "total": 1}


def test_write_enforces_max_limit():
    with patch("vlog_tool.session_log._MAX", 5):
        for i in range(10):
            write(str(i))

    assert _logs == ["5", "6", "7", "8", "9"]


def test_write_does_not_remove_below_limit():
    with patch("vlog_tool.session_log._MAX", 5):
        for i in range(5):
            write(str(i))

    assert _logs == ["0", "1", "2", "3", "4"]


def test_clear_empties_logs():
    write("a")
    write("b")
    assert len(read()["logs"]) == 2
    _logs.clear()
    assert read() == {"logs": [], "total": 0}


def test_read_returns_copy_not_reference():
    write("a")
    result = read()
    result["logs"].append("bogus")
    assert _logs == ["a"]
