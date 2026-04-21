from pathlib import Path

from core.state import EpisodeStatus, StateStore


def _fresh(tmp_path: Path) -> StateStore:
    db = StateStore(tmp_path / "s.sqlite")
    db.init_schema()
    return db


def test_init_creates_schema(tmp_path: Path):
    _fresh(tmp_path)
    assert (tmp_path / "s.sqlite").exists()


def test_insert_and_get_episode(tmp_path: Path):
    db = _fresh(tmp_path)
    db.upsert_episode(
        show_slug="foo", guid="abc", title="Ep 1", pub_date="2026-04-01", mp3_url="https://x/1.mp3"
    )
    ep = db.get_episode("abc")
    assert ep["show_slug"] == "foo"
    assert ep["status"] == EpisodeStatus.PENDING.value


def test_upsert_is_idempotent(tmp_path: Path):
    db = _fresh(tmp_path)
    db.upsert_episode(show_slug="s", guid="g", title="T", pub_date="2026-04-01", mp3_url="u")
    db.upsert_episode(show_slug="s", guid="g", title="T2", pub_date="2026-04-01", mp3_url="u")
    assert db.get_episode("g")["title"] == "T2"


def test_set_status_transitions(tmp_path: Path):
    db = _fresh(tmp_path)
    db.upsert_episode(show_slug="s", guid="g", title="T", pub_date="2026-04-01", mp3_url="u")
    db.set_status("g", EpisodeStatus.DOWNLOADING)
    assert db.get_episode("g")["status"] == "downloading"
    db.set_status("g", EpisodeStatus.DONE)
    assert db.get_episode("g")["status"] == "done"
    assert db.get_episode("g")["completed_at"]


def test_recovery_resets_in_flight(tmp_path: Path):
    db = _fresh(tmp_path)
    db.upsert_episode(show_slug="s", guid="g1", title="T", pub_date="2026-04-01", mp3_url="u")
    db.set_status("g1", EpisodeStatus.DOWNLOADING)
    db.upsert_episode(show_slug="s", guid="g2", title="T", pub_date="2026-04-01", mp3_url="u")
    db.set_status("g2", EpisodeStatus.TRANSCRIBING)
    reset = db.recover_in_flight()
    assert reset == 2
    assert db.get_episode("g1")["status"] == "pending"


def test_meta_kv(tmp_path: Path):
    db = _fresh(tmp_path)
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"
    assert db.get_meta("missing") is None


def test_list_by_status(tmp_path: Path):
    db = _fresh(tmp_path)
    for i, s in enumerate(["a", "b", "c"]):
        db.upsert_episode(show_slug="x", guid=s, title=s, pub_date=f"2026-04-0{i + 1}", mp3_url="u")
    db.set_status("b", EpisodeStatus.DONE)
    pend = db.list_by_status("x", EpisodeStatus.PENDING)
    assert [p["guid"] for p in pend] == ["a", "c"]
