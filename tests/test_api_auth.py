"""Tests for the backend authentication.

The job API requires a bearer token on every route. These tests cover the
three things that matter: the header is really sent (including on the
streaming download), a refused token produces a handled error instead of a
crash, and a refused token is not retried.
"""

import json

import pytest
import requests

import config
import job_processor
import job_runner


class FakeResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, status_code=200, payload=None, text="", chunks=()):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self._chunks = chunks

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=8192):
        yield from self._chunks


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """A configured client: a token, an API URL and no stray environment."""
    monkeypatch.setattr(config, "API_URL", "http://backend.test")
    monkeypatch.setattr(config, "API_TOKEN", "test-token")


# --------------------------------------------------------------------------
# The header is sent on every request
# --------------------------------------------------------------------------


def test_next_job_request_carries_the_bearer_token(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"id": 7, "source_link": "https://example.test"})

    monkeypatch.setattr(requests, "get", fake_get)
    job_runner.requests_get_next_job()

    assert len(calls) == 1
    _url, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_download_video_request_carries_the_bearer_token(monkeypatch, tmp_path):
    """The video is fetched with a streaming request: the header goes with it."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, chunks=[b"video-bytes"])

    monkeypatch.setattr(requests, "get", fake_get)
    target = tmp_path / "video.mp4"

    assert job_processor._download_video(7, str(target)) is True
    assert target.read_bytes() == b"video-bytes"

    _url, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"
    assert kwargs["stream"] is True


def test_download_json_request_carries_the_bearer_token(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200, {"titolo": "t", "descrizione_post": "d"})

    monkeypatch.setattr(requests, "get", fake_get)
    target = tmp_path / "desc.json"

    assert job_processor._download_metadata(7, str(target)) is True

    _url, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_job_status_request_carries_the_bearer_token(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(200)

    monkeypatch.setattr(requests, "post", fake_post)
    job_runner.requests_post_job_status(7, "completed")

    assert len(calls) == 1
    _url, kwargs = calls[0]
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_no_authorization_header_without_a_token(monkeypatch):
    """A missing token is not a crash: the request goes out without the header
    and the server decides, so the client stays compatible with a backend
    that has no authentication at all."""
    monkeypatch.setattr(config, "API_TOKEN", "")
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(401, text="unauthorized")

    monkeypatch.setattr(requests, "get", fake_get)

    with pytest.raises(config.ApiAuthError):
        job_runner.requests_get_next_job()

    _url, kwargs = calls[0]
    assert "Authorization" not in kwargs["headers"]


# --------------------------------------------------------------------------
# A refused token is a configuration error, not a transient one
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status_code", [401, 503])
def test_refused_token_raises_a_handled_error(monkeypatch, status_code):
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: FakeResponse(status_code, text="nope")
    )

    with pytest.raises(config.ApiAuthError) as excinfo:
        job_runner.requests_get_next_job()

    message = str(excinfo.value)
    assert "API token rifiutato dal server" in message
    assert "API_TOKEN" in message


@pytest.mark.parametrize("status_code", [401, 503])
def test_refused_token_on_download_raises_a_handled_error(monkeypatch, status_code):
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: FakeResponse(status_code, text="nope")
    )

    with pytest.raises(config.ApiAuthError):
        job_processor._download_video(7, "video.mp4")

    with pytest.raises(config.ApiAuthError):
        job_processor._download_metadata(7, "desc.json")


def test_refused_token_does_not_retry_the_status_report(monkeypatch):
    """Retrying a report with a wrong token cannot work: it would only fill
    the logs."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return FakeResponse(401, text="nope")

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(job_runner.time, "sleep", lambda s: None)

    job_runner.requests_post_job_status(7, "completed")

    assert len(calls) == 1


def test_polling_loop_backs_off_long_on_a_refused_token(monkeypatch):
    """A watch/poll client must not hammer the server with a token that
    cannot work: it waits at least five minutes instead."""
    sleeps = []
    calls = []

    def fake_next_job():
        calls.append(1)
        if len(calls) > 1:
            # The second poll ends the test: SystemExit is not caught by the
            # loop, so it breaks out of it.
            raise SystemExit
        raise config.ApiAuthError("API token rifiutato dal server: controlla API_TOKEN")

    monkeypatch.setattr(job_runner, "requests_get_next_job", fake_next_job)
    monkeypatch.setattr(job_runner.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(SystemExit):
        job_runner.poll_for_jobs()

    assert sleeps == [config.AUTH_ERROR_BACKOFF]
    assert config.AUTH_ERROR_BACKOFF >= 300


def test_process_job_propagates_the_auth_error(monkeypatch):
    """The error must not be swallowed into a generic 'job failed', or the
    job would be reported as failed and retried forever."""
    monkeypatch.setattr(
        job_processor, "_download_video", lambda job_id, path: (_ for _ in ()).throw(
            config.ApiAuthError("API token rifiutato dal server: controlla API_TOKEN")
        )
    )

    with pytest.raises(config.ApiAuthError):
        job_processor.process_job(7)


# --------------------------------------------------------------------------
# The rate limit
# --------------------------------------------------------------------------


def test_rate_limit_backs_off_sixty_seconds(monkeypatch):
    sleeps = []

    def fake_get(url, **kwargs):
        return FakeResponse(429, text="too many requests")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(job_runner.time, "sleep", lambda s: sleeps.append(s))

    assert job_runner.requests_get_next_job() is None
    assert sleeps == [60]
    assert config.RATE_LIMIT_BACKOFF == 60


def test_rate_limit_on_the_status_report_backs_off(monkeypatch):
    sleeps = []
    monkeypatch.setattr(requests, "post", lambda url, **kwargs: FakeResponse(429))
    monkeypatch.setattr(job_runner.time, "sleep", lambda s: sleeps.append(s))

    job_runner.requests_post_job_status(7, "completed")

    assert 60 in sleeps


# --------------------------------------------------------------------------
# The successful path is unchanged
# --------------------------------------------------------------------------


def test_a_healthy_server_still_returns_the_job(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kwargs: FakeResponse(
            200, {"id": 42, "source_link": "https://example.test/repo"}
        ),
    )

    assert job_runner.requests_get_next_job() == (42, "https://example.test/repo")


def test_an_empty_queue_is_not_an_error(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: FakeResponse(200, {"status": "no_jobs"})
    )

    assert job_runner.requests_get_next_job() is None


def test_the_metadata_shape_is_untouched(monkeypatch, tmp_path):
    """The contract says a hand-made job may miss keys: they are treated as
    empty strings instead of crashing."""
    monkeypatch.setattr(
        requests, "get", lambda url, **kwargs: FakeResponse(200, {"titolo": "t"})
    )
    target = tmp_path / "desc.json"

    job_processor._download_metadata(7, str(target))

    assert json.loads(target.read_text(encoding="utf-8")) == {"titolo": "t"}


# --------------------------------------------------------------------------
# The job is reported exactly once
# --------------------------------------------------------------------------


def test_a_successful_job_is_reported_completed(monkeypatch):
    reports = []
    monkeypatch.setattr(job_runner, "process_job", lambda job_id: True)
    monkeypatch.setattr(
        job_runner, "requests_post_job_status", lambda job_id, status: reports.append((job_id, status))
    )

    job_runner.run_job(14)

    assert reports == [(14, "completed")]


def test_a_failed_job_is_reported_failed(monkeypatch):
    reports = []
    monkeypatch.setattr(job_runner, "process_job", lambda job_id: False)
    monkeypatch.setattr(
        job_runner, "requests_post_job_status", lambda job_id, status: reports.append((job_id, status))
    )

    job_runner.run_job(14)

    assert reports == [(14, "failed")]


def test_the_job_is_reported_exactly_once(monkeypatch):
    """A job that is processed but never reported stays in the queue and is
    handed out again by the next poll, publishing the same video twice."""
    reports = []
    monkeypatch.setattr(job_runner, "process_job", lambda job_id: True)
    monkeypatch.setattr(
        job_runner, "requests_post_job_status", lambda job_id, status: reports.append((job_id, status))
    )

    job_runner.run_job(14)

    assert len(reports) == 1
