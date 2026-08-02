import subprocess
import time
from typing import List, Tuple
import config


class ADBController:
    """Thin wrapper around the Android Debug Bridge (ADB) command line tool.

    All commands are routed to a single device, identified by ``device_id``
    (empty string means "the only connected device").
    """

    def __init__(self, device_id: str = ""):
        self.device_id = device_id
        self.screen_size = None

    def _adb_cmd(self, args: List[str]) -> List[str]:
        """Build an adb command list, prefixing the device selector if set."""
        if self.device_id:
            return ["adb", "-s", self.device_id] + args
        return ["adb"] + args

    def get_screen_size(self) -> Tuple[int, int]:
        if self.screen_size:
            return self.screen_size
        output = subprocess.check_output(self._adb_cmd(["shell", "wm", "size"])).decode("utf-8")
        if "Physical size:" in output:
            parts = output.strip().split(":")[-1].strip().split("x")
            self.screen_size = (int(parts[0]), int(parts[1]))
            return self.screen_size
        raise ValueError("Could not determine screen size")

    def get_app_installed(self) -> list[str]:
        output = subprocess.check_output(self._adb_cmd(["shell", "pm", "list", "packages", "-3"])).decode("utf-8")
        return [app.replace("package:", "").strip() for app in output.strip().split("\n") if "package:" in app]

    def norm_to_abs(self, norm_x: int, norm_y: int) -> Tuple[int, int]:
        width, height = self.get_screen_size()
        abs_x = int((norm_x / 1000.0) * width)
        abs_y = int((norm_y / 1000.0) * height)
        return abs_x, abs_y

    def click(self, norm_x: int, norm_y: int):
        abs_x, abs_y = self.norm_to_abs(norm_x, norm_y)
        subprocess.run(self._adb_cmd(["shell", "input", "tap", str(abs_x), str(abs_y)]), check=True)

    def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 300):
        abs_sx, abs_sy = self.norm_to_abs(start_x, start_y)
        abs_ex, abs_ey = self.norm_to_abs(end_x, end_y)
        subprocess.run(self._adb_cmd(["shell", "input", "swipe", str(abs_sx), str(abs_sy), str(abs_ex), str(abs_ey), str(duration_ms)]), check=True)

    def type_text(self, text: str):
        if not text or not text.strip():
            config.debug_print("Warning: type_text called with empty text. Skipping.")
            return
        # Wait for any active soft keyboard/focus transitions to settle down
        time.sleep(1.2)
        escaped_text = text.replace(' ', '%s').replace("'", "\\'")
        subprocess.run(self._adb_cmd(["shell", "input", "text", escaped_text]), check=True)

    def hide_keyboard(self):
        subprocess.run(self._adb_cmd(["shell", "input", "keyevent", "111"]), check=True)

    def press_key(self, key_name: str):
        key_map = {"BACK": "4", "HOME": "3", "ENTER": "66"}
        if key_name in key_map:
            subprocess.run(self._adb_cmd(["shell", "input", "keyevent", key_map[key_name]]), check=True)
            
    def take_screenshot(self) -> bytes:
        return subprocess.check_output(self._adb_cmd(["exec-out", "screencap", "-p"]))

    def dump_ui_tree(self) -> str:
        """Dump the UIAutomator accessibility tree as XML and return it as a string.
        
        Returns an empty string if the dump fails (e.g., Flutter apps with no accessibility tree).
        """
        try:
            # Clean up old dump if any
            subprocess.run(self._adb_cmd(["shell", "rm", "-f", "/sdcard/window_dump.xml"]), capture_output=True)
            
            # Run uiautomator dump with a 4-second timeout on device side
            subprocess.run(
                self._adb_cmd(["shell", "timeout", "4", "uiautomator", "dump", "/sdcard/window_dump.xml"]),
                capture_output=True, timeout=6
            )
            
            # Check if file was created and is not empty
            check_file = subprocess.run(
                self._adb_cmd(["shell", "ls", "-l", "/sdcard/window_dump.xml"]),
                capture_output=True, text=True
            )
            if "No such file" in check_file.stdout or not check_file.stdout.strip():
                return ""
                
            xml_bytes = subprocess.check_output(
                self._adb_cmd(["exec-out", "cat", "/sdcard/window_dump.xml"]),
                timeout=6
            )
            return xml_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def wake_and_unlock(self):
        """Force-wake the screen and unlock the device."""
        try:
            power_state = subprocess.check_output(self._adb_cmd(["shell", "dumpsys", "power"])).decode("utf-8")
            is_interactive = "mIsInteractive: true" in power_state or "mIsInteractive=true" in power_state
            
            if not is_interactive:
                config.debug_print("Screen off or not interactive. Sending hardware power trigger...")
                subprocess.run(self._adb_cmd(["shell", "input", "keyevent", "26"]), check=True)  # KEYCODE_POWER
                time.sleep(1)
            
            # Unlock the device (send KEYCODE_MENU / 82)
            subprocess.run(self._adb_cmd(["shell", "input", "keyevent", "82"]), check=True)  # KEYCODE_MENU
            time.sleep(0.5)
            config.debug_print("Device woken up and unlocked.")
        except Exception as e:
            config.debug_print(f"Error during wake_and_unlock: {e}")
