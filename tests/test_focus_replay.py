"""Daily Focus Replay UI tests."""

from datetime import date

from app.statistics import DailyReplaySummary, FocusItemTotal
from app.ui.replay_dialog import FocusReplayDialog


def test_replay_dialog_renders_factual_daily_summary(qt_application) -> None:
    dialog = FocusReplayDialog()
    hourly = [0.0] * 24
    hourly[19] = 5400
    summary = DailyReplaySummary(
        day=date(2026, 8, 15),
        total_seconds=5400,
        session_count=2,
        longest_session_seconds=3600,
        top_focus_item=FocusItemTotal(7, "Project", 4200),
        hourly_seconds=tuple(hourly),
    )

    dialog.set_summary(summary)

    assert "1h 30min" == dialog._total.text()
    assert dialog._sessions.text() == "2"
    assert dialog._top_item.text() == "Project"
    assert "2 completed" in dialog._completion.text()
    assert dialog._distribution._values[19] == 5400
    dialog.close()
