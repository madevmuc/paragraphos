from pathlib import Path

from core.cleanup import delete_episode_audio, delete_show_audio


def test_episode_delete_removes_mp3_keeps_md_and_srt(tmp_path):
    show = tmp_path / "tech"
    show.mkdir()
    (show / "ep-001.mp3").write_bytes(b"audio")
    (show / "ep-001.md").write_text("transcript")
    (show / "ep-001.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")

    delete_episode_audio(show, basename="ep-001")

    assert not (show / "ep-001.mp3").exists()
    assert (show / "ep-001.md").exists()
    assert (show / "ep-001.srt").exists()


def test_episode_delete_is_idempotent(tmp_path):
    show = tmp_path / "tech"
    show.mkdir()
    (show / "ep-001.md").write_text("transcript")
    # Calling with no .mp3 present must not raise.
    delete_episode_audio(show, basename="ep-001")
    assert (show / "ep-001.md").exists()


def test_show_delete_removes_all_mp3s_keeps_rest(tmp_path):
    show = tmp_path / "tech"
    show.mkdir()
    for guid in ("a", "b", "c"):
        (show / f"{guid}.mp3").write_bytes(b"audio")
        (show / f"{guid}.md").write_text("t")
        (show / f"{guid}.srt").write_text("s")
    # A file that isn't audio/transcript — should be preserved.
    (show / "cover.jpg").write_bytes(b"img")

    delete_show_audio(show)

    assert not any(show.glob("*.mp3"))
    assert len(list(show.glob("*.md"))) == 3
    assert len(list(show.glob("*.srt"))) == 3
    assert (show / "cover.jpg").exists()


def test_show_delete_tolerates_missing_dir(tmp_path):
    delete_show_audio(tmp_path / "nonexistent")  # must not raise
