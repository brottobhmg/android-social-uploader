"""
platforms.base — Base class for platform uploaders.

A platform uploader encapsulates the UI automation flow needed to publish a
video on a specific social platform. Subclasses implement :meth:`upload`,
which receives the path of the video already pushed to the device and the
metadata (description, tags, title) for the post.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from step_recorder import step_recorder
import ui_automator as uia


class BaseUploader(ABC):
    """Base class for a platform-specific video upload automation."""

    #: Human-readable platform name (used in generated guides).
    platform_name: str = "Generic"

    #: Android application package name.
    app_package: str = ""

    #: Activity to launch when starting the app.
    launch_activity: str = ""

    def __init__(self) -> None:
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_app(self) -> None:
        """Launch the platform app on the device and record the step."""
        step_recorder.start_platform(self.platform_name, self.app_package)
        uia.adb(
            f"shell am start -n {self.app_package}/{self.launch_activity}"
        )
        self._started = True

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------

    @abstractmethod
    def upload(self, video_path: str, metadata: Dict[str, Any]) -> bool:
        """Run the full upload automation for this platform.

        Args:
            video_path: Absolute path of the video on the Android device.
            metadata: Post metadata (``descrizione_post``, ``tag``, ``titolo``).

        Returns:
            ``True`` if the upload flow completed, ``False`` otherwise.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_description(metadata: Dict[str, Any], default: str = "Description") -> str:
        """Build the post description from metadata, appending unique hashtags."""
        desc = metadata.get("descrizione_post", default)
        desc = desc + "\n   \n"
        tags = metadata.get("tag", "")
        if tags:
            tag_list = list(
                dict.fromkeys(t.strip() for t in tags.split(",") if t.strip())
            )
            for tag in tag_list:
                desc = desc + f"#{tag} "
        return desc
