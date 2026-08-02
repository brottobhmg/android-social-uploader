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
import time

from job_processor import process_job
import ui_automator as uia
import config


def scan_device(select=None):
    """List attached ADB devices, or select one when ``select`` is provided."""
    proc = subprocess.Popen("adb devices", stdout=subprocess.PIPE, shell=False)
    out, _ = proc.communicate()
    devices = out.decode("utf-8").split("\n")[1:]
    all_attached_devices: list[str] = []
    for device in devices:
        device = device.split("\t")[0].strip()
        if select is not None:
            uia.set_device_id(device)
            config.debug_print(f"selected Device ID: {uia.get_device_id()}")
            return
        if device != "":
            all_attached_devices.append(device)
    return all_attached_devices


def poll_for_jobs() -> None:
    """Continuously poll the backend API for pending jobs and process them."""
    config.debug_print(
        f"Polling endpoint {config.API_URL}/api/next-job every {config.POLL_INTERVAL} seconds..."
    )
    while True:
        try:
            response = requests_get_next_job()
            if response is None:
                continue
            job_id, source_link = response
            config.debug_print(f"🔔 Found pending job {job_id} for {source_link}")

            success = process_job(job_id)
            if success:
                requests_post_job_status(job_id, "completed")
                config.debug_print(f"🎉 Job {job_id} completed successfully!")
            else:
                requests_post_job_status(job_id, "failed")
                config.debug_print(f"❌ Job {job_id} marked as FAILED")
        except Exception as e:
            config.debug_print(f"Network error or exception during polling: {e}")

        time.sleep(config.POLL_INTERVAL)


def requests_get_next_job():
    """Fetch the next pending job from the backend API."""
    import requests

    response = requests.get(f"{config.API_URL}/api/next-job", timeout=10)
    if response.status_code != 200:
        config.debug_print(f"The server API responded with code {response.status_code}")
        return None
    data = response.json()
    if data.get("status") == "no_jobs":
        return None  # No job in queue, keep polling
    return data["id"], data["source_link"]


def requests_post_job_status(job_id: int, status: str) -> None:
    """Notify the backend API about a job's completion status."""
    import requests

    requests.post(f"{config.API_URL}/api/job-{status}/{job_id}", timeout=10)


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

    if args.job_id:
        process_job(args.job_id)
    else:
        main()
