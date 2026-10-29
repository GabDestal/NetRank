"""Groq usage log, and the freshness gate that live evaluation runs must pass (decision log D77).

Groq's free-tier daily caps (200k tokens, 1,000 requests) are a rolling 24 h window: live-4 started
two hours after live-3 and was stopped by the token cap after q02. Every live Groq session (eval runs,
smoke tests, single-question runs) is logged in eval/quota_log.json with its start and end; a live run
refuses to start while the last use is less than 24 h old. Usage before this log existed was
backfilled from the run files and console logs ("source": "backfilled").

There is no override flag. If the log is wrong, correct eval/quota_log.json in a commit.

Usage: python -m scripts.quota_log   (prints the last use and when the window is fresh; no Groq call)
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG = Path("eval/quota_log.json")
WINDOW = timedelta(hours=24)
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# Printed by `make quota` and repeated in the README: the log only sees `make eval` sessions.
SCOPE = "Covers make eval sessions only: agent calls through the API (POST /api/agent/ask) are not logged."


class StaleQuotaWindowError(RuntimeError):
    """The daily window still holds Groq usage from an earlier session."""


def stamp(moment: datetime) -> str:
    """UTC timestamp as stored in the log."""
    return moment.astimezone(timezone.utc).strftime(STAMP)


def parse(text: str) -> datetime:
    """Stored timestamp back to an aware datetime."""
    return datetime.strptime(text, STAMP).replace(tzinfo=timezone.utc)


def load(path: Path = LOG) -> list[dict]:
    """All logged sessions, oldest first (empty if there is no log yet)."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save(entries: list[dict], path: Path = LOG) -> None:
    """Write the log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8", newline="\n")


def last_use(entries: list[dict]) -> datetime | None:
    """End of the latest session; a session without an end (killed run) makes the log unusable."""
    open_sessions = [e["label"] for e in entries if not e.get("end")]
    if open_sessions:
        raise StaleQuotaWindowError(
            f"no end time for {', '.join(open_sessions)} in {LOG} (run killed?): "
            + "fill in when its last Groq call happened, then retry"
        )
    return max((parse(e["end"]) for e in entries), default=None)


def fresh_at(entries: list[dict]) -> datetime | None:
    """When the rolling daily window no longer holds any logged usage (None: nothing logged)."""
    last = last_use(entries)
    return last + WINDOW if last else None


def wait(delta: timedelta) -> str:
    """Remaining time, to the second."""
    return str(timedelta(seconds=int(delta.total_seconds())))


def check_fresh(now: datetime, path: Path = LOG) -> None:
    """Raise StaleQuotaWindowError unless the last logged use is at least 24 h before `now`."""
    entries = load(path)
    fresh = fresh_at(entries)
    if fresh and now < fresh:
        last = entries[-1]
        raise StaleQuotaWindowError(
            f"Groq's daily window is not fresh: last use {stamp(fresh - WINDOW)} ({last['label']}); "
            + f"a live run can start after {stamp(fresh)}, in {wait(fresh - now)}"
        )


def start(label: str, model: str, now: datetime, path: Path = LOG) -> None:
    """Log the start of a live session (its end stays empty until finish)."""
    entries = load(path)
    entries.append({"label": label, "model": model, "start": stamp(now), "end": None, "source": "eval"})
    save(entries, path)


def finish(label: str, now: datetime, rows: list[dict], path: Path = LOG) -> None:
    """Close the session: end time, Groq's token counts and whether the daily cap stopped it."""
    entries = load(path)
    entry = next(e for e in reversed(entries) if e["label"] == label and not e.get("end"))
    entry.update(
        {
            "end": stamp(now),
            "questions": len(rows),
            "promptTokens": sum(r.get("promptTokens") or 0 for r in rows),
            "completionTokens": sum(r.get("completionTokens") or 0 for r in rows),
            "dailyQuotaHit": any(r.get("dailyQuota") for r in rows),
        }
    )
    save(entries, path)


def main() -> None:
    """Print the state of the window, without calling Groq."""
    now = datetime.now(timezone.utc)
    sys.stdout.write(f"{SCOPE}\n")
    try:
        fresh = fresh_at(load())
    except StaleQuotaWindowError as exc:
        sys.stdout.write(f"{exc}\n")
        sys.exit(1)
    if fresh is None or now >= fresh:
        sys.stdout.write(f"fresh: no Groq use logged in the 24 h before {stamp(now)}\n")
        return
    sys.stdout.write(
        f"not fresh: last use {stamp(fresh - WINDOW)}; fresh after {stamp(fresh)}, in {wait(fresh - now)}\n"
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
