"""
job_processor.py — Orchestrates the end-to-end job processing flow.

A "job" represents a video that must be downloaded from the backend API,
pushed to the Android device, and uploaded to one or more social platforms.
This module handles the download, device push, media-scan broadcast, upload
orchestration and temporary-file cleanup.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

import requests

from platforms import TikTokUploader, InstagramUploader, YouTubeUploader
from step_recorder import step_recorder
import ui_automator as uia
import config

#: Directory on the Android device where media files are pushed.
PHONE_DIR = "/storage/emulated/0/Download/BotAutomazione"


def _download_video(job_id: int, local_path: str) -> bool:
    """Download the video for a job from the backend API."""
    config.debug_print(f"Downloading video for job {job_id}...")
    resp = requests.get(
        f"{config.API_URL}/api/download/{job_id}/video", stream=True, timeout=30
    )
    if resp.status_code != 200:
        config.debug_print(f"Unable to download video: {resp.status_code}")
        return False
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return True


def _download_metadata(job_id: int, local_path: str) -> bool:
    """Download the JSON metadata for a job from the backend API."""
    config.debug_print(f"Downloading JSON for job {job_id}...")
    resp = requests.get(f"{config.API_URL}/api/download/{job_id}/json", timeout=10)
    if resp.status_code != 200:
        config.debug_print(f"Unable to download JSON: {resp.status_code}")
        return False
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(resp.json(), f, ensure_ascii=False, indent=4)
    return True


def _push_to_device(local_video: str, local_json: str, job_id: int) -> Dict[str, str]:
    """Push the video and metadata to the Android device, returning device paths."""
    uia.adb(f"shell mkdir -p {PHONE_DIR}")
    phone_video = f"{PHONE_DIR}/video_{job_id}.mp4"
    phone_json = f"{PHONE_DIR}/desc_{job_id}.json"

    config.debug_print(f"Pushing video to Android: {phone_video}")
    uia.adb(f"push {local_video} {phone_video}")
    config.debug_print(f"Pushing JSON to Android: {phone_json}")
    uia.adb(f"push {local_json} {phone_json}")

    # TikTok's internal gallery reads ONLY from MediaStore and typically only
    # shows media in standard folders (camera roll, etc.), unlike Instagram and
    # YouTube which use the system picker (Storage Access Framework) that can
    # browse the real filesystem. So we:
    #   1. copy the video into the camera roll (DCIM/Camera) so TikTok shows it,
    #   2. insert it directly into the MediaStore database via `content insert`
    #      (the most reliable method; `cmd media_scanner scan` and the legacy
    #      MEDIA_SCANNER_SCAN_FILE broadcast are unreliable/ignored on Android 10+).
    camera_dir = "/storage/emulated/0/DCIM/Camera"
    camera_video = f"{camera_dir}/video_{job_id}.mp4"
    uia.adb(f"shell mkdir -p {camera_dir}")
    uia.adb(f"shell cp {phone_video} {camera_video}")

    config.debug_print("Forcing MediaStore database scan...")
    # Direct MediaStore insert (most reliable across versions). The shell user
    # can set _data directly, which forces the entry into the media database.
    # This is what makes the file appear in TikTok's internal gallery.
    uia.adb(
        "shell content insert --uri content://media/external/video/media "
        f"--bind _data:s:{camera_video} "
        f"--bind _display_name:s:video_{job_id}.mp4 "
        "--bind mime_type:s:video/mp4"
    )
    time.sleep(2)
    # Fallback for Android 10 and older, where `content insert` may be restricted.
    uia.adb(
        f"shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{camera_video}"
    )
    time.sleep(2)
    return {"video": phone_video, "json": phone_json}


def _cleanup_local_files(paths: List[str]) -> None:
    """Remove temporary local files created during processing."""
    for path in paths:
        if os.path.exists(path):
            os.remove(path)


def process_job(job_id: int) -> bool:
    """Download the files for a job, push them to Android and run the uploads.

    Args:
        job_id: The backend job identifier.

    Returns:
        ``True`` if the job was processed, ``False`` on any failure.
    """
    try:
        os.makedirs(config.LOCAL_DOWNLOAD_DIR, exist_ok=True)
        video_local = os.path.join(config.LOCAL_DOWNLOAD_DIR, f"video_{job_id}.mp4")
        json_local = os.path.join(config.LOCAL_DOWNLOAD_DIR, f"desc_{job_id}.json")

        # 1-2. Download video and metadata
        if not _download_video(job_id, video_local):
            return False
        if not _download_metadata(job_id, json_local):
            return False

        # 3. Read metadata
        with open(json_local, "r", encoding="utf-8") as f:
            metadata: Dict[str, Any] = json.load(f)

        # 4. Wake the device
        uia.wake_and_unlock()

        # 5. Push files to the device
        phone_paths = _push_to_device(video_local, json_local, job_id)

        # 6. Run the upload automations
        uploaders = [
            InstagramUploader(),
            TikTokUploader(),
            YouTubeUploader(),
        ]
        # ponytail: "completed" here means no exception was raised, not that the
        # post is live (upload() returns True unconditionally and the return
        # value is ignored). Add a published-post check if false positives
        # show up in the dashboard.
        for uploader in uploaders:
            uploader.upload(phone_paths["video"], metadata)
            time.sleep(20)

        # Generate markdown guide only in debug mode (keeps the working tree
        # clean during normal runs).
        if config.DEBUG:
            guide_path = f"./docs/guida_caricamento_job_{job_id}.md"
            step_recorder.generate_guide(guide_path, job_id=job_id)

        # 7. Clean up temporary local files
        _cleanup_local_files([video_local, json_local])

        return True
    except Exception as e:
        config.debug_print(f"Error while processing job {job_id}: {e}")
        return False
