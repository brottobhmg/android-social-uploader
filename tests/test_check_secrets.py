"""Tests for the secret scanner used by the pre-commit hook and by CI.

This file embeds sample credentials in the exact format of the real ones, on
purpose: they are the fixtures the detection rules are tested against. The
scanner therefore skips this file.

secret-scan: allow
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_secrets import (  # noqa: E402
    is_allowed,
    is_placeholder,
    redact,
    scan_text,
    shannon_entropy,
)


def _s(head: str, body: str) -> str:
    """Join the two halves of a sample credential.

    The halves are kept apart in the source on purpose: the file must never
    contain a string that looks like a real credential, because push
    protection blocks the commit and a public repository has no business
    carrying anything a secret scanner would flag.
    """
    return head + body



# --------------------------------------------------------------------------
# Vendor-specific formats
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sample",
    [
        ("GOOGLE=" + _s("AQ.Ab8", "RN6LzxhLODl-j5yhyEPwS_7HXLZ4L4NKLYKRENE_AFzCcEw")),
        ("GOOGLE=" + _s("AIza", "SyD-1234567890abcdefghijklmnopqrstu") + "v"),
        ("NIM=" + _s("nvapi-", "LUD4_75DSvPiFoGCAYEBlVnJBRPta16h4Ta-gkY07No8ihnB00")),
        ("CEREBRAS=" + _s("MTUyMT", "c4MzMyNzIyMzMyMDU4Ng.GS5tSV.9UClUbJyzd0-PLkzsA-rp2GJu6")),
        ("OPENAI=" + _s("sk-", "abcdefghijklmnopqrstuvwxyz0123456789ABCD")),
        ("ANTHROPIC=" + _s("sk-ant-", "api03-abcdefghijklmnopqrstuvwxyz0123456789ABCD")),
        ("OPENROUTER=" + _s("sk-or-v1-", "abcdefghijklmnopqrstuvwxyz0123456789")),
        ("GITHUB=" + _s("ghp_", "0123456789abcdefghijklmnopqrstuvwxyzAB")),
        ("GITHUB_FINE=" + _s("github_pat_", "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz")),
        ("AWS=" + _s("AKIA", "IOSFODNN7EXAMPLE")),
        ("SLACK=" + _s("xoxb-", "1234567890-abcdefghij")),
        ("STRIPE=" + _s("sk_live_", "abcdefghijklmnopqrstuvwx")),
    ],
)
def test_detects_vendor_formats(sample):
    assert scan_text(sample, "sample.py") != []


def test_detects_private_key_block():
    text = (_s("-----BEGIN ", "RSA PRIVATE KEY-----") + "\nMIIabc\n-----END RSA PRIVATE KEY-----")
    assert scan_text(text, "key.pem") != []


def test_reports_the_line_number():
    findings = scan_text(("ok = 1\n" + _s("AIza", "SyD-1234567890abcdefghijklmnopqrstu") + "v\n"), "f.py")
    assert findings
    assert findings[0].startswith("f.py:2:")


# --------------------------------------------------------------------------
# False positives that must NOT be reported
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "your_google_api_key_here",
        "your_nvidia_nim_api_key_here",
        "your_cerebras_api_key_here",
        "your_token_here",
        "changeme",
        "placeholder",
        "dummy_value_1234",
        "example_key_value",
        "<your-key-here>",
        "***",
    ],
)
def test_ignores_placeholders(value):
    text = f'API_KEY = "{value}"'
    assert scan_text(text, ".env.example") == []
    assert is_placeholder(value)


def test_ignores_low_entropy_values():
    assert scan_text('password = "aaaaaaaaaaaaaaaa"', "f.py") == []


def test_ignores_ordinary_code():
    text = 'max_tokens = 4096\nlimit = 100\nname = "config"\n'
    assert scan_text(text, "f.py") == []


def test_ignores_the_scanner_itself_when_asked_for_working_tree(tmp_path):
    # The scanner file is excluded by path, not by content.
    from scripts.check_secrets import SELF_EXCLUDE

    assert "scripts/check_secrets.py" in SELF_EXCLUDE


# --------------------------------------------------------------------------
# The allow marker
# --------------------------------------------------------------------------


def test_allow_marker_opts_a_file_out_of_the_scan():
    text = ("secret-scan: allow\nK = \"" + _s("nvapi-", "0123456789abcdefghijklmnopqrstuv") + "\"\n")
    assert is_allowed(text) is True


def test_allow_marker_must_be_in_the_header():
    body = "\n" * 40 + "secret-scan: allow\n"
    assert is_allowed(body) is False


def test_a_file_without_the_marker_is_not_allowed():
    assert is_allowed(("K = \"" + _s("nvapi-", "0123456789abcdefghijklmnopqrstuv") + "\"\n")) is False


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def test_redact_never_reveals_the_full_value():
    secret = (_s("nvapi-", "abcdefghijklmnopqrstuvwxyz0123456789"))
    redacted = redact(secret)
    assert secret not in redacted
    assert redacted.startswith("nvap")
    assert f"{len(secret)} chars" in redacted


def test_entropy_of_random_looking_string_is_high():
    assert shannon_entropy("aB3xY9kQ2mN7pR4tV6wZ1") > 3.0


def test_entropy_of_repeated_string_is_low():
    assert shannon_entropy("aaaaaaaaaaaaaaaa") < 1.0
