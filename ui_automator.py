"""
ui_automator.py — Shared UI automation helpers for Android.

This module centralizes the vision-based "agent click" logic and the text-input
helpers that are shared across all platform uploaders. Low-level ADB operations
are delegated to a single :class:`adb_controller.ADBController` instance, which
is the single source of truth for device interaction.

The module keeps a module-level ``DEVICE_ID`` that is set once at startup via
:func:`set_device_id`. All ADB commands are routed to that device.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET

from adb_controller import ADBController
from llm_provider import GoogleGenAIProvider, OpenAICompatibleProvider
from step_recorder import step_recorder
import config

# Corrective actions the agent has taken, kept across the steps of a single
# platform flow so it does not repeat a trick that just failed (e.g. BACK on a
# screen that needs a swipe). Reset by :func:`reset_agent_history` when the
# platform changes -- see BaseUploader.start_app().
AGENT_HISTORY: list[str] = []

# Single ADB controller instance shared across the codebase. Its device_id is
# updated by :func:`set_device_id` at startup.
controller = ADBController()

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def set_device_id(device_id: str) -> None:
    """Set the ADB device serial used by all subsequent commands."""
    controller.device_id = device_id


def get_device_id() -> str:
    """Return the currently configured ADB device serial."""
    return controller.device_id


# ---------------------------------------------------------------------------
# LLM provider bootstrap
# ---------------------------------------------------------------------------

_LLM_PROVIDER_INSTANCE = None


def init_agent_llm():
    """Create (once) and return the LLM provider used by the vision agent.

    The provider is selected from the first available API key in this order:
    Google Gemini, NVIDIA NIM, Cerebras.

    NVIDIA NIM is the preferred zero-cost option: its free tier lets the whole
    pipeline run without paying for inference. Note the free tier is subject to
    NVIDIA NIM terms of service (rate limits, model availability, evaluation
    intent, data handling, no SLA) — see the README for details.
    """
    global _LLM_PROVIDER_INSTANCE
    if _LLM_PROVIDER_INSTANCE is not None:
        return _LLM_PROVIDER_INSTANCE

    google_key = config.GOOGLE_API_KEY
    nim_key = config.NVIDIA_NIM_API_KEY
    cerebras_key = config.CEREBRAS_API_KEY

    if google_key:
        _LLM_PROVIDER_INSTANCE = GoogleGenAIProvider(
            api_key=google_key, model_name="gemini-3.5-flash-lite"
        )
        config.debug_print("Initialized Google Gemini Vision Provider.")
    elif nim_key:
        _LLM_PROVIDER_INSTANCE = OpenAICompatibleProvider(
            api_key=nim_key,
            base_url=config.NVIDIA_NIM_BASE_URL,
            model_name="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        )
        config.debug_print("Initialized NVIDIA NIM Vision Provider.")
    elif cerebras_key:
        _LLM_PROVIDER_INSTANCE = OpenAICompatibleProvider(
            api_key=cerebras_key,
            base_url="https://api.cerebras.ai/v1",
            model_name="gemma-4-31b",
        )
        config.debug_print("Initialized Cerebras Vision Provider.")
    else:
        raise ValueError(
            "No API key found in the .env file or environment. "
            "Copy .env.example to .env and add your keys."
        )
    return _LLM_PROVIDER_INSTANCE


# ---------------------------------------------------------------------------
# Low-level ADB helpers (delegated to the shared ADBController)
# ---------------------------------------------------------------------------

def adb(command):
    """Send a native ADB command (accepts both strings and lists).

    Delegates to the shared :class:`ADBController` so that the device selector
    is applied consistently.
    """
    if isinstance(command, list):
        proc = subprocess.Popen(controller._adb_cmd(command), stdout=subprocess.PIPE, shell=False)
    else:
        prefix = f"adb -s {controller.device_id} " if controller.device_id else "adb "
        proc = subprocess.Popen(prefix + command, stdout=subprocess.PIPE, shell=True)
    out, _ = proc.communicate()
    return out.decode("utf-8")


def get_screen_size():
    """Return (width, height) of the screen using native adb data."""
    return controller.get_screen_size()


def touch_relative(x_prop, y_prop):
    """Simulate a tap using relative coordinates.

    Supports both fractions (0.0-1.0) and percentages (0-100).
    """
    w, h = get_screen_size()
    x_val = x_prop / 100.0 if x_prop > 1.0 else x_prop
    y_val = y_prop / 100.0 if y_prop > 1.0 else y_prop
    x = int(x_val * w)
    y = int(y_val * h)
    config.debug_print(f"Tap in: {x}, {y} (props: {x_prop}, {y_prop})")
    adb(f"shell input tap {x} {y}")


def dump_ui_tree():
    """Dump the Android accessibility tree and return it as an XML string."""
    return controller.dump_ui_tree()


def wake_and_unlock():
    """Wake the screen and unlock the device."""
    controller.wake_and_unlock()


# ---------------------------------------------------------------------------
# Accessibility tree parsing
# ---------------------------------------------------------------------------

def parse_ui_tree(xml_str: str, screen_width: int, screen_height: int, max_elements: int = 30) -> str:
    """Parse a UIAutomator XML dump and return a compact text summary of clickable elements.

    Each element is formatted as:
      [ID] text/content-desc | class | center:(norm_x, norm_y) | clickable

    Coordinates are normalized to 0-1000 scale.
    Returns an empty string if the XML is empty or fails to parse.
    """
    if not xml_str or len(xml_str.strip()) < 10:
        return ""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return ""

    lines = []
    idx = 0
    for node in root.iter("node"):
        text = node.get("text", "").strip()
        desc = node.get("content-desc", "").strip()
        cls = node.get("class", "").split(".")[-1]  # short class name
        clickable = node.get("clickable", "false")
        bounds_raw = node.get("bounds", "")

        # Skip elements with no useful label and not clickable
        label = text or desc
        if not label and clickable != "true":
            continue

        # Parse bounds [x1,y1][x2,y2]
        coords = list(map(int, re.findall(r"\d+", bounds_raw)))
        if len(coords) != 4:
            continue
        x1, y1, x2, y2 = coords
        cx = int(((x1 + x2) / 2) / screen_width * 1000)
        cy = int(((y1 + y2) / 2) / screen_height * 1000)

        # Skip zero-size or off-screen elements
        if x1 == x2 or y1 == y2:
            continue

        click_marker = "[CLICKABLE]" if clickable == "true" else ""
        label_str = label if label else f"<{cls}>"
        lines.append(f"  [{idx}] {label_str} | {cls} | center:({cx},{cy}) {click_marker}")
        idx += 1
        if idx >= max_elements:
            break

    if not lines:
        return ""
    return "UI Elements detected from accessibility tree:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Text input helpers
# ---------------------------------------------------------------------------

def clean_text(text):
    """Normalize text by removing special characters not supported by ADB."""
    text = text.replace("\u2011", "-")  # Non-breaking hyphen
    text = text.replace("\u2012", "-")  # Figure dash
    text = text.replace("\u2013", "-")  # En dash
    text = text.replace("\u2014", "-")  # Em dash
    text = text.replace("\u2015", "-")  # Horizontal bar
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u00a0", " ")  # Non-breaking space

    # Remove double quotes to avoid conflicts with shell quoting
    text = text.replace('"', "'")

    # Decompose accented characters (e.g. à -> a) and convert to pure ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    # Remove other characters potentially problematic for the Android shell
    for char in ["$", "`", "\\"]:
        text = text.replace(char, "")

    return text


def clear_focused_field():
    """Select all text in the focused field and delete it."""
    adb(["shell", "input", "keycombination", "113", "29"])  # Ctrl+A
    time.sleep(0.5)
    adb(["shell", "input", "keyevent", "67"])  # KEYCODE_DEL
    time.sleep(0.5)


def _type_chunk_only(text, chunk_size, delay):
    """Internal helper to type a single line segment without commas."""
    words = text.split(" ")
    current_chunk = []
    current_length = 0
    is_first_chunk = not text.startswith(" ")

    for word in words:
        if not word:
            continue
        if current_length + len(word) + (1 if current_chunk else 0) > chunk_size:
            if current_chunk:
                chunk_str = " ".join(current_chunk)
                if not is_first_chunk:
                    chunk_str = " " + chunk_str
                escaped_chunk = chunk_str.replace(" ", "%s")
                adb(["shell", "input", "text", f'"{escaped_chunk}"'])
                is_first_chunk = False
                time.sleep(delay)

            if len(word) > chunk_size:
                for k in range(0, len(word), chunk_size):
                    sub_word = word[k : k + chunk_size]
                    if not is_first_chunk and k == 0:
                        sub_word = " " + sub_word
                    escaped_sub = sub_word.replace(" ", "%s")
                    adb(["shell", "input", "text", f'"{escaped_sub}"'])
                    is_first_chunk = False
                    time.sleep(delay)
                current_chunk = []
                current_length = 0
            else:
                current_chunk = [word]
                current_length = len(word)
        else:
            current_chunk.append(word)
            current_length += len(word) + (1 if len(current_chunk) > 1 else 0)

    if current_chunk:
        chunk_str = " ".join(current_chunk)
        if not is_first_chunk:
            chunk_str = " " + chunk_str
        escaped_chunk = chunk_str.replace(" ", "%s")
        adb(["shell", "input", "text", f'"{escaped_chunk}"'])
        time.sleep(delay)


def type_text(text, chunk_size=12, delay=0.15):
    """Type text, handling spaces, special chars, commas and newlines via ADB."""
    cleaned = clean_text(text)

    lines = cleaned.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            if i < len(lines) - 1:
                adb(["shell", "input", "keyevent", "66"])
                time.sleep(0.8)
            continue

        # Split by comma to send them via native keyevent 55
        parts = line.split(",")
        for j, part in enumerate(parts):
            if part:
                _type_chunk_only(part, chunk_size, delay)

            # If not the last segment of the line, there was a comma
            if j < len(parts) - 1:
                adb(["shell", "input", "keyevent", "55"])
                time.sleep(delay)

        # If not the last line, send a KEYCODE_ENTER
        if i < len(lines) - 1:
            adb(["shell", "input", "keyevent", "66"])
            time.sleep(0.8)


def hide_keyboard():
    """Hide the virtual keyboard if it is visible."""
    im_state = adb(
        "shell \"dumpsys input_method | grep -E 'mIsInputViewShown=true|mInputShown=true'\""
    )
    if "mIsInputViewShown=true" in im_state or "mInputShown=true" in im_state:
        config.debug_print("Keyboard visible. Hiding it...")
        adb("shell input keyevent 4")
        time.sleep(1)
        step_recorder.record_hide_keyboard()


# ---------------------------------------------------------------------------
# Vision-based agent click
# ---------------------------------------------------------------------------

def reset_agent_history() -> None:
    """Forget the corrective actions taken so far.

    Called when the platform changes, not between steps: within one platform
    the history is useful (it stops the agent from re-issuing a corrective
    action that already failed), while across platforms it would push the agent
    into actions that make no sense on the new app.
    """
    AGENT_HISTORY.clear()


def agent_click(x_prop, y_prop, description, max_attempts=10):
    """Find an element described near specific coordinates and click it.

    Uses a vision LLM to refine the exact position, supporting up to
    ``max_attempts`` intermediate corrective actions. Returns ``True`` on
    success, ``False`` if it falls back to the original coordinates.
    """
    config.debug_print(
        f"\n🔍 Agent: goal '{description}' theoretically near ({x_prop}, {y_prop})..."
    )

    hint_x_1000 = int(x_prop * 10)
    hint_y_1000 = int(y_prop * 10)

    global AGENT_HISTORY
    img_bytes = None

    for attempt in range(1, max_attempts + 1):
        config.debug_print(f"--- Attempt {attempt}/{max_attempts} ---")
        wake_and_unlock()
        time.sleep(1)

        # 1. Capture screenshot
        try:
            img_bytes = controller.take_screenshot()
        except Exception as e:
            config.debug_print(f"Screenshot capture error: {e}")
            break

        # 2. Dump and parse UI tree
        w, h = get_screen_size()
        xml_raw = dump_ui_tree()
        ui_tree = parse_ui_tree(xml_raw, w, h)

        # 3. Prepare prompt for the LLM
        system_prompt = (
            "You are a Vision-based Android UI Automation Agent.\n"
            "Your final goal is to click on the element described by the user, which is expected to be near the provided hint coordinates (0-1000 scale).\n"
            "If the element is visible on the screen, locate its exact center coordinates and return:\n"
            "  {\"status\": \"click\", \"x\": int, \"y\": int, \"rationale\": string}\n\n"
            "If the element is NOT visible, or is blocked by an overlay, keyboard, or popup, you can perform one corrective step to get closer to the goal.\n"
            "Corrective actions allowed:\n"
            "  - Click elsewhere: {\"status\": \"action\", \"action\": \"click\", \"params\": {\"x\": int, \"y\": int}, \"rationale\": string}\n"
            "  - Swipe/Scroll: {\"status\": \"action\", \"action\": \"swipe\", \"params\": {\"start_x\": int, \"start_y\": int, \"end_x\": int, \"end_y\": int}, \"rationale\": string}\n"
            "  - Press key: {\"status\": \"action\", \"action\": \"press_key\", \"params\": {\"key\": \"BACK\" | \"HOME\" | \"ENTER\"}, \"rationale\": string}\n"
            "  - Wait: {\"status\": \"action\", \"action\": \"wait\", \"params\": {\"seconds\": int}, \"rationale\": string}\n\n"
            "CRITICAL RULES FOR TEXT FIELDS:\n"
            "  - When the goal is a text input field, you MUST click the EXACT field described, matching its hint/label text (e.g. 'Title', 'Describe your Short', 'Add a description', 'Tags').\n"
            "  - Do NOT confuse the title field with the description field, or vice versa. They are different fields with different hint text and different positions.\n"
            "  - If the hint text of the field you are about to click does NOT match the goal description, do NOT click it. Instead use a corrective action (click the correct field, or scroll) to reach the right one.\n"
            "  - Prefer clicking directly on the visible hint text of the target field, not on empty space nearby.\n\n"
            "You will be given the history of actions taken so far in this loop. Avoid repeating failing actions.\n"
            "You must return ONLY a valid JSON object matching the schemas above, and nothing else."
        )

        history_str = (
            "\n".join([f"- {h}" for h in AGENT_HISTORY])
            if AGENT_HISTORY
            else "No action taken yet."
        )
        user_prompt = (
            f"Target Goal Element: '{description}'\n"
            f"Original Position Hint (0-1000 scale): ({hint_x_1000}, {hint_y_1000})\n\n"
            f"History of actions taken in this click loop:\n{history_str}\n\n"
            f"UI Tree elements:\n{ui_tree}\n\n"
            "Analyze the screenshot and UI tree, decide if the goal element is visible to be clicked, or if you need an intermediate corrective step."
        )

        # 4. Ask the LLM
        try:
            provider = init_agent_llm()
            response = provider.analyze_screen(img_bytes, system_prompt, user_prompt)
            config.debug_print(f"LLM response: {response}")

            clean_resp = response.strip()
            if "```json" in clean_resp:
                start = clean_resp.find("```json") + 7
                end = clean_resp.find("```", start)
                clean_resp = clean_resp[start:end].strip()
            start = clean_resp.find("{")
            end = clean_resp.rfind("}")
            if start != -1 and end != -1:
                clean_resp = clean_resp[start : end + 1]

            data = json.loads(clean_resp)
            status = data.get("status")
            rationale = data.get("rationale", "")
            config.debug_print(f"Agent reasoning: {rationale}")

            if status == "click":
                norm_x = float(data["x"])
                norm_y = float(data["y"])

                # Save debug screenshot (green = final success)
                config.debug_save_screenshot(img_bytes, norm_x, norm_y, "success", description)

                # Execute final click
                rel_x = norm_x / 10.0
                rel_y = norm_y / 10.0
                config.debug_print(f"Clicking the final target at the correct coordinates: ({rel_x}, {rel_y})")
                touch_relative(rel_x, rel_y)
                step_recorder.record_click(description, x_prop, y_prop, success=True, attempts=attempt)
                return True

            elif status == "action":
                action_type = data.get("action")
                params = data.get("params", {})

                act_desc = f"Action: {action_type} - {params} ({rationale})"
                AGENT_HISTORY.append(act_desc)
                config.debug_print(f"Executing corrective action: {act_desc}")

                # Save intermediate debug screenshot (yellow = intermediate action)
                if action_type == "click":
                    act_x = float(params.get("x", 500))
                    act_y = float(params.get("y", 500))
                    config.debug_save_screenshot(img_bytes, act_x, act_y, "action", description)
                    touch_relative(act_x / 10.0, act_y / 10.0)
                elif action_type == "swipe":
                    sx = float(params.get("start_x", 500))
                    sy = float(params.get("start_y", 500))
                    ex = float(params.get("end_x", 500))
                    ey = float(params.get("end_y", 500))
                    config.debug_save_screenshot(img_bytes, sx, sy, "action", description, end_x=ex, end_y=ey)
                    w_size, h_size = get_screen_size()
                    abs_sx = int((sx / 1000.0) * w_size)
                    abs_sy = int((sy / 1000.0) * h_size)
                    abs_ex = int((ex / 1000.0) * w_size)
                    abs_ey = int((ey / 1000.0) * h_size)
                    adb(f"shell input swipe {abs_sx} {abs_sy} {abs_ex} {abs_ey} 500")
                elif action_type == "press_key":
                    key_name = params.get("key", "BACK")
                    config.debug_save_screenshot(img_bytes, 500, 500, "action", description)
                    key_map = {"BACK": "4", "HOME": "3", "ENTER": "66"}
                    if key_name in key_map:
                        adb(f"shell input keyevent {key_map[key_name]}")
                elif action_type == "wait":
                    sec = int(params.get("seconds", 2))
                    config.debug_save_screenshot(img_bytes, 500, 500, "action", description)
                    time.sleep(sec)

        except Exception as e:
            config.debug_print(f"Agent loop error: {e}. Moving to next step.")
            AGENT_HISTORY.append(f"Error in step: {e}")

    # If it fails after max_attempts, execute the final fallback
    config.debug_print("⚠️ Agent could not click the final target. Falling back to the original coordinates.")
    config.debug_save_screenshot(img_bytes, hint_x_1000, hint_y_1000, "fallback", description)
    touch_relative(x_prop, y_prop)
    step_recorder.record_click(description, x_prop, y_prop, success=False, attempts=max_attempts)
    return False
