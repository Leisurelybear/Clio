"""Tests for clio/index.py — ArtifactIndex, ArtifactGroup."""

from __future__ import annotations

import json
from pathlib import Path

from clio.identity import MediaIdentity, _identity_to_dict
from clio.vmeta import VideoMeta


def _make_text_json(path: Path, compressed_stem: str, index: str, title: str):
    """Create a v2 text JSON file with media_identity."""
    identity = MediaIdentity(
        original_stem="GL010683",
        original_path=str(path.parent.parent / "GL010683.mp4"),
        compressed_stem=compressed_stem,
        compressed_path=str(path.parent.parent / "compressed" / f"{compressed_stem}.mp4"),
        index=index,
        segment_index=None,
        segment_offset_sec=0.0,
        segment_duration_sec=None,
    )
    data = {
        "version": 2,
        "title": title,
        "compressed_file": f"{compressed_stem}.mp4",
        "media_identity": _identity_to_dict(identity),
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _make_script_json(path: Path, text_stem: str):
    """Create a voiceover JSON file."""
    data = {"version": 2, "text": f"Voiceover for {text_stem}"}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _make_transcript_json(path: Path, compressed_stem: str):
    """Create a transcription JSON file with media_identity."""
    identity = MediaIdentity(
        original_stem="GL010683",
        original_path="",
        compressed_stem=compressed_stem,
        compressed_path="",
        index=compressed_stem.split("_")[0],
        segment_index=None,
        segment_offset_sec=0.0,
        segment_duration_sec=None,
    )
    data = {
        "version": 2,
        "segments": [],
        "media_identity": _identity_to_dict(identity),
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class TestArtifactIndexBuild:
    """Verify ArtifactIndex scans directories and builds correct maps."""

    def test_build_and_lookup_by_compressed_stem(self, tmp_path: Path):
        compressed_dir = tmp_path / "compressed"
        texts_dir = tmp_path / "texts"
        scripts_dir = tmp_path / "scripts"
        transcripts_dir = tmp_path / "transcripts"
        covers_dir = tmp_path / "covers"
        for d in [compressed_dir, texts_dir, scripts_dir, transcripts_dir, covers_dir]:
            d.mkdir(parents=True)

        # Create compressed video
        compressed_path = compressed_dir / "001_GL010683.mp4"
        compressed_path.write_bytes(b"\x00" * 100)

        # Create .vmeta
        src = tmp_path / "GL010683.mp4"
        src.write_bytes(b"\x00" * 1000)
        meta = VideoMeta.build(source=src, target=compressed_path, source_duration=120.0, target_duration=120.0)
        meta.write(compressed_path)

        # Create text JSON with identity
        text_path = texts_dir / "001_Sunset_Beach.json"
        _make_text_json(text_path, "001_GL010683", "001", "Sunset Beach")

        # Create script JSON
        script_path = scripts_dir / "001_Sunset_Beach_voiceover.json"
        _make_script_json(script_path, "001_Sunset_Beach")

        # Create transcript JSON
        transcript_path = transcripts_dir / "001_GL010683_transcript.json"
        _make_transcript_json(transcript_path, "001_GL010683")

        # Create cover
        cover_path = covers_dir / "001_Sunset_Beach.jpg"
        cover_path.write_bytes(b"\x00" * 50)

        # --- Test ---
        from clio.index import ArtifactIndex

        index = ArtifactIndex(
            output_dir=tmp_path,
            input_dir=tmp_path,
            compressed_dir=compressed_dir,
            texts_dir=texts_dir,
            scripts_dir=scripts_dir,
            transcripts_dir=transcripts_dir,
            covers_dir=covers_dir,
        )
        index.build()

        group = index.lookup(compressed_stem="001_GL010683")
        assert group is not None
        assert group.compressed.path == compressed_path
        assert group.compressed.stem == "001_GL010683"
        assert len(group.texts) == 1
        assert group.texts[0].path == text_path
        assert group.texts[0].title == "Sunset Beach"
        assert group.script is not None
        assert group.script.path == script_path
        assert group.transcript is not None
        assert group.transcript.path == transcript_path
        assert group.cover is not None
        assert group.cover.path == cover_path
