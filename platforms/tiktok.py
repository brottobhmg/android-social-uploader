"""
platforms.tiktok — TikTok upload automation.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from platforms.base import BaseUploader
from step_recorder import step_recorder
import ui_automator as uia
import config


class TikTokUploader(BaseUploader):
    """Automates uploading a video to TikTok."""

    platform_name = "TikTok"
    app_package = "com.zhiliaoapp.musically"
    launch_activity = "com.ss.android.ugc.aweme.splash.SplashActivity"

    def upload(self, video_path: str, metadata: Dict[str, Any]) -> bool:
        config.debug_print("🚀 Starting TikTok...")
        self.start_app()

        # Sequence of touches to start the upload (coordinates in 0-100 scale)
        uia.agent_click(92.59, 97.92, "profile button at the bottom right")
        time.sleep(2)
        uia.agent_click(49.81, 97.13, "+ button to create a new post, in the center of the bottom nav bar")
        time.sleep(2)
        uia.agent_click(9.26, 95.83, "button at the bottom left to browse local files")
        time.sleep(1)

        uia.agent_click(5, 20, "the first video in the gallery grid")
        time.sleep(2)
        uia.agent_click(73, 95, "Next button at the bottom right")
        time.sleep(2)

        # Remove song: at the top
        uia.agent_click(47.22, 11.13, "button at the top center to add sound (there may or may not be a song title)")
        time.sleep(2)
        uia.agent_click(51.2, 95.83, "button at the bottom center with the music note icon and the text 'Sound'")
        time.sleep(2)
        uia.hide_keyboard()
        time.sleep(2)

        uia.agent_click(72.5, 95.83, "Next button at the bottom right to go to the publication step")
        time.sleep(2)

        # Description input (relative coordinate 37%, 36%)
        uia.agent_click(37, 17, "post description field where it says 'Add a description...' or similar")
        time.sleep(2)
        desc = self._build_description(metadata, "Reel Description")
        config.logger.info("Typing description: %s", desc)
        uia.clear_focused_field()
        uia.type_text(desc)
        step_recorder.record_type("Post description field", desc)
        time.sleep(2)

        # Hide the keyboard after typing
        uia.hide_keyboard()
        time.sleep(1)

        # Confirm publication
        uia.agent_click(64.8, 96.91, "'Publish' or 'Post' button at the bottom right, usually colored, NOT the 'Next' button")

        config.debug_print("✅ TikTok operation completed successfully!")
        return True
