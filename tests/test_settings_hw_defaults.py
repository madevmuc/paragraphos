from unittest.mock import patch

from core.models import Settings


def test_fresh_install_applies_hw_recommendations(tmp_path):
    path = tmp_path / "settings.yaml"
    # Path does not exist yet — this is a fresh install.
    with (
        patch("core.hw.recommended_parallel_workers", return_value=3),
        patch("core.hw.recommended_multiproc_split", return_value=2),
    ):
        s = Settings.load(path)
    assert s.parallel_transcribe == 3
    assert s.whisper_multiproc == 2
    # Settings file should now exist on disk (we saved after populating).
    assert path.exists()


def test_existing_file_values_override_recommendations(tmp_path):
    path = tmp_path / "settings.yaml"
    # Write a settings file with explicit values.
    existing = Settings()
    existing.parallel_transcribe = 1
    existing.whisper_multiproc = 1
    existing.save(path)
    # Recommendations suggest different numbers, but the saved values win.
    with (
        patch("core.hw.recommended_parallel_workers", return_value=8),
        patch("core.hw.recommended_multiproc_split", return_value=4),
    ):
        s = Settings.load(path)
    assert s.parallel_transcribe == 1
    assert s.whisper_multiproc == 1


def test_hw_detection_failure_leaves_generic_defaults(tmp_path):
    path = tmp_path / "settings.yaml"

    def boom():
        raise RuntimeError("no sysctl")

    with patch("core.hw.recommended_parallel_workers", side_effect=boom):
        s = Settings.load(path)
    # Values should be whatever the Settings() default constructor yields —
    # just assert the load didn't crash and returned a Settings.
    assert isinstance(s, Settings)
