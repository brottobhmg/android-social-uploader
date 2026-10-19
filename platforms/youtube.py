"""
platforms.youtube — YouTube Studio upload automation.
"""

from __future__ import annotations

import re
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
        title = metadata.get("titolo", "")
        config.logger.info("Typing title: %s", title)
        uia.clear_focused_field()
        uia.type_text(title)
        step_recorder.record_type("Short title field", title)
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

        # The AI usage disclosure is REQUIRED by YouTube Studio: while it is
        # unanswered the publish button stays disabled, so the upload
        # silently never happens. The category is not set: YouTube Studio
        # assigns one on its own.
        self._answer_ai_disclosure()

        # The tags live behind the "Aggiungi tag" entry of the attributes
        # screen, in the middle of the chip list. Clicking the inline chip
        # area instead types the tags into the title field, which then gets
        # published with the tags stuck to it.
        tags = self._valid_tags(metadata.get("tag", ""))
        config.logger.info("Typing %d tags: %s", len(tags), ", ".join(tags))
        if not uia.agent_click(
            50.0, 57.9, "the 'Aggiungi tag' entry that opens the tag editor"
        ):
            config.logger.error("YouTube: could not open the tag editor")
            return False
        time.sleep(2)
        uia.clear_focused_field()
        uia.type_text(", ".join(tags))
        step_recorder.record_type("Short tags field", ", ".join(tags))
        time.sleep(2)

        # Hide keyboard
        uia.hide_keyboard()
        time.sleep(2)

        # The tags are committed with a comma: without it the last tag stays
        # in the field as plain text instead of becoming a chip.
        uia.adb(["shell", "input", "text", ","])
        time.sleep(1)
        uia.hide_keyboard()
        time.sleep(2)

        # Verify that the tags really became chips.
        missing = self._tags_missing(tags)
        if missing:
            config.logger.error(
                "YouTube: %d tag(s) were not accepted: %s",
                len(missing),
                ", ".join(missing),
            )

        # Back to the main publication screen. The hardware BACK opens the
        # "discard the changes?" dialog when the form holds unsaved edits,
        # so the on-screen arrow is used instead.
        config.logger.info("Going back to the main publication screen...")
        uia.agent_click(
            6.6, 7.6, "the 'Indietro' (back) arrow in the top left of the attributes screen"
        )
        step_recorder.record_back("Return to the main publication screen")
        time.sleep(2)

        # The title must be exactly what the metadata says: a mistargeted
        # click can leave the tags stuck to it.
        if not self._title_is_intact(title):
            config.logger.error(
                "YouTube: the title field does not hold the expected text "
                "('%s'): refusing to publish a corrupted title.", title
            )
            return False

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
        # Back to the attributes screen: the hardware BACK would leave the
        # attributes screen altogether and land on the main form.
        uia.agent_click(
            6.6, 7.6, "the 'Back' arrow in the top left of the AI usage screen"
        )
        time.sleep(2)
        return ok

    def _tags_missing(self, tags: list) -> list:
        """Return the tags that did not become a chip on the screen.

        The chips are exposed as ``content-desc="<tag>, Tocca per selezionare
        il tag."``, without a leading hash.
        """
        tree = uia.dump_ui_tree()
        if not tree:
            return []
        present = set()
        for match in re.finditer(r'content-desc="([^"]*?)Tocca per selezionare', tree):
            # The chip is exposed as "<tag>, Tocca per selezionare il tag.":
            # the comma belongs to the label, not to the tag.
            present.add(match.group(1).split(",")[0].strip().lstrip("#").lower())
        return [tag for tag in tags if tag.lower() not in present]

    def _title_is_intact(self, expected: str) -> bool:
        """Return True when the title field still holds the expected text.

        The tag editor sits close to the title field: a mistargeted click
        types the tags into the title, and the Short is then published with
        the tags stuck to its title.

        A field that is not on screen says nothing about its content, so the
        check only fails when a title field is visible and holds something
        else.
        """
        tree = uia.dump_ui_tree()
        if not tree:
            return True
        # A visible text holding exactly the expected title: the title is
        # fine. The comparison is exact because a corrupted title still
        # contains the expected one as a prefix.
        for match in re.finditer(r'text="([^"]*)"', tree):
            if match.group(1) == expected:
                return True
        # A dialog covers the form: the title cannot be checked, and
        # refusing here would block a perfectly good upload.
        if "Vuoi ignorare le modifiche" in tree:
            return True
        # A visible title field holding something else is a corrupted title.
        for match in re.finditer(r'text="([^"]*)"', tree):
            value = match.group(1)
            if expected[:20] in value:
                return False
        return True

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
