"""load_level / background_priority settings: defaults, round-trip, and the
one-time migration off the legacy parallel_transcribe knob."""

from __future__ import annotations

from core.models import Settings


def test_fresh_install_defaults_to_balanced(tmp_path):
    s = Settings.load(tmp_path / "settings.yaml")
    assert s.load_level == "balanced"
    assert s.background_priority is True


def test_round_trips(tmp_path):
    p = tmp_path / "settings.yaml"
    Settings(load_level="quiet", background_priority=False).save(p)
    reloaded = Settings.load(p)
    assert reloaded.load_level == "quiet"
    assert reloaded.background_priority is False


def test_legacy_parallel_2_migrates_to_full(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("parallel_transcribe: 3\nwhisper_multiproc: 4\n", encoding="utf-8")
    assert Settings.load(p).load_level == "full"


def test_legacy_single_worker_migrates_to_balanced(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("parallel_transcribe: 1\n", encoding="utf-8")
    assert Settings.load(p).load_level == "balanced"


def test_explicit_load_level_wins_over_legacy(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("load_level: quiet\nparallel_transcribe: 3\n", encoding="utf-8")
    assert Settings.load(p).load_level == "quiet"
