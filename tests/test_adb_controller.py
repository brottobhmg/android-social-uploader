import pytest
from unittest.mock import patch
from adb_controller import ADBController

@patch("subprocess.check_output")
def test_get_screen_size(mock_check_output):
    mock_check_output.return_value = b"Physical size: 1080x2400\n"
    adb = ADBController()
    assert adb.get_screen_size() == (1080, 2400)

@patch("subprocess.run")
def test_click(mock_run):
    adb = ADBController()
    adb.screen_size = (1080, 2400)
    adb.click(500, 500)
    mock_run.assert_called_with(["adb", "shell", "input", "tap", "540", "1200"], check=True)

@patch("subprocess.run")
def test_swipe(mock_run):
    adb = ADBController()
    adb.screen_size = (1080, 2400)
    adb.swipe(0, 0, 1000, 1000, 500)
    mock_run.assert_called_with(["adb", "shell", "input", "swipe", "0", "0", "1080", "2400", "500"], check=True)

@patch("subprocess.run")
def test_type_text(mock_run):
    adb = ADBController()
    adb.type_text("hello world")
    mock_run.assert_called_with(["adb", "shell", "input", "text", "hello%sworld"], check=True)

@patch("subprocess.check_output")
def test_take_screenshot(mock_check_output):
    mock_check_output.return_value = b"fake_png_data"
    adb = ADBController()
    assert adb.take_screenshot() == b"fake_png_data"
    mock_check_output.assert_called_with(["adb", "exec-out", "screencap", "-p"])
