from datetime import datetime

from ui.widgets.queue_hero import human_finish_framing


def test_framing_soon():
    now = datetime(2026, 4, 21, 10, 0)
    assert human_finish_framing(now, datetime(2026, 4, 21, 10, 20)) == "soon"


def test_framing_before_lunch():
    now = datetime(2026, 4, 21, 8, 0)
    assert human_finish_framing(now, datetime(2026, 4, 21, 11, 30)) == "before lunch"


def test_framing_afternoon():
    now = datetime(2026, 4, 21, 12, 0)
    assert human_finish_framing(now, datetime(2026, 4, 21, 16, 0)) == "this afternoon"


def test_framing_tomorrow_morning():
    now = datetime(2026, 4, 21, 22, 0)
    assert human_finish_framing(now, datetime(2026, 4, 22, 9, 0)) == "tomorrow morning"
