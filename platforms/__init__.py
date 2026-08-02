"""
platforms — Platform-specific upload automations.

Each module in this package implements the UI automation flow to upload a
video to a specific social platform (TikTok, Instagram, YouTube Studio).
"""

from platforms.base import BaseUploader
from platforms.tiktok import TikTokUploader
from platforms.instagram import InstagramUploader
from platforms.youtube import YouTubeUploader

__all__ = [
    "BaseUploader",
    "TikTokUploader",
    "InstagramUploader",
    "YouTubeUploader",
]
