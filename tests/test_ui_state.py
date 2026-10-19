"""Tests for the UI state checks that make the upload results trustworthy.

A tap on a disabled control is silently ignored by Android. The automation
used to report it as a success, so a job could be marked as published while
nothing had been published at all.
"""

import pytest

import ui_automator as uia


#: A minimal dump with a disabled button at the bottom of the screen.
DISABLED_BUTTON_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
    <node index="0" text="Carica Short" resource-id="" class="android.widget.Button"
          package="com.google.android.apps.youtube.creator" content-desc=""
          checkable="false" checked="false" clickable="true" enabled="false"
          focusable="true" focused="false" scrollable="false" long-clickable="false"
          password="false" selected="false" bounds="[36,2250][1044,2380]" />
  </node>
</hierarchy>
"""

ENABLED_BUTTON_XML = DISABLED_BUTTON_XML.replace('enabled="false"', 'enabled="true"')


# --------------------------------------------------------------------------
# element_state_at / is_enabled_at
# --------------------------------------------------------------------------


def test_a_disabled_button_is_detected():
    state = uia.element_state_at(DISABLED_BUTTON_XML, 50, 96, 1080, 2400)
    assert state is not None
    assert state["enabled"] is False
    assert state["text"] == "Carica Short"


def test_an_enabled_button_is_detected():
    state = uia.element_state_at(ENABLED_BUTTON_XML, 50, 96, 1080, 2400)
    assert state["enabled"] is True


def test_an_empty_position_gives_no_state():
    """A point covered by no element gives no state: nothing can be said."""
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <hierarchy rotation="0">
      <node class="android.widget.Button" text="OK" bounds="[36,2250][1044,2380]" enabled="true" />
    </hierarchy>
    """
    assert uia.element_state_at(xml, 5, 5, 1080, 2400) is None
    assert uia.is_enabled_at(xml, 5, 5, 1080, 2400) is None


def test_an_empty_tree_gives_no_state():
    assert uia.is_enabled_at("", 50, 96, 1080, 2400) is None


def test_the_smallest_element_wins():
    """A button nested in a container is the one the user taps."""
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <hierarchy rotation="0">
      <node class="android.widget.FrameLayout" bounds="[0,0][1080,2400]" enabled="true">
        <node class="android.widget.LinearLayout" bounds="[0,2000][1080,2400]" enabled="true">
          <node class="android.widget.Button" text="OK" bounds="[36,2250][1044,2380]" enabled="false" />
        </node>
      </node>
    </hierarchy>
    """
    state = uia.element_state_at(xml, 50, 96, 1080, 2400)
    assert state["class"] == "Button"
    assert state["enabled"] is False


# --------------------------------------------------------------------------
# agent_click refuses to click a disabled target
# --------------------------------------------------------------------------


def test_agent_click_refuses_a_disabled_target(monkeypatch):
    """The tap is not emitted and the call reports a failure."""
    taps = []
    monkeypatch.setattr(uia, "touch_relative", lambda x, y: taps.append((x, y)))
    monkeypatch.setattr(uia, "dump_ui_tree", lambda: DISABLED_BUTTON_XML)
    monkeypatch.setattr(uia, "get_screen_size", lambda: (1080, 2400))
    monkeypatch.setattr(uia, "wake_and_unlock", lambda: None)
    monkeypatch.setattr(uia.controller, "take_screenshot", lambda: b"fake-png")

    class FakeProvider:
        def analyze_screen(self, image_bytes, system_prompt, user_prompt):
            return '{"status": "click", "x": 500, "y": 965, "rationale": "found it"}'

    monkeypatch.setattr(uia, "init_agent_llm", lambda: FakeProvider())

    result = uia.agent_click(50, 96, "the publish button")

    assert result is False
    assert taps == [], "a disabled target must not be tapped"


def test_agent_click_clicks_an_enabled_target(monkeypatch):
    taps = []
    monkeypatch.setattr(uia, "touch_relative", lambda x, y: taps.append((x, y)))
    monkeypatch.setattr(uia, "dump_ui_tree", lambda: ENABLED_BUTTON_XML)
    monkeypatch.setattr(uia, "get_screen_size", lambda: (1080, 2400))
    monkeypatch.setattr(uia, "wake_and_unlock", lambda: None)
    monkeypatch.setattr(uia.controller, "take_screenshot", lambda: b"fake-png")

    class FakeProvider:
        def analyze_screen(self, image_bytes, system_prompt, user_prompt):
            return '{"status": "click", "x": 500, "y": 965, "rationale": "found it"}'

    monkeypatch.setattr(uia, "init_agent_llm", lambda: FakeProvider())

    result = uia.agent_click(50, 96, "the publish button")

    assert result is True
    assert len(taps) == 1
