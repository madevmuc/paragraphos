"""resolve_load_profile maps a user-facing background-load level to concrete
whisper-cli launch parameters. Pure + HW-independent (perf_cores passed in)."""

from __future__ import annotations

from core.load import describe_profile, resolve_load_profile


def test_quiet_is_minimal_and_background():
    p = resolve_load_profile("quiet", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos) == (1, 2, "background")
    assert p.command_prefix() == ["taskpolicy", "-b"]


def test_balanced_uses_half_the_cores_and_nice():
    p = resolve_load_profile("balanced", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos) == (1, 4, "nice")
    assert p.command_prefix() == ["nice", "-n", "10"]


def test_full_is_polite_when_background_priority_on():
    p = resolve_load_profile("full", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos, p.nice_level) == (2, 4, "nice", 5)
    assert p.command_prefix() == ["nice", "-n", "5"]


def test_full_is_raw_normal_when_background_priority_off():
    p = resolve_load_profile("full", perf_cores=8, background_priority=False)
    assert p.qos == "normal"
    assert p.command_prefix() == []


def test_scales_down_on_a_small_machine():
    p = resolve_load_profile("full", perf_cores=2, background_priority=True)
    assert p.parallel == 1 and p.threads == 2


def test_detection_failure_never_divides_by_zero():
    p = resolve_load_profile("balanced", perf_cores=0, background_priority=True)
    assert p.parallel >= 1 and p.threads >= 1


def test_unknown_level_raises():
    import pytest

    with pytest.raises(ValueError):
        resolve_load_profile("turbo", perf_cores=8, background_priority=True)  # type: ignore[arg-type]


def test_describe_profile_is_human_readable():
    p = resolve_load_profile("balanced", perf_cores=8, background_priority=True)
    text = describe_profile(p)
    assert "1 Episode" in text and "4 Threads" in text
