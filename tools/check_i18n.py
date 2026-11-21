#!/usr/bin/python3
"""Sanity check for translations: every tr() key exists in every language."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from g6app.i18n import LANGUAGES, TRANSLATIONS  # noqa: E402

KEY_RE = re.compile(r"""tr\(\s*(?:f?)(["'])([a-zA-Z0-9_.]+)\1""")
DYNAMIC_PREFIXES = ("fx.", "preset.")


def used_keys() -> set[str]:
    keys: set[str] = set()
    for path in (ROOT / "g6app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        keys.update(match[1] for match in KEY_RE.findall(text))
        for effect in ("surround", "crystalizer", "bass", "dialog", "smartvol"):
            if f"fx.{effect}" in text:
                keys.add(f"fx.{effect}.title")
                keys.add(f"fx.{effect}.desc")
        for preset in ("flat", "gaming", "fps", "music", "cinema", "bass", "vocal", "night"):
            if "preset.{preset.name}" in text:
                keys.add(f"preset.{preset}")
    return keys


def main() -> int:
    keys = used_keys()
    failures = 0
    for code, _name in LANGUAGES:
        catalog = TRANSLATIONS.get(code, {})
        missing = sorted(key for key in keys if key not in catalog)
        extra = sorted(key for key in catalog if key not in keys)
        if missing:
            failures += 1
            print(f"{code}: missing {len(missing)}:")
            for key in missing:
                print(f"  {key}")
        if extra:
            print(f"{code}: unused {len(extra)}: {', '.join(extra)}")
    if failures:
        return 1
    print(f"ok: {len(keys)} keys × {len(LANGUAGES)} languages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
