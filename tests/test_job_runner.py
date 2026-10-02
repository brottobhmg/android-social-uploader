"""Tests for job_runner: the polling loop must never spin without sleeping."""

import pytest

import job_runner
import config


def test_empty_queue_sleeps_between_polls(monkeypatch):
    """When the queue is empty, poll_for_jobs must sleep POLL_INTERVAL before
    polling again; a busy loop would trip the API rate limit (60 req/min)."""
    polls = []

    def fake_next_job():
        polls.append(1)
        if len(polls) > 1:
            # A second poll before any sleep means the loop is spinning.
            raise SystemExit
        return None

    sleeps = []
    monkeypatch.setattr(job_runner, "requests_get_next_job", fake_next_job)
    monkeypatch.setattr(job_runner.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(SystemExit):
        job_runner.poll_for_jobs()

    assert sleeps == [config.POLL_INTERVAL]
