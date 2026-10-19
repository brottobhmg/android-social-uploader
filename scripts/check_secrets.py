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
import bisect
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

#: Content larger than this is treated as data, not as source: only the
#: high-confidence vendor patterns are applied to it. One megabyte is far
#: above any configuration or source file and far below the size of the data
#: dumps a history can hold.
MAX_FULL_SCAN = 1 << 20

#: Chunk size used to scan oversized content, with a small overlap so that a
#: pattern spanning a chunk boundary is still caught.
CHUNK_SIZE = 1 << 20
CHUNK_OVERLAP = 256

#: How many commits are handed to a single `git grep` invocation. The limit
#: keeps the command line short on repositories with a long history.
GREP_BATCH = 400


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


def _line_index(text: str) -> list[int]:
    """Return the offset at which every line of *text* starts."""
    return [0] + [match.end() for match in re.finditer("\n", text)]


def scan_vendor(text: str, label: str, line_offset: int = 0) -> list[str]:
    """Return the findings of the high-confidence vendor patterns."""
    line_starts = _line_index(text)
    found: list[tuple[int, str]] = []
    for name, pattern in VENDOR_RULES:
        for match in pattern.finditer(text):
            line = bisect.bisect_right(line_starts, match.start()) + line_offset
            found.append(
                (line, f"{label}:{line}: [{name}] {redact(match.group(0))}")
            )
    found.sort(key=lambda item: item[0])
    return [text for _, text in found]


def scan_generic(text: str, label: str, line_offset: int = 0) -> list[str]:
    """Return the findings of the low-confidence, entropy-checked rule."""
    line_starts = _line_index(text)
    found: list[tuple[int, str]] = []
    for match in GENERIC_RULE.finditer(text):
        value = match.group(2)
        if is_placeholder(value):
            continue
        if shannon_entropy(value) < MIN_ENTROPY:
            continue
        line = bisect.bisect_right(line_starts, match.start()) + line_offset
        found.append(
            (line, f"{label}:{line}: [generic secret assignment] {redact(value)}")
        )
    found.sort(key=lambda item: item[0])
    return [text for _, text in found]


def scan_text(text: str, label: str) -> list[str]:
    """Return a list of findings for *text*, each prefixed by *label*.

    The patterns are applied to the whole text instead of line by line: on a
    large file the per-line loop dominates the runtime. Line numbers are
    recovered afterwards from the match offsets.
    """
    return scan_vendor(text, label) + scan_generic(text, label)


def scan_bytes(raw: bytes, label: str) -> list[str]:
    """Scan raw content, choosing the strategy according to its size.

    Small content gets the full treatment. Oversized content is treated as
    data: only the high-confidence vendor patterns are applied, chunk by
    chunk, so that a dump of results is not scanned line by line.
    """
    if b"\x00" in raw:
        return []
    if len(raw) <= MAX_FULL_SCAN:
        return scan_text(raw.decode("utf-8", "replace"), label)

    findings: list[str] = []
    line_offset = 0
    start = 0
    while start < len(raw):
        chunk = raw[start : start + CHUNK_SIZE + CHUNK_OVERLAP]
        text = chunk.decode("utf-8", "replace")
        findings.extend(scan_vendor(text, label, line_offset))
        line_offset += text.count("\n")
        start += CHUNK_SIZE
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


def git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command and return stdout (empty when the command fails)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def staged_files(root: Path) -> list[str]:
    """Return the paths staged for commit."""
    output = git("diff", "--cached", "--name-only", "--diff-filter=ACM", cwd=root)
    return [line for line in output.splitlines() if line.strip()]


def tracked_files(root: Path) -> list[str]:
    """Return every path tracked by git."""
    output = git("ls-files", cwd=root)
    return [line for line in output.splitlines() if line.strip()]


def history_objects(root: Path) -> list[tuple[str, str]]:
    """Return (sha, path) for every object reachable from any ref.

    A single `git rev-list --objects --all` is used instead of walking every
    commit: the latter costs one subprocess per commit, which is unusable on
    a repository with a long history.
    """
    objects: list[tuple[str, str]] = []
    for line in git("rev-list", "--objects", "--all", cwd=root).splitlines():
        sha, _, path = line.partition(" ")
        if sha:
            objects.append((sha, path))
    return objects


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
    for rel in tracked_files(root):
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
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        text = raw.decode("utf-8", "replace")
        if is_allowed(text):
            continue
        findings.extend(scan_bytes(raw, rel))
    return findings


def vendor_matches_in_line(content: str, label: str, line_no: int) -> list[str]:
    """Return the vendor findings of a single line, with an explicit line number."""
    found: list[str] = []
    for name, pattern in VENDOR_RULES:
        for match in pattern.finditer(content):
            found.append(
                f"{label}:{line_no}: [{name}] {redact(match.group(0))}"
            )
    return found


def to_ere(pattern: str) -> str:
    """Translate a Python regular expression into a POSIX ERE compatible one.

    `git grep -E` uses the POSIX extended syntax, which knows neither the
    non-capturing group `(?:...)` nor the `\\s` shorthand. The patterns are
    written in Python syntax and translated here for the fallback path.
    """
    return (
        pattern.replace("(?:", "(")
        .replace(r"\s", "[[:space:]]")
        .replace(r"\d", "[0-9]")
        .replace(r"\w", "[[:alnum:]_]")
    )


def _run_git_grep(
    pattern: str, commits: list[str], pcre: bool, root: Path
) -> subprocess.CompletedProcess:
    """Run `git grep` over *commits* with the given pattern."""
    args = ["git", "grep", "-I", "-n"]
    args.append("-P" if pcre else "-E")
    args += ["-e", pattern, *commits]
    return subprocess.run(
        args,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def grep_history_vendor(
    root: Path, allowed: set[str] | None = None
) -> list[str]:
    """Find vendor-format secrets anywhere in the history with `git grep`.

    `git grep` is implemented in C and walks every commit in a fraction of a
    second, even on a history that holds gigabytes of content. It is used for
    the high-confidence patterns, where the format alone is enough to report.

    PCRE is used when the local git supports it, with a POSIX ERE fallback
    otherwise. A failure of the search is reported instead of being ignored:
    a silent error would look exactly like a clean repository.

    Returns the findings and the number of commits that were searched.
    """
    allowed = allowed or set()
    commits = git("rev-list", "--all", cwd=root).split()
    if not commits:
        return [], 0

    pattern = "|".join(rule.pattern for _, rule in VENDOR_RULES)
    findings: list[str] = []
    for start in range(0, len(commits), GREP_BATCH):
        batch = commits[start : start + GREP_BATCH]
        result = _run_git_grep(pattern, batch, pcre=True, root=root)
        if result.returncode not in (0, 1):
            # PCRE is not available in this git build: fall back to POSIX ERE.
            result = _run_git_grep(to_ere(pattern), batch, pcre=False, root=root)
        if result.returncode not in (0, 1):
            raise RuntimeError(
                "git grep failed while scanning the history: "
                f"{result.stderr.strip() or result.returncode}"
            )
        for line in result.stdout.splitlines():
            parts = line.split(":", 3)
            if len(parts) != 4:
                continue
            _sha, path, line_no, content = parts
            if path in SELF_EXCLUDE or path in allowed:
                continue
            findings.extend(
                vendor_matches_in_line(content, f"{path}@{_sha[:8]}", line_no)
            )
    return findings, len(commits)


def scan_history(
    root: Path, allowed: set[str] | None = None
) -> tuple[list[str], int]:
    """Scan every blob stored in the git history.

    The high-confidence patterns are searched with `git grep` (fast, and it
    covers the content of every size), while the entropy-based rule is
    applied in Python to the small blobs only: reading a history that holds
    gigabytes of data dumps through Python would take minutes.

    Returns the findings and the number of commits that were searched.
    """
    allowed = allowed or set()
    findings, commits = grep_history_vendor(root, allowed)

    objects = [
        (sha, path)
        for sha, path in history_objects(root)
        if path not in SELF_EXCLUDE and path not in allowed
    ]
    if not objects:
        return findings, commits

    # Sizes come from a cheap --batch-check pass, so that the content of the
    # oversized blobs never has to be read.
    sizes: dict[str, int] = {}
    check = subprocess.run(
        ["git", "cat-file", "--batch-check"],
        input="\n".join(sha for sha, _ in objects),
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    for line in check.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] == "blob":
            sizes[parts[0]] = int(parts[2])

    small = [
        (sha, path)
        for sha, path in objects
        if sizes.get(sha, 0) <= MAX_FULL_SCAN
    ]
    if not small:
        return findings, commits

    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=str(root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(b"".join(sha.encode() + b"\n" for sha, _ in small))
        process.stdin.close()
        for sha, path in small:
            header = process.stdout.readline().decode("utf-8", "replace").strip()
            parts = header.split()
            if len(parts) != 3:
                break
            size = int(parts[2])
            raw = process.stdout.read(size)
            process.stdout.read(1)  # trailing newline
            if parts[1] != "blob":
                continue
            content = raw.decode("utf-8", "replace")
            findings.extend(scan_generic(content, f"{path}@{sha[:8]}"))
    finally:
        process.stdout.close()
        process.wait()
    return findings, commits


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

    try:
        if args.history:
            findings, count = scan_history(root, allowed)
            scope = "git history"
            unit = "commit(s)"
        elif args.all:
            targets = tracked_files(root)
            findings = scan_working_tree(targets, root, allowed)
            count = len(targets)
            scope = "tracked files"
            unit = "file(s)"
        else:
            targets = staged_files(root)
            findings = scan_working_tree(targets, root, allowed)
            count = len(targets)
            scope = "staged files"
            unit = "file(s)"
    except RuntimeError as error:
        # A broken search must never be reported as a clean repository.
        print(f"SECRET SCAN ERROR: {error}", file=sys.stderr)
        return 2

    if findings:
        print(f"SECRET SCAN FAILED ({scope}): {len(findings)} finding(s)")
        for finding in findings:
            print(f"  {finding}")
        print(
            "\nIf a finding is a false positive, add an explicit placeholder "
            "marker to the value or refine scripts/check_secrets.py."
        )
        return 1

    print(f"secret scan OK ({scope}): {count} {unit} checked, no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
