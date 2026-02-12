#!/usr/bin/env python3
"""Fix file encoding: strip BOM, convert CRLF to LF, repair mojibake.

Usage:
    python cli/fix_encoding.py <file1> [file2 ...]
    python cli/fix_encoding.py --staged          # fix all git-staged files
    python cli/fix_encoding.py --modified         # fix all git-modified files

Fixes:
    - Removes UTF-8 BOM (byte order mark)
    - Converts CRLF line endings to LF
    - Repairs common mojibake (UTF-8 read as Windows-1252)
    - Skips binary files

Safe to run multiple times (idempotent).
"""

import subprocess
import sys
from pathlib import Path

BOM = b"\xef\xbb\xbf"

# Common mojibake: UTF-8 bytes read as Windows-1252 then re-encoded as UTF-8.
# Each key is the garbled string, value is the correct character.
MOJIBAKE_REPAIRS = {
    # Box-drawing characters (U+2500-U+257F)
    "\u00e2\u0094\u008c": "\u250c",  # ┌ (box drawings light down and right)
    "\u00e2\u0094\u0080": "\u2500",  # ─ (box drawings light horizontal)
    "\u00e2\u0094\u0082": "\u2502",  # │ (box drawings light vertical)
    "\u00e2\u0094\u0094": "\u2514",  # └ (box drawings light up and right)
    "\u00e2\u0094\u0098": "\u2518",  # ┘ (box drawings light up and left)
    "\u00e2\u0094\u00ac": "\u252c",  # ┬ (box drawings light down and horizontal)
    "\u00e2\u0094\u00b4": "\u2534",  # ┴ (box drawings light up and horizontal)
    "\u00e2\u0094\u009c": "\u251c",  # ├ (box drawings light vertical and right)
    "\u00e2\u0094\u00a4": "\u2524",  # ┤ (box drawings light vertical and left)
    "\u00e2\u0094\u00bc": "\u253c",  # ┼ (box drawings light vertical and horizontal)
    "\u00e2\u0094\u0090": "\u2510",  # ┐ (box drawings light down and left)
    "\u00e2\u0096\u00bc": "\u25bc",  # ▼ (black down-pointing triangle)
    "\u00e2\u0096\u00ba": "\u25ba",  # ► (black right-pointing pointer)

    # Windows-1252 variants (bytes 0x80-0x9F interpreted as cp1252)
    "\u00e2\u201d\u20ac": "\u2500",  # ─
    "\u00e2\u201d\u201a": "\u2502",  # │
    "\u00e2\u201d\u0152": "\u250c",  # ┌
    "\u00e2\u201d\u2018": "\u2510",  # ┐
    "\u00e2\u201d\u201d": "\u2514",  # └
    "\u00e2\u201d\u02dc": "\u2518",  # ┘
    "\u00e2\u201d\u0153": "\u251c",  # ├
    "\u00e2\u201d\u00a4": "\u2524",  # ┤
    "\u00e2\u201d\u00ac": "\u252c",  # ┬
    "\u00e2\u201d\u00b4": "\u2534",  # ┴
    "\u00e2\u201d\u00bc": "\u253c",  # ┼

    # Typography
    "\u00e2\u20ac\u00a2": "\u2022",  # • (bullet)
    "\u00e2\u0086\u2019": "\u2192",  # → (rightwards arrow)
    "\u00e2\u0086\u0090": "\u2190",  # ← (leftwards arrow)
    "\u00e2\u2020\u2019": "\u2192",  # → (right arrow, alt encoding)
    "\u00c2\u00a7": "\u00a7",        # § (section sign)
    "\u00e2\u0153\u2026": "\u2705",  # ✅ (white heavy check mark)
    "\u00e2\u008c": "\u274c",        # ❌ (cross mark)
    "\u00c2\u00b0": "\u00b0",        # ° (degree sign)
    "\u00c3\u0097": "\u00d7",        # × (multiplication sign)

    # Quotes and dashes
    "\u00e2\u20ac\u201c": "\u2014",  # — (em dash)
    "\u00e2\u20ac\u201d": "\u2014",  # — (em dash, alt)
    "\u00e2\u0080\u0094": "\u2014",  # — (em dash, another encoding)
    "\u00e2\u20ac\u0093": "\u2013",  # – (en dash)
    "\u00e2\u0080\u0093": "\u2013",  # – (en dash, alt)
    "\u00e2\u20ac\u2122": "\u2019",  # ' (right single quotation mark)
    "\u00e2\u0080\u2122": "\u2019",  # ' (right single quote, alt)
    "\u00e2\u20ac\u0153": "\u201c",  # " (left double quotation mark)
    "\u00e2\u0080\u009c": "\u201c",  # " (left double quote, alt)
    "\u00e2\u20ac\u009d": "\u201d",  # " (right double quotation mark)
    "\u00e2\u0080\u009d": "\u201d",  # " (right double quote, alt)
    "\u00e2\u0080\u00a6": "\u2026",  # … (horizontal ellipsis)
}


def fix_file(path: Path) -> list[str]:
    """Fix encoding issues in a single file. Returns list of fixes applied."""
    fixes = []
    try:
        data = path.read_bytes()
    except (OSError, PermissionError) as e:
        print(f"  SKIP {path}: {e}")
        return fixes

    # Skip binary files (null bytes)
    if b"\x00" in data[:8192]:
        return fixes

    original = data

    if data.startswith(BOM):
        data = data[len(BOM):]
        fixes.append("stripped BOM")

    if b"\r\n" in data:
        data = data.replace(b"\r\n", b"\n")
        fixes.append("CRLF -> LF")

    # Mojibake repair (work on decoded text)
    try:
        text = data.decode("utf-8")
        repaired = text
        for garbled, correct in MOJIBAKE_REPAIRS.items():
            if garbled in repaired:
                repaired = repaired.replace(garbled, correct)
        if repaired != text:
            data = repaired.encode("utf-8")
            fixes.append("repaired mojibake")
    except UnicodeDecodeError:
        pass  # Not valid UTF-8, skip mojibake repair

    if data != original:
        path.write_bytes(data)
        print(f"  FIXED {path}: {', '.join(fixes)}")
    return fixes


def get_git_files(flag: str) -> list[Path]:
    """Get files from git status."""
    if flag == "--staged":
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    elif flag == "--modified":
        cmd = ["git", "diff", "--name-only", "--diff-filter=ACM"]
        # Also include untracked files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True,
        )
        untracked = [Path(f) for f in result.stdout.strip().splitlines() if f]
    else:
        return []

    result = subprocess.run(cmd, capture_output=True, text=True)
    files = [Path(f) for f in result.stdout.strip().splitlines() if f]

    if flag == "--modified":
        files.extend(untracked)

    return files


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] in ("--staged", "--modified"):
        files = get_git_files(sys.argv[1])
    else:
        files = [Path(f) for f in sys.argv[1:]]

    if not files:
        print("No files to check.")
        return

    total_fixes = 0
    for f in files:
        if f.exists() and f.is_file():
            fixes = fix_file(f)
            total_fixes += len(fixes)

    if total_fixes:
        print(f"\n{total_fixes} fix(es) applied.")
    else:
        print("All files clean.")


if __name__ == "__main__":
    main()
