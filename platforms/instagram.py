"""
platforms.instagram — Instagram upload automation.
"""

from __future__ import annotations

import time
from typing import Any, Dict

from platforms.base import BaseUploader
from step_recorder import step_recorder
import ui_automator as uia
import config


class InstagramUploader(BaseUploader):
    """Automates uploading a Reel to Instagram."""

    platform_name = "Instagram"
    app_package = "com.instagram.android"
    launch_activity = "com.instagram.android.activity.MainTabActivity"

    def upload(self, video_path: str, metadata: Dict[str, Any]) -> bool:
        config.debug_print("🚀 Starting Instagram...")
        self.start_app()
        time.sleep(10)

        # 1. Tap profile button bottom-right (967, 2266 -> 89.5, 94.4)
        uia.agent_click(89.5, 94.4, "profile button at the bottom right to go to the profile")
        time.sleep(3)

        # 2. Tap "+" to create at the top (52, 209 -> 4.8, 8.7)
        uia.agent_click(4.8, 8.7, "plus (+) button at the top to create")
        time.sleep(3)

        # 3. Select Reel category (444, 1062 -> 41.1, 44.3)
        uia.agent_click(41.1, 44.3, "Reel item or Reel category to select Reel")
        time.sleep(3)

        # 4. Select file in the grid (545, 909 -> 50.5, 37.9)
        uia.agent_click(50.5, 37.9, "first file or video in the gallery media grid (the first file should be in the first row, second column)")
        time.sleep(3)

        # 5. Tap "Next" (928, 2287 -> 85.9, 95.3)
        uia.agent_click(85.9, 95.3, "Next button at the bottom to proceed to editing")
        time.sleep(4)

        # 6. Tap description field to insert text (473, 1162 -> 43.8, 48.4)
        uia.agent_click(43.8, 48.4, "post description field or 'write a caption'")
        time.sleep(2)

        desc = self._build_description(metadata, "Reel Description")
        config.logger.info("Typing description: %s", desc)
        uia.clear_focused_field()
        uia.type_text(desc)
        step_recorder.record_type("Reel caption field", desc)
        time.sleep(2)

        # 7. Hide the keyboard
        uia.hide_keyboard()
        time.sleep(2)

        # 8. Tap "Share" (786, 2231 -> 72.8, 93.0)
        uia.agent_click(72.8, 93.0, "Share button at the bottom to publish")

        config.debug_print("✅ Instagram operation completed successfully!")
        return True
