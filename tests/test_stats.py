from pathlib import Path

from core.state import EpisodeStatus, StateStore
from core.stats import (_parse_duration, compute_global_stats,
                        compute_show_stats, format_duration,
                        rescan_library_counts)


def _seed(tmp_path: Path) -> StateStore:
    db = StateStore(tmp_path / "s.sqlite")
    db.init_schema()
    return db


def test_parse_duration():
    assert _parse_duration("2063") == 2063
    assert _parse_duration("14:39") == 14 * 60 + 39
    assert _parse_duration("01:09:45") == 3600 + 9 * 60 + 45
    assert _parse_duration(None) == 0
    assert _parse_duration("") == 0


def test_format_duration():
    assert format_duration(0) == "0m"
    assert format_duration(59) == "0m"
    assert format_duration(60) == "1m"
    assert format_duration(3661) == "1h 1m"
    assert format_duration(90000) == "1d 1h"


def test_global_stats(tmp_path: Path):
    db = _seed(tmp_path)
    db.upsert_episode(show_slug="s", guid="a", title="A",
                      pub_date="2026-04-01", mp3_url="u", duration_sec=600)
    db.upsert_episode(show_slug="s", guid="b", title="B",
                      pub_date="2026-04-02", mp3_url="u", duration_sec=1200)
    db.set_status("a", EpisodeStatus.DONE)
    db.record_completion("a", word_count=3000, duration_sec=600)
    g = compute_global_stats(db)
    assert g.transcripts == 1
    assert g.total_words == 3000
    assert g.total_seconds == 600
    assert g.episodes_pending == 1


def test_show_stats(tmp_path: Path):
    db = _seed(tmp_path)
    for i, guid in enumerate(["x1", "x2", "x3"]):
        db.upsert_episode(show_slug="s", guid=guid, title=f"T{i}",
                          pub_date=f"2026-04-0{i+1}", mp3_url="u",
                          duration_sec=1000 + i * 100)
    db.set_status("x1", EpisodeStatus.DONE)
    db.record_completion("x1", word_count=2000, duration_sec=1000)
    db.set_status("x2", EpisodeStatus.DONE)
    db.record_completion("x2", word_count=3000, duration_sec=1100)
    s = compute_show_stats(db, "s")
    assert s.total == 3
    assert s.done == 2
    assert s.pending == 1
    assert s.total_words == 5000
    assert s.total_seconds == 2100
    assert s.avg_words == 2500


def test_rescan_library_counts(tmp_path: Path):
    db = _seed(tmp_path)
    db.upsert_episode(show_slug="demo", guid="gg", title="t",
                      pub_date="2026-04-01", mp3_url="u")
    out = tmp_path / "out" / "demo"
    out.mkdir(parents=True)
    md = out / "2026-04-01_1_x.md"
    md.write_text('---\nguid: "gg"\n---\n\n' + "word " * 500, encoding="utf-8")
    (out / "2026-04-01_1_x.srt").write_text(
        "1\n00:00:00,000 --> 00:10:30,000\nhi\n", encoding="utf-8")
    updated = rescan_library_counts(db, tmp_path / "out")
    assert updated == 1
    ep = db.get_episode("gg")
    assert ep["word_count"] == 500
    assert ep["duration_sec"] == 10 * 60 + 30


def test_prompt_coverage_empty_inputs():
    from core.stats import prompt_coverage
    assert prompt_coverage("", ["blah"]) == 0.0
    assert prompt_coverage("foo, bar", []) == 0.0


def test_prompt_coverage_basic():
    from core.stats import prompt_coverage
    prompt = "KfW, Grunderwerbsteuer, Mietspiegel, Kapitalanlage"
    transcripts = [
        "Die KfW-Förderung und die Grunderwerbsteuer sind wichtig.",
        "Wer Kapitalanlage sucht, sollte den Mietspiegel kennen.",
    ]
    # All 4 tokens appear
    assert prompt_coverage(prompt, transcripts) == 1.0


def test_prompt_coverage_partial():
    from core.stats import prompt_coverage
    prompt = "Alpha, Beta, Gamma, Delta, Epsilon"
    transcripts = ["Alpha appears. Beta appears."]
    # 2 of 5 = 0.4
    assert abs(prompt_coverage(prompt, transcripts) - 0.4) < 0.01


def test_prompt_coverage_low_triggers_flag_threshold():
    from core.stats import prompt_coverage
    prompt = "KfW, Grunderwerbsteuer, Mietspiegel, Kapitalanlage, Rendite, Zinsbindung"
    # Entirely unrelated transcripts
    transcripts = ["Ich ging heute in den Supermarkt und kaufte Brot."]
    assert prompt_coverage(prompt, transcripts) < 0.2
