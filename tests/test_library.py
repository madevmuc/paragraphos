import shutil
from pathlib import Path

from core.library import LibraryIndex

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.md"


def _seed(root: Path, rel: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, target)
    return target


def test_scan_picks_up_existing_transcripts(tmp_path: Path):
    _seed(tmp_path, "demo/2026-04-01_1_sample.md")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    assert idx.has_guid("abc-123")


def test_dedup_by_guid(tmp_path: Path):
    _seed(tmp_path, "demo/2026-04-01_1_sample.md")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    r = idx.check_dedup(guid="abc-123", filename_key=None)
    assert r.matched is True and r.reason == "guid"


def test_dedup_by_filename(tmp_path: Path):
    _seed(tmp_path, "demo/2026-04-01_1_sample.md")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    r = idx.check_dedup(guid="new-guid", filename_key="2026-04-01_1_sample")
    assert r.matched is True and r.reason == "filename"


def test_dedup_miss(tmp_path: Path):
    _seed(tmp_path, "demo/2026-04-01_1_sample.md")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    r = idx.check_dedup(guid="other", filename_key="2026-04-02_2_x")
    assert r.matched is False


def test_frontmatter_less_file_indexed_by_filename(tmp_path: Path):
    p = tmp_path / "demo/2026-04-05_5_loose.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("no frontmatter at all", encoding="utf-8")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    r = idx.check_dedup(guid="unk", filename_key="2026-04-05_5_loose")
    assert r.matched is True and r.reason == "filename"


def test_index_md_is_ignored(tmp_path: Path):
    p = tmp_path / "demo/index.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('---\nguid: "should-ignore"\n---\nhello', encoding="utf-8")
    idx = LibraryIndex(tmp_path)
    idx.scan()
    assert not idx.has_guid("should-ignore")
