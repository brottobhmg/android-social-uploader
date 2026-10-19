"""
job_runner.py — Entry point for the job-processing (polling) mode.

This module is intentionally thin: it wires together the ADB device selection,
the job polling loop and the job processor. All the heavy lifting lives in:

- ``ui_automator`` — low-level ADB + vision-based agent click helpers
- ``job_processor`` — download / push / upload orchestration
- ``platforms`` — per-platform upload automations

Run a single job::

    python job_runner.py --job-id 84

Run in continuous polling mode::

    python job_runner.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

from job_processor import process_job
import ui_automator as uia
import config


def scan_device(select=None):
    """List attached ADB devices, or select the ``select``-th one (1-based)."""
    out = subprocess.check_output(["adb", "devices"]).decode("utf-8")
    devices = [
        line.split("\t")[0].strip() for line in out.splitlines()[1:] if line.strip()
    ]
    if select is not None:
        uia.set_device_id(devices[select - 1])
        config.debug_print(f"selected Device ID: {uia.get_device_id()}")
    return devices


def run_job(job_id: int) -> bool:
    """Process a job and report its outcome to the backend.

    The job is reported exactly once, in both modes. A job that is processed
    but never reported stays in the queue and is handed out again by the next
    poll, which would publish the same video twice.
    """
    success = process_job(job_id)
    if success:
        requests_post_job_status(job_id, "completed")
        config.debug_print(f"🎉 Job {job_id} completed successfully!")
    else:
        requests_post_job_status(job_id, "failed")
        config.debug_print(f"❌ Job {job_id} marked as FAILED")
    return success


def poll_for_jobs() -> None:
    """Continuously poll the backend API for pending jobs and process them."""
    config.debug_print(
        f"Polling endpoint {config.API_URL}/api/next-job every {config.POLL_INTERVAL} seconds..."
    )
    while True:
        try:
            response = requests_get_next_job()
            if response is None:
                # Empty queue or error: back off before polling again, or we
                # hammer /api/next-job in a tight loop and trip the 60 req/min
                # per-IP rate limit (which punishes the dashboard too).
                time.sleep(config.POLL_INTERVAL)
                continue
            job_id, source_link = response
            config.debug_print(f"🔔 Found pending job {job_id} for {source_link}")

            run_job(job_id)
        except config.ApiAuthError as e:
            # The token was refused: a configuration error, not a transient
            # one. Retrying immediately would flood the logs with requests
            # that cannot succeed, so wait long and try again later.
            config.logger.error(str(e))
            time.sleep(config.AUTH_ERROR_BACKOFF)
            continue
        except Exception as e:
            config.debug_print(f"Network error or exception during polling: {e}")

        time.sleep(config.POLL_INTERVAL)


def requests_get_next_job():
    """Fetch the next pending job from the backend API.

    Returns:
        A ``(job_id, source_link)`` tuple, or ``None`` when the queue is
        empty or the call failed.

    Raises:
        config.ApiAuthError: the server rejected the API token. That is a
            configuration error, so the caller must not retry it.
    """
    import requests

    if not config.API_URL:
        config.logger.error(
            "API_URL is not configured: add it to your .env file before polling"
        )
        return None

    # (connect, read) timeout: 3s to establish TCP+TLS, 15s to get a response.
    response = requests.get(
        f"{config.API_URL}/api/next-job",
        headers=config.api_headers(),
        timeout=(3.05, 15),
    )
    if response.status_code in (401, 503):
        raise config.ApiAuthError(config.auth_error_message(response.status_code))
    if response.status_code == 429:
        config.logger.warning(
            f"Rate limit reached on /api/next-job: backing off for "
            f"{config.RATE_LIMIT_BACKOFF}s"
        )
        time.sleep(config.RATE_LIMIT_BACKOFF)
        return None
    if response.status_code != 200:
        body = response.text.strip()[:200]
        config.logger.warning(
            f"Server answered HTTP {response.status_code} on /api/next-job"
            + (f": {body}" if body else "")
        )
        return None
    data = response.json()
    if data.get("status") == "no_jobs":
        return None  # No job in queue, keep polling
    return data["id"], data["source_link"]


def requests_post_job_status(job_id: int, status: str, attempts: int = 3) -> None:
    """Notify the backend API about a job's completion status, with retries.

    A job left in ``processing`` after a failed report is invisible to the
    queue forever, so retry a few times before giving up. HTTP 404 means the
    job was deleted from the dashboard: stop working on it.
    """
    import requests

    url = f"{config.API_URL}/api/job-{status}/{job_id}"
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                url, headers=config.api_headers(), timeout=(3.05, 15)
            )
            if response.status_code in (200, 404):
                return
            if response.status_code in (401, 503):
                # Configuration error: retrying would only fill the logs.
                config.logger.error(config.auth_error_message(response.status_code))
                return
            if response.status_code == 429:
                config.logger.warning(
                    f"Rate limit reached while reporting job {job_id}: backing "
                    f"off for {config.RATE_LIMIT_BACKOFF}s"
                )
                time.sleep(config.RATE_LIMIT_BACKOFF)
                continue
            config.logger.warning(
                f"Report for job {job_id} answered HTTP {response.status_code}"
            )
        except Exception as e:
            config.logger.warning(f"Report for job {job_id} failed: {e}")
        time.sleep(5)
    config.logger.error(
        f"Could not report job {job_id} as {status}: it may stay in 'processing'"
    )


def main() -> None:
    """Select the device and start the polling loop."""
    uia.adb("start-server")
    config.debug_print("Available devices:")
    devices = scan_device() or []
    for i, device in enumerate(devices):
        config.debug_print(f"{i + 1}: {device}")

    if len(devices) == 1:
        device_id = 1
    else:
        device_id = int(input("Choice your devices: "))

    scan_device(device_id)
    poll_for_jobs()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto Test Android job processor")
    parser.add_argument(
        "--job-id", type=int, required=False, default=None, help="Job ID to process"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode: verbose logging, annotated screenshots and generated guides",
    )
    args = parser.parse_args()

    if args.debug:
        config.set_debug(True)

    # NOTE: check `is not None` — a job id of 0 is a valid value and is falsy
    # in Python, so `if args.job_id:` would wrongly fall into polling mode.
    if args.job_id is not None:
        try:
            run_job(args.job_id)
        except config.ApiAuthError as e:
            # A refused token is a configuration error: report it and stop
            # instead of crashing with a traceback.
            config.logger.error(str(e))
            sys.exit(2)
    else:
        main()
