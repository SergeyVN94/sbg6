"""XDG autostart entry (``~/.config/autostart/sbg6.desktop``)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
AUTOSTART_FILE = CONFIG_HOME / "autostart" / "sbg6.desktop"


def _inside_own_appimage() -> str | None:
    """Return our AppImage path, but not an AppImage we merely run inside of.

    Other AppImages (for example an editor that hosts a terminal) export
    APPIMAGE/APPDIR into the environment, so the variables alone are not proof
    that *we* are the AppImage: the running interpreter must live in APPDIR.
    """
    appimage = os.environ.get("APPIMAGE")
    appdir = os.environ.get("APPDIR")
    if not appimage or not appdir:
        return None
    try:
        executable = Path(sys.executable).resolve()
        if executable.is_relative_to(Path(appdir).resolve()):
            return appimage
    except (OSError, ValueError):
        return None
    return None


def launcher_command() -> list[str]:
    """How to start this copy of the app (source tree, deb or AppImage)."""
    appimage = _inside_own_appimage()
    if appimage:
        return [appimage, "gui", "--tray"]
    argv0 = Path(sys.argv[0]).resolve()
    if argv0.name == "g6":
        return [str(argv0), "gui", "--tray"]
    installed = Path("/usr/bin/g6")
    if installed.exists():
        return [str(installed), "gui", "--tray"]
    found = shutil.which("g6")
    if found:
        return [str(Path(found).resolve()), "gui", "--tray"]
    return ["g6", "gui", "--tray"]


def _exec_line(parts: list[str]) -> str:
    quoted = [part if " " not in part and '"' not in part else '"' + part.replace('"', '\\"') + '"' for part in parts]
    return " ".join(quoted)


def entry_text() -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=Sound Blaster G6\n"
        "Comment=Sound BlasterX G6 control\n"
        f"Exec={_exec_line(launcher_command())}\n"
        "Icon=sbg6\n"
        "Terminal=false\n"
        "StartupNotify=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def is_enabled() -> bool:
    return AUTOSTART_FILE.exists()


def enable() -> Path:
    AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(entry_text(), encoding="utf-8")
    return AUTOSTART_FILE


def disable() -> bool:
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        return True
    return False
