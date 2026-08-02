"""
step_recorder.py — Records the actions executed during an upload and
automatically generates a markdown guide at the end of the job.
"""

import datetime
import os
import re

import config


# ---------------------------------------------------------------------------
# Step types
# ---------------------------------------------------------------------------
STEP_CLICK   = "click"
STEP_TYPE    = "type"
STEP_BACK    = "back"
STEP_KEYBOARD= "keyboard"
STEP_APP     = "app_start"
STEP_NOTE    = "note"


class StepRecorder:
    """
    Records the steps executed on each platform and generates a markdown
    guide file at the end of the job.
    """

    def __init__(self):
        self._platforms: list[dict] = []      # [{ name, package, steps[] }]
        self._current: dict | None = None     # current platform

    # ------------------------------------------------------------------
    # Platform management
    # ------------------------------------------------------------------

    def start_platform(self, name: str, package: str = ""):
        """Start recording for a new platform."""
        self._current = {
            "name": name,
            "package": package,
            "steps": [],
        }
        self._platforms.append(self._current)
        self._add({
            "type": STEP_APP,
            "label": "App start",
            "detail": f"`{package}` opened via ADB",
        })

    def _add(self, step: dict):
        """Add a step to the current platform (if any)."""
        if self._current is None:
            return
        step["index"] = len(self._current["steps"]) + 1
        self._current["steps"].append(step)

    # ------------------------------------------------------------------
    # Public hooks — called by the automation logic
    # ------------------------------------------------------------------

    def record_click(
        self,
        description: str,
        x_prop: float,
        y_prop: float,
        success: bool,
        attempts: int,
    ):
        """Record a completed agent_click."""
        note = f"reached on attempt {attempts}" if attempts > 1 else "1st attempt"
        self._add({
            "type": STEP_CLICK,
            "label": f"Tap → {description}",
            "detail": f"Pos. ~{x_prop:.1f}%, {y_prop:.1f}% — {note}",
            "success": success,
            "attempts": attempts,
        })

    def record_type(self, field_description: str, text: str):
        """Record a text input."""
        preview = text[:80].replace("\n", "↵") + ("…" if len(text) > 80 else "")
        self._add({
            "type": STEP_TYPE,
            "label": f"Typing → {field_description}",
            "detail": f"`{preview}`",
        })

    def record_hide_keyboard(self):
        """Record the keyboard being hidden."""
        self._add({
            "type": STEP_KEYBOARD,
            "label": "Hide keyboard",
            "detail": "The virtual keyboard is hidden (keyevent BACK)",
        })

    def record_back(self, reason: str = ""):
        """Record a hardware Back key press."""
        self._add({
            "type": STEP_BACK,
            "label": "Back key",
            "detail": reason or "Simulate the hardware Back key (keyevent 4)",
        })

    def record_note(self, text: str):
        """Record a free-form textual note."""
        self._add({
            "type": STEP_NOTE,
            "label": "📝 Note",
            "detail": text,
        })

    # ------------------------------------------------------------------
    # Guide generation
    # ------------------------------------------------------------------

    def generate_guide(self, output_path: str, job_id=None):
        """
        Generate the markdown guide file and write it to disk.
        Returns the path of the created file.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        lines = self._build_markdown(job_id)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        config.logger.info("📄 Upload guide generated: %s", output_path)
        return output_path

    def _build_markdown(self, job_id=None) -> list[str]:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job_label = f" — Job #{job_id}" if job_id is not None else ""
        lines = [
            f"# Video Upload Guide{job_label}",
            f"",
            f"> Automatically generated on {now}  ",
            f"> Each step reflects the real execution, recorded during the job.",
            f"",
            f"---",
            f"",
        ]

        icon_map = {
            "com.instagram.android":                     "🟣",
            "com.zhiliaoapp.musically":                 "🎵",
            "com.google.android.apps.youtube.creator":  "📺",
        }

        for platform in self._platforms:
            name    = platform["name"]
            package = platform["package"]
            steps   = platform["steps"]
            icon    = icon_map.get(package, "📱")

            lines += [
                f"## {icon} {name}",
                f"",
                f"**Package:** `{package}`",
                f"",
                f"| # | Type | Action | Detail |",
                f"|---|------|--------|--------|",
            ]

            type_icon = {
                STEP_APP:      "🚀",
                STEP_CLICK:    "👆",
                STEP_TYPE:     "⌨️",
                STEP_KEYBOARD: "⌨️",
                STEP_BACK:     "⬅️",
                STEP_NOTE:     "📝",
            }

            for step in steps:
                idx    = step["index"]
                stype  = step["type"]
                label  = step["label"]
                detail = step.get("detail", "")
                ticon  = type_icon.get(stype, "•")

                # Highlight steps that required multiple attempts
                if stype == STEP_CLICK and step.get("attempts", 1) > 1:
                    label = f"**{label}** ⚠️"

                lines.append(f"| {idx} | {ticon} | {label} | {detail} |")

            # Summary section of detected issues
            slow_steps = [
                s for s in steps
                if s.get("type") == STEP_CLICK and s.get("attempts", 1) > 1
            ]
            if slow_steps:
                lines += [
                    f"",
                    f"### ⚠️ Steps with multiple attempts",
                    f"",
                ]
                for s in slow_steps:
                    lines.append(
                        f"- **Step {s['index']}** — *{s['label'].replace('**', '')}*: "
                        f"{s.get('attempts', '?')} attempts"
                    )

            lines += ["", "---", ""]

        # Footer with general notes
        lines += [
            "## General notes",
            "",
            "- **Coordinates** are expressed as percentages relative to the screen (`x%, y%`).",
            "- The **vision LLM agent** analyzes the screenshot and refines the real position.",
            "- A ⚠️ next to a step indicates the agent had to perform corrective actions.",
            "- `wake_and_unlock()` runs before each sequence to ensure the device is active.",
        ]

        return lines


# ---------------------------------------------------------------------------
# Shared global instance — imported by job_processor.py
# ---------------------------------------------------------------------------
step_recorder = StepRecorder()
