"""Cross-platform native file browser dialog for selecting video files."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _extensions_glob() -> list[str]:
    """Return supported video extensions as glob patterns."""
    from vtgtui.converter import SUPPORTED_EXTENSIONS
    return [f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)]


def _extensions_mime() -> str:
    """Pipe-separated glob patterns for zenity/kdialog filters."""
    return " ".join(_extensions_glob())


def browse_for_video() -> str | None:
    """Open a native file-picker dialog and return the selected path.

    Tries platform-appropriate tools in order, returning None if no
    dialog could be opened or the user cancelled.
    """
    if sys.platform == "darwin":
        return _browse_macos()
    elif sys.platform == "win32":
        return _browse_windows()
    else:
        return _browse_linux()


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _browse_macos() -> str | None:
    exts = ", ".join(f'".{e.lstrip("*.")}"' for e in _extensions_glob())
    script = (
        'tell application "System Events"\n'
        '  set f to choose file with prompt "Select a video file" '
        f'of type {{{exts}}}\n'
        "  return POSIX path of f\n"
        "end tell"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

def _browse_windows() -> str | None:
    from vtgtui.converter import SUPPORTED_EXTENSIONS
    exts = ";".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        "$d.Title = 'Select a video file'; "
        f"$d.Filter = 'Video files|{exts}|All files|*.*'; "
        "if ($d.ShowDialog() -eq 'OK') { Write-Output $d.FileName }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Linux — try tools in order of preference
# ---------------------------------------------------------------------------

def _browse_linux() -> str | None:
    globs = _extensions_glob()

    # 1. zenity — GTK, works on GNOME, XFCE, and most Wayland compositors
    if shutil.which("zenity"):
        filter_arg = "--file-filter=Video files (" + " ".join(globs) + ")|" + " ".join(globs)
        try:
            result = subprocess.run(
                ["zenity", "--file-selection", "--title=Select a video file", filter_arg],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass

    # 2. kdialog — KDE / Qt
    if shutil.which("kdialog"):
        filter_str = "Video files (" + " ".join(globs) + ")"
        try:
            result = subprocess.run(
                ["kdialog", "--getopenfilename", str(Path.home()), filter_str],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass

    # 3. yad — GTK2/3 alternative to zenity
    if shutil.which("yad"):
        filter_arg = "|".join(globs)
        try:
            result = subprocess.run(
                ["yad", "--file-selection", "--title=Select a video file",
                 f"--file-filter={filter_arg}"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass

    # 4. qarma — zenity fork used on some distros
    if shutil.which("qarma"):
        filter_arg = "--file-filter=Video files (" + " ".join(globs) + ")|" + " ".join(globs)
        try:
            result = subprocess.run(
                ["qarma", "--file-selection", "--title=Select a video file", filter_arg],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except Exception:
            pass

    # 5. Tkinter — ships with most Python installs; opens an X11/Wayland window
    return _browse_tkinter()


def _browse_tkinter() -> str | None:
    from vtgtui.converter import SUPPORTED_EXTENSIONS
    exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_EXTENSIONS))
    script = (
        "import tkinter as tk; from tkinter import filedialog; "
        "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True); "
        f"f = filedialog.askopenfilename(title='Select a video file', "
        f"filetypes=[('Video files', '{exts}'), ('All files', '*')]); "
        "print(f)"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            return path or None
    except Exception:
        pass
    return None
