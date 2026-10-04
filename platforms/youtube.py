"""
platforms.youtube — YouTube Studio upload automation.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from platforms.base import BaseUploader
from step_recorder import step_recorder
import ui_automator as uia
import config


class YouTubeUploader(BaseUploader):
    """Automates uploading a Short to YouTube Studio."""

    platform_name = "YouTube Studio"
    app_package = "com.google.android.apps.youtube.creator"
    launch_activity = ".main.MainActivity"

    def upload(self, video_path: str, metadata: Dict[str, Any]) -> bool:
        config.debug_print("🚀 Starting YouTube Studio...")
        self.start_app()

        # 0. Tap bottom nav bar: 130 2333
        uia.agent_click(12, 97.2, "'dashboard' button in the bottom left bar")
        time.sleep(3)

        # 1. Tap "+" at the top: 741 166 (-> 68.6, 6.9)
        uia.agent_click(68.6, 6.9, "plus (+) button at the top to create")
        time.sleep(3)

        # 2. Select the video in the picker. This used to be a blind
        # touch_relative() tap: no screenshot, no vision check, and a wrong
        # hit would publish someone else's video without a single warning.
        uia.agent_click(18.5, 34.4, "the video thumbnail to upload in the media picker: the tile of the video file that was just added to the device, near the top-left of the grid")
        time.sleep(5)

        # Click on title field to focus
        uia.agent_click(55.6, 18, "the TITLE text field at the top of the form, the one whose hint text is 'Describe your Short' or 'Add a title'. This is the FIRST field, ABOVE the description field. Do NOT click the description field.")
        time.sleep(3)

        # Insert title text
        desc = metadata.get("titolo", "")
        config.logger.info("Typing title: %s", desc)
        uia.clear_focused_field()
        uia.type_text(desc)
        step_recorder.record_type("Short title field", desc)
        time.sleep(2)

        # Hide keyboard
        uia.hide_keyboard()
        time.sleep(2)

        # Click "show more": 490 1370 (-> 45.37, 57.08)
        uia.agent_click(45.37, 57.08, "'Show more' item — click to EXPAND the details section, NOT to collapse it. It must show the additional fields below.")
        time.sleep(2)

        # Scroll up to show the following options
        uia.adb("shell input swipe 540 1600 540 600 500")
        time.sleep(1)


        # Click "add description": 422 1240
        uia.agent_click(39.07, 51.66, "the DESCRIPTION text field, the one whose hint text is 'Add a description' or 'Describe your video'. This is BELOW the title field. Do NOT click the title field.")
        time.sleep(1)
        desc = metadata.get("descrizione_post", "Shorts Description")
        config.logger.info("Typing description: %s", desc)
        uia.clear_focused_field()
        uia.type_text(desc)
        step_recorder.record_type("Short description field", desc)
        time.sleep(1)
        uia.hide_keyboard()
        time.sleep(1)
        config.logger.info("Simulating Back button...")
        uia.adb(["shell", "input", "keyevent", "4"])
        step_recorder.record_back("Return to the details screen after the description")
        time.sleep(2)

        # Click menu with tags: 480 1735 (-> 44.4, 72.29)
        uia.agent_click(44.4, 72.29, "'AI usage, Category, Tags and ' item, the last visible element containing that title")
        time.sleep(2)

        # Click on tag field: 468 629 (-> 43.3, 26.2)
        uia.agent_click(43.3, 26.2, "text field to enter tags")
        time.sleep(2)
        uia.clear_focused_field()

        # Insert tags as-is, separated by spaces, without hashtags or commas
        tags = metadata.get("tag", "")
        config.logger.info("Typing tags: %s", tags)
        uia.type_text(tags + ",")
        step_recorder.record_type("Short tags field", tags)
        time.sleep(2)

        # Hide keyboard
        uia.hide_keyboard()
        time.sleep(2)

        # Simulate back key
        config.logger.info("Simulating Back button...")
        uia.adb(["shell", "input", "keyevent", "4"])
        step_recorder.record_back("Confirm and return to the main publication screen")
        time.sleep(2)

        # Click "upload short": 543 2302 (-> 50.3, 95.9)
        uia.agent_click(50.3, 95.9, "Upload Short or Upload video button at the bottom")

        config.debug_print("✅ YouTube operation completed successfully!")
        return True
