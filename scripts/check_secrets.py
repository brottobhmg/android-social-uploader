#!/usr/bin/env python
"""Scan the repository for accidentally committed secrets.

The tool has three modes:

    python scripts/check_secrets.py              # staged files (used by the pre-commit hook)
    python scripts/check_secrets.py --all        # every file tracked by git
    python scripts/check_secrets.py --history    # every blob in every commit of every ref

It exits with status 1 when something suspicious is found, 0 otherwise.
Only the standard library is used, so it runs anywhere Python 3.10+ does.

Detected values are never printed in full: only a short prefix and the
length are reported, so that a finding cannot leak the secret into a
terminal scrollback or a CI log.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Detection rules
# --------------------------------------------------------------------------

#: High-confidence vendor formats. A match is a finding on its own.
VENDOR_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("NVIDIA NIM", re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("Google API key (new format)", re.compile(r"\bAQ\.Ab8[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{40,}")),
    ("OpenRouter API key", re.compile(r"\bsk-or-v1-[A-Za-z0-9]{32,}")),
    ("Cerebras API key", re.compile(r"\bMTUyMT[A-Za-z0-9+/=._\-]{20,}")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{24,}")),
]

#: Low-confidence rule: only reports when the value also looks random.
GENERIC_RULE = re.compile(
    r"""(?ix)
    \b(
        api[_-]?key | apikey | secret[_-]?key | secret | access[_-]?key |
        auth[_-]?token | access[_-]?token | client[_-]?secret |
        private[_-]?key | password | passwd | pwd | token
    )\b
    \s*[:=]\s*["']([^"'\s]{12,})["']
    """
)

#: Substrings that mark a value as a documentation placeholder.
PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "example",
    "placeholder",
    "changeme",
    "change_me",
    "dummy",
    "fake",
    "sample",
    "redacted",
    "notreal",
    "not_real",
    "test_key",
    "testkey",
    "test-token",
    "insert",
    "replace",
    "todo",
    "xxxxx",
    "abcdef",
    "123456",
    "***",
    "...",
    "<",
    ">",
)

#: Files that are never scanned (the scanner itself would match its own rules).
SELF_EXCLUDE = {"scripts/check_secrets.py"}

#: A file whose first lines contain this marker is skipped. It is the escape
#: hatch for test fixtures, which have to embed credentials in their real
#: format to test the detection rules.
ALLOW_MARKER = "secret-scan: allow"

#: How many leading lines are inspected for the allow marker.
ALLOW_MARKER_LINES = 20

#: Minimum Shannon entropy (bits per character) for the generic rule.
MIN_ENTROPY = 3.0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def shannon_entropy(value: str) -> float:
    """Return the Shannon entropy of *value* in bits per character."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum(
        (n / length) * math.log2(n / length) for n in counts.values()
    )


def is_placeholder(value: str) -> bool:
    """Return True when *value* looks like a documentation placeholder."""
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def is_allowed(text: str) -> bool:
    """Return True when *text* opts out of the scan via the allow marker."""
    header = "\n".join(text.splitlines()[:ALLOW_MARKER_LINES])
    return ALLOW_MARKER in header


def redact(value: str) -> str:
    """Return a safe, non-reversible description of *value*."""
    prefix = value[:4]
    return f"{prefix}... ({len(value)} chars)"


def scan_text(text: str, label: str) -> list[str]:
    """Return a list of findings for *text*, one per line, each prefixed by *label*."""
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for name, pattern in VENDOR_RULES:
            for match in pattern.finditer(line):
                findings.append(
                    f"{label}:{line_no}: [{name}] {redact(match.group(0))}"
                )
        for match in GENERIC_RULE.finditer(line):
            value = match.group(2)
            if is_placeholder(value):
                continue
            if shannon_entropy(value) < MIN_ENTROPY:
                continue
            findings.append(
                f"{label}:{line_no}: [generic secret assignment] {redact(value)}"
            )
    return findings


def read_text(path: Path) -> str | None:
    """Read *path* as text, or return None when it is binary or unreadable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# Git plumbing
# --------------------------------------------------------------------------


def git(*args: str) -> str:
    """Run a git command in the current repository and return stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def staged_files() -> list[str]:
    """Return the paths staged for commit."""
    output = git("diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [line for line in output.splitlines() if line.strip()]


def tracked_files() -> list[str]:
    """Return every path tracked by git."""
    output = git("ls-files")
    return [line for line in output.splitlines() if line.strip()]


def history_blobs() -> list[tuple[str, str]]:
    """Return (blob sha, path) for every blob reachable from any ref."""
    seen: dict[str, str] = {}
    for commit in git("rev-list", "--all").splitlines():
        if not commit.strip():
            continue
        for line in git(
            "ls-tree", "-r", "--format=%(objectname) %(path)", commit
        ).splitlines():
            if not line.strip():
                continue
            sha, _, path = line.partition(" ")
            if sha and path and sha not in seen:
                seen[sha] = path
    return sorted(seen.items(), key=lambda item: item[1])


# --------------------------------------------------------------------------
# Modes
# --------------------------------------------------------------------------


def allowed_paths(root: Path) -> set[str]:
    """Return the tracked paths that opt out of the scan.

    The exemption is a property of the *file*, not of a single blob: a file
    that carries the allow marker today is exempt for all its historical
    versions too. Otherwise an old revision of a test fixture would keep
    failing the history scan forever.
    """
    allowed: set[str] = set()
    for rel in tracked_files():
        if rel in SELF_EXCLUDE:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if text is not None and is_allowed(text):
            allowed.add(rel)
    return allowed


def scan_working_tree(
    paths: list[str], root: Path, allowed: set[str] | None = None
) -> list[str]:
    """Scan the given repository-relative paths in the working tree."""
    allowed = allowed or set()
    findings: list[str] = []
    for rel in paths:
        if rel in SELF_EXCLUDE or rel in allowed:
            continue
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        if text is None:
            continue
        if is_allowed(text):
            continue
        findings.extend(scan_text(text, rel))
    return findings


def scan_history(root: Path, allowed: set[str] | None = None) -> list[str]:
    """Scan every blob stored in the git history."""
    allowed = allowed or set()
    findings: list[str] = []
    for sha, path in history_blobs():
        if path in SELF_EXCLUDE or path in allowed:
            continue
        content = git("cat-file", "-p", sha)
        if not content:
            continue
        findings.extend(scan_text(content, f"{path}@{sha[:8]}"))
    return findings


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--all", action="store_true", help="scan every file tracked by git"
    )
    mode.add_argument(
        "--history", action="store_true", help="scan every blob in every commit"
    )
    parser.add_argument(
        "--root",
        default=".",
        help="repository root (default: the current directory)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print("not a git repository: nothing to scan", file=sys.stderr)
        return 0

    allowed = allowed_paths(root)

    if args.history:
        targets: list[str] = []
        findings = scan_history(root, allowed)
        scope = "git history"
    elif args.all:
        targets = tracked_files()
        findings = scan_working_tree(targets, root, allowed)
        scope = "tracked files"
    else:
        targets = staged_files()
        findings = scan_working_tree(targets, root, allowed)
        scope = "staged files"

    if findings:
        print(f"SECRET SCAN FAILED ({scope}): {len(findings)} finding(s)")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nIf a finding is a false positive, add an explicit placeholder "
            "marker to the value or refine scripts/check_secrets.py."
        )
        return 1

    count = len(targets) if not args.history else len(history_blobs())
    print(f"secret scan OK ({scope}): {count} file(s) checked, no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
