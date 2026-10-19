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

        # The AI usage disclosure and the category are REQUIRED by YouTube
        # Studio: while they are unanswered the publish button stays
        # disabled, so the upload silently never happens.
        self._answer_ai_disclosure()
        self._select_category()

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
        if not uia.agent_click(50.3, 95.9, "Upload Short or Upload video button at the bottom"):
            config.logger.error(
                "YouTube: the publish button could not be clicked. It is usually "
                "disabled because a required field is still missing."
            )
            return False

        # Post-condition: the publish really happened only when the details
        # screen is gone. Without this check a click on a disabled button
        # was reported as a successful upload.
        if not self._publication_left_the_form():
            config.logger.error(
                "YouTube: the details screen is still open after the publish "
                "click: the Short was NOT published."
            )
            return False

        config.debug_print("✅ YouTube operation completed successfully!")
        return True

    # ------------------------------------------------------------------
    # Required fields
    # ------------------------------------------------------------------

    def _answer_ai_disclosure(self) -> bool:
        """Answer the mandatory "AI usage" disclosure.

        YouTube Studio asks whether AI was used to generate or modify the
        content and keeps the publish button disabled until the question is
        answered. The answer is a policy decision, so it is configurable:
        ``AI_DISCLOSURE`` in the environment, ``No`` by default.
        """
        answer = config.AI_DISCLOSURE
        if not uia.agent_click(
            93.9, 15.2, "'Utilizzo dell'AI' row in the attributes screen, the one with the info icon"
        ):
            config.logger.warning("YouTube: could not open the AI usage disclosure")
            return False
        time.sleep(2)

        # The two options are stacked: "Si" on top, "No" below it.
        yes = answer.strip().lower().startswith(("s", "y"))
        ok = uia.agent_click(
            6.0,
            36.0 if yes else 46.5,
            f"the '{'Si' if yes else 'No'}' radio button of the AI usage question",
        )
        time.sleep(1)
        if ok:
            step_recorder.record_type("AI usage disclosure", answer)
        # Go back to the attributes screen.
        uia.adb(["shell", "input", "keyevent", "4"])
        time.sleep(2)
        return ok

    def _select_category(self) -> bool:
        """Pick a category. YouTube Studio requires one for every upload."""
        if not uia.agent_click(
            94.0, 19.0, "the '+' button next to 'Seleziona categoria' in the attributes screen"
        ):
            config.logger.warning("YouTube: could not open the category picker")
            return False
        time.sleep(2)

        ok = uia.agent_click(
            6.0, 50.0, f"the '{config.YOUTUBE_CATEGORY}' radio button in the category list"
        )
        time.sleep(1)
        if ok:
            step_recorder.record_type("YouTube category", config.YOUTUBE_CATEGORY)
        # Close the picker.
        uia.adb(["shell", "input", "keyevent", "4"])
        time.sleep(2)
        return ok

    def _publication_left_the_form(self) -> bool:
        """Return True when the details screen is no longer on display."""
        for _ in range(3):
            time.sleep(3)
            tree = uia.dump_ui_tree()
            if not tree:
                continue
            if "Aggiungi dettagli" not in tree and "Carica Short" not in tree:
                return True
        return False
