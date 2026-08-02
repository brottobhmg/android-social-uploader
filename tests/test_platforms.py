"""Tests for the platform uploader base class."""

from platforms.base import BaseUploader


class _ConcreteUploader(BaseUploader):
    platform_name = "Test"
    app_package = "com.test.app"
    launch_activity = ".MainActivity"

    def upload(self, video_path, metadata):
        return True


def test_build_description_with_tags():
    uploader = _ConcreteUploader()
    metadata = {
        "descrizione_post": "Ciao mondo",
        "tag": "tech, python, tech",
    }
    desc = uploader._build_description(metadata, "Default")
    # Description + newlines + unique hashtags (duplicates removed)
    assert "Ciao mondo" in desc
    assert "#tech" in desc
    assert "#python" in desc
    # Duplicate tag should appear only once
    assert desc.count("#tech") == 1


def test_build_description_without_tags():
    uploader = _ConcreteUploader()
    metadata = {"descrizione_post": "Solo testo"}
    desc = uploader._build_description(metadata, "Default")
    assert "Solo testo" in desc
    assert "#" not in desc


def test_build_description_default_when_missing():
    uploader = _ConcreteUploader()
    desc = uploader._build_description({}, "Default Desc")
    assert "Default Desc" in desc
