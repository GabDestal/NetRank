"""Groq usage log and the freshness gate for live evaluation runs (no Groq call)."""

from datetime import datetime, timedelta, timezone

import pytest

from scripts import quota_log

LAST = datetime(2026, 10, 23, 9, 9, 55, tzinfo=timezone.utc)


@pytest.fixture(name="log_path")
def fixture_log_path(tmp_path):
    """A log whose last session ended at LAST."""
    path = tmp_path / "quota_log.json"
    quota_log.save(
        [
            {"label": "live-3", "start": "2026-10-23T07:17:00Z", "end": "2026-10-23T08:33:20Z"},
            {"label": "live-4", "start": "2026-10-23T09:08:45Z", "end": "2026-10-23T09:09:55Z"},
        ],
        path,
    )
    return path


def test_refuses_inside_the_window(log_path):
    """One second short of 24 h after the last use, a live run may not start."""
    with pytest.raises(quota_log.StaleQuotaWindowError, match="2026-10-24T09:09:55Z"):
        quota_log.check_fresh(LAST + timedelta(hours=24) - timedelta(seconds=1), log_path)


def test_allows_once_the_window_has_passed(log_path):
    """24 h after the last use the window is fresh."""
    quota_log.check_fresh(LAST + timedelta(hours=24), log_path)


def test_empty_log_is_fresh(tmp_path):
    """No logged use: nothing to wait for."""
    quota_log.check_fresh(LAST, tmp_path / "missing.json")


def test_unfinished_session_blocks(log_path):
    """A session with no end (killed run) blocks until the log is corrected."""
    quota_log.start("live-5", "openai/gpt-oss-120b", LAST + timedelta(days=2), log_path)
    with pytest.raises(quota_log.StaleQuotaWindowError, match="no end time for live-5"):
        quota_log.check_fresh(LAST + timedelta(days=5), log_path)


def test_finish_records_end_and_tokens(log_path):
    """finish closes the open session with Groq's token counts and the daily-cap flag."""
    begin = LAST + timedelta(days=1)
    quota_log.start("live-5", "openai/gpt-oss-120b", begin, log_path)
    rows = [{"promptTokens": 3000, "completionTokens": 200}, {"promptTokens": None, "dailyQuota": True}]
    quota_log.finish("live-5", begin + timedelta(minutes=40), rows, log_path)
    entry = quota_log.load(log_path)[-1]
    assert entry["end"] == "2026-10-24T09:49:55Z"
    assert (entry["promptTokens"], entry["completionTokens"], entry["dailyQuotaHit"]) == (3000, 200, True)
    with pytest.raises(quota_log.StaleQuotaWindowError):
        quota_log.check_fresh(begin + timedelta(hours=24), log_path)
