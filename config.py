"""
Configuration module for auto-test-android.

This module centralizes configuration settings including debug mode,
which controls debug prints and artifact generation.
"""

import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# =============================================================================
# LOGGING
# =============================================================================
# A single module-level logger shared across the codebase. When DEBUG is
# enabled the level is raised to DEBUG so verbose messages are shown.
def _build_logger() -> logging.Logger:
    logger = logging.getLogger("auto_test_android")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    return logger


# =============================================================================
# DEBUG CONFIGURATION
# =============================================================================
# Set DEBUG=true in .env or environment to enable debug prints and artifacts
# Default is False (disabled) for production/publication
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on")

logger = _build_logger()
logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)


def set_debug(enabled: bool) -> None:
    """Enable or disable debug mode at runtime.

    This is used by the ``--debug`` CLI flag so that debug artifacts (verbose
    logging, annotated screenshots, generated guides) are only produced when
    explicitly requested.
    """
    global DEBUG
    DEBUG = bool(enabled)
    logger.setLevel(logging.DEBUG if DEBUG else logging.INFO)

# =============================================================================
# API CONFIGURATION
# =============================================================================
# API keys are loaded from environment variables (.env file)
# No hardcoded defaults - must be provided via .env or environment

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NVIDIA_NIM_API_KEY = os.getenv("NVIDIA_NIM_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")

# Optional configurations
NVIDIA_NIM_BASE_URL = os.getenv("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
DEVICE_ID = os.getenv("DEVICE_ID", "")
# Backend API URL for job polling. Must be set via .env (no default to avoid
# leaking private infrastructure endpoints).
API_URL = os.getenv("API_URL", "")

# =============================================================================
# ADB / DEVICE CONFIGURATION
# =============================================================================
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))
LOCAL_DOWNLOAD_DIR = os.getenv("LOCAL_DOWNLOAD_DIR", "./downloads")

# =============================================================================
# AGENT CONFIGURATION
# =============================================================================
MAX_AGENT_ATTEMPTS = int(os.getenv("MAX_AGENT_ATTEMPTS", "10"))

# =============================================================================
# DEBUG HELPER FUNCTIONS
# =============================================================================
def debug_print(*args, **kwargs):
    """Log a debug message (only shown when DEBUG is enabled)."""
    if DEBUG:
        logger.debug(" ".join(str(a) for a in args))

def debug_save_screenshot(img_bytes, x, y, status_type, description, end_x=None, end_y=None):
    """Save debug screenshot only when DEBUG is enabled."""
    if not DEBUG or not img_bytes:
        return
    try:
        import os
        import re
        import datetime
        from PIL import Image, ImageDraw
        import io
        
        os.makedirs("./debug_agent_clicks", exist_ok=True)
        img = Image.open(io.BytesIO(img_bytes))
        draw = ImageDraw.Draw(img)
        img_w, img_h = img.size
        
        abs_x = int((x / 1000.0) * img_w)
        abs_y = int((y / 1000.0) * img_h)
        
        color_map = {"success": "green", "action": "yellow", "fallback": "red"}
        color = color_map.get(status_type, "blue")
        
        r = 20
        draw.ellipse([abs_x - r, abs_y - r, abs_x + r, abs_y + r], outline=color, width=5)
        
        if end_x is not None and end_y is not None:
            abs_ex = int((end_x / 1000.0) * img_w)
            abs_ey = int((end_y / 1000.0) * img_h)
            draw.line([abs_x, abs_y, abs_ex, abs_ey], fill=color, width=5)
            
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        desc_safe = re.sub(r'[^\w\-]', '_', description)[:30]
        debug_path = f"./debug_agent_clicks/{timestamp}_{status_type}_{desc_safe}.png"
        img.save(debug_path)
        debug_print(f"Debug screenshot saved ({status_type}): {debug_path}")
    except Exception as e:
        debug_print(f"Error saving debug screenshot: {e}")

def get_debug_dir():
    """Get debug directory path, creating it if needed (only in DEBUG mode)."""
    if DEBUG:
        import os
        os.makedirs("./debug_agent_clicks", exist_ok=True)
        return "./debug_agent_clicks"
    return None