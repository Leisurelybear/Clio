from __future__ import annotations

from pathlib import Path

from vlog_tool.processing_state import ProcessingState


class TestProcessingState:
    def test_mark_new_file(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        data = state.get_state()
        assert data["version"] == 1
        assert data["steps"] == ["compress", "analyze", "voiceover", "transcribe", "plan", "label"]
        assert data["files"]["GL010683"]["compress"] == "done"

    def test_mark_multiple_steps(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        state.mark("GL010683", "transcribe", "running")
        data = state.get_state()
        assert data["files"]["GL010683"]["compress"] == "done"
        assert data["files"]["GL010683"]["transcribe"] == "running"

    def test_mark_second_file(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        state.mark("GL010684", "compress", "done")
        data = state.get_state()
        assert len(data["files"]) == 2

    def test_mark_unknown_step(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        state.mark("GL010683", "nonexistent", "running")
        data = state.get_state()
        assert data["files"]["GL010683"]["nonexistent"] == "running"

    def test_reset_step(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        state.mark("GL010683", "transcribe", "done")
        state.mark("GL010684", "compress", "done")
        state.reset_step("compress")
        data = state.get_state()
        assert data["files"]["GL010683"]["compress"] is None
        assert data["files"]["GL010683"]["transcribe"] == "done"
        assert data["files"]["GL010684"]["compress"] is None

    def test_persistence(self, tmp_path: Path):
        state1 = ProcessingState(tmp_path)
        state1.mark("GL010683", "compress", "done")
        state2 = ProcessingState(tmp_path)
        data = state2.get_state()
        assert data["files"]["GL010683"]["compress"] == "done"

    def test_corrupted_file_fallback(self, tmp_path: Path):
        pf = tmp_path / ".processing.json"
        pf.write_text("{{{corrupted", encoding="utf-8")
        state = ProcessingState(tmp_path)
        data = state.get_state()
        assert data["version"] == 1
        assert data["files"] == {}

    def test_get_state_returns_deep_copy(self, tmp_path: Path):
        state = ProcessingState(tmp_path)
        state.mark("GL010683", "compress", "done")
        data1 = state.get_state()
        data1["files"]["GL010683"]["compress"] = "modified"
        data2 = state.get_state()
        assert data2["files"]["GL010683"]["compress"] == "done"
