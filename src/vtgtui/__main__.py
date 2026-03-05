"""Entry point for vtgtui."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path


def _desktop_path() -> Path:
    return Path.home() / ".local" / "share" / "applications" / "vtgtui.desktop"


def _desktop_source() -> Path:
    return Path(str(resources.files("vtgtui").joinpath("data/vtgtui.desktop")))


def install_desktop() -> None:
    dest = _desktop_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = _desktop_source()
    shutil.copy2(src, dest)
    print(f"Installed desktop entry: {dest}")


def uninstall_desktop() -> None:
    dest = _desktop_path()
    if dest.exists():
        dest.unlink()
        print(f"Removed desktop entry: {dest}")
    else:
        print(f"No desktop entry found at {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vtgtui",
        description="Video to GIF TUI converter",
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="Install .desktop file to ~/.local/share/applications/",
    )
    parser.add_argument(
        "--uninstall-desktop",
        action="store_true",
        help="Remove .desktop file from ~/.local/share/applications/",
    )
    args = parser.parse_args()

    if args.install_desktop:
        install_desktop()
        sys.exit(0)

    if args.uninstall_desktop:
        uninstall_desktop()
        sys.exit(0)

    from vtgtui.app import VTGApp

    app = VTGApp()
    app.run()


if __name__ == "__main__":
    main()
