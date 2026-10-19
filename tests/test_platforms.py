"""Tests for the platform uploader base class."""

import pytest

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


# --------------------------------------------------------------------------
# Tag validation
# --------------------------------------------------------------------------


def test_tags_drop_the_one_character_ones():
    """YouTube Studio refuses the whole batch when a tag is too short.

    A single character tag used to make the upload fail with a truncated
    list of tags.
    """
    uploader = _ConcreteUploader()
    tags = uploader._valid_tags("foryou, c, ai, ai")
    assert "c" not in tags
    assert "foryou" in tags
    assert "ai" in tags


def test_tags_drop_the_duplicates():
    uploader = _ConcreteUploader()
    tags = uploader._valid_tags("dns, tunnel, DNS, Tunnel")
    assert tags == ["dns", "tunnel"]


def test_tags_accept_the_hash_prefix():
    uploader = _ConcreteUploader()
    assert uploader._valid_tags("#dns, #tunnel") == ["dns", "tunnel"]


def test_tags_accept_spaces_as_separators():
    uploader = _ConcreteUploader()
    assert uploader._valid_tags("dns tunnel") == ["dns", "tunnel"]


def test_tags_of_an_empty_field():
    uploader = _ConcreteUploader()
    assert uploader._valid_tags("") == []
    assert uploader._valid_tags(None) == []


def test_the_job_14_tags_are_all_usable():
    """The real metadata of job 14 must survive the validation."""
    uploader = _ConcreteUploader()
    raw = (
        "foryou, github, ai, dns, tunnel, iodine, network, firewall, linux, "
        "makefile, compile, unittest, checklib, subdomain, bind, dynamicdns, "
        "ipv4, opensource, devops, programming, c, cli, tool, utility"
    )
    tags = uploader._valid_tags(raw)
    assert "c" not in tags
    assert len(tags) == len(raw.split(",")) - 1
    # The ones that matter for the post are all there.
    for expected in ("foryou", "github", "ai", "dns", "tunnel", "iodine"):
        assert expected in tags
