import hashlib
from pathlib import Path

from app.ingest.source import sha256_file
from scripts.profile_pbp import END_MARKER, START_MARKER, write_section


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    payload = b"playbookiq" * 100_000
    path.write_bytes(payload)
    assert sha256_file(path, chunk_size=4096) == hashlib.sha256(payload).hexdigest()


def test_write_section_appends_then_replaces(tmp_path: Path) -> None:
    doc = tmp_path / "data.md"
    doc.write_text("# Data\n\nIntro.\n")

    write_section(doc, "first run")
    text = doc.read_text()
    assert "Intro." in text
    assert f"{START_MARKER}\nfirst run\n{END_MARKER}" in text

    write_section(doc, "second run")
    text = doc.read_text()
    assert "first run" not in text
    assert text.count(START_MARKER) == 1
    assert "second run" in text
