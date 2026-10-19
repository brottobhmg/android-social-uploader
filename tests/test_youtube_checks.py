"""Tests for the YouTube Studio uploader checks.

The tag editor and the title field sit close to each other: a mistargeted
click types the tags into the title and the Short is published with a
corrupted title. These tests cover the guards that catch it.
"""

import pytest

from platforms.youtube import YouTubeUploader


def _uploader():
    return YouTubeUploader()


# --------------------------------------------------------------------------
# The tag chips
# --------------------------------------------------------------------------

CHIP_TREE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.ViewGroup" content-desc="foryou, Tocca per selezionare il tag." bounds="[0,0][200,100]" />
  <node index="1" class="android.widget.ViewGroup" content-desc="github, Tocca per selezionare il tag." bounds="[0,100][200,200]" />
  <node index="2" class="android.widget.ViewGroup" content-desc="iodine, Tocca per selezionare il tag." bounds="[0,200][200,300]" />
</hierarchy>
"""


def test_the_tags_present_as_chips_are_not_reported_missing(monkeypatch):
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: CHIP_TREE)
    missing = _uploader()._tags_missing(["foryou", "github", "iodine"])
    assert missing == []


def test_the_tags_absent_from_the_chips_are_reported(monkeypatch):
    """A chip is exposed without the hash: a lookup that expects the hash
    would report every tag as missing."""
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: CHIP_TREE)
    missing = _uploader()._tags_missing(["foryou", "github", "tunnel"])
    assert missing == ["tunnel"]


def test_no_tree_means_nothing_is_missing(monkeypatch):
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: "")
    assert _uploader()._tags_missing(["a", "b"]) == []


# --------------------------------------------------------------------------
# The title
# --------------------------------------------------------------------------

TITLE_TREE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.EditText"
        text="Remove 20+ AI slop patterns from your writing" bounds="[0,0][1080,200]" />
</hierarchy>
"""

CORRUPTED_TITLE_TREE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.EditText"
        text="Remove 20+ AI slop patterns from your writing #chatgpt aa"
        bounds="[0,0][1080,200]" />
</hierarchy>
"""

DIALOG_TREE = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" class="android.widget.TextView" text="Vuoi ignorare le modifiche?" bounds="[0,0][1080,100]" />
  <node index="1" class="android.widget.Button" text="Annulla" bounds="[0,100][500,200]" />
</hierarchy>
"""


def test_an_intact_title_is_accepted(monkeypatch):
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: TITLE_TREE)
    assert _uploader()._title_is_intact(
        "Remove 20+ AI slop patterns from your writing"
    ) is True


def test_a_title_with_the_tags_stuck_to_it_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "platforms.youtube.uia.dump_ui_tree", lambda: CORRUPTED_TITLE_TREE
    )
    assert _uploader()._title_is_intact(
        "Remove 20+ AI slop patterns from your writing"
    ) is False


def test_a_dialog_does_not_block_the_check(monkeypatch):
    """A dialog covers the form: the title cannot be checked, and refusing
    here would block a perfectly good upload."""
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: DIALOG_TREE)
    assert _uploader()._title_is_intact("Remove 20+ AI slop patterns") is True


def test_an_empty_tree_does_not_block_the_check(monkeypatch):
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: "")
    assert _uploader()._title_is_intact("Remove 20+ AI slop patterns") is True


def test_a_title_out_of_the_viewport_does_not_block_the_check(monkeypatch):
    """The form scrolls: the title field is often not in the tree even
    though it holds the right text."""
    tree = """<?xml version='1.0' encoding='UTF-8'?>
    <hierarchy rotation="0">
      <node index="0" class="android.widget.TextView" text="Mostra meno" bounds="[0,0][1080,100]" />
      <node index="1" class="android.widget.Button" text="Carica Short" bounds="[0,2200][1080,2400]" />
    </hierarchy>
    """
    monkeypatch.setattr("platforms.youtube.uia.dump_ui_tree", lambda: tree)
    assert _uploader()._title_is_intact("Remove 20+ AI slop patterns") is True
