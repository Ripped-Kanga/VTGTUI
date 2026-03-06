"""Kitty terminal graphics protocol for inline high-resolution images.

Sends PNG image data directly to the terminal via escape sequences.
Supported by: Kitty, Ghostty, WezTerm, Konsole.
"""

from __future__ import annotations

import base64
import os
import sys


def detect_kitty_support() -> bool:
    """Check if the terminal likely supports the Kitty graphics protocol."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()

    supported = {"kitty", "ghostty", "wezterm"}
    if term_program in supported:
        return True
    if "xterm-kitty" in term:
        return True
    return False


def _open_tty():
    """Open /dev/tty for direct terminal writes (bypasses Textual's stdout)."""
    return open("/dev/tty", "wb")


def show_image(
    png_data: bytes,
    x: int,
    y: int,
    cols: int,
    rows: int,
    image_id: int = 1,
) -> None:
    """Display a PNG image at a terminal cell position.

    Args:
        png_data: Raw PNG file bytes.
        x: Column position (0-based).
        y: Row position (0-based).
        cols: Display width in terminal columns.
        rows: Display height in terminal rows.
        image_id: Unique ID for later deletion.
    """
    try:
        tty = _open_tty()
    except OSError:
        return

    try:
        # Delete any previous image with this ID
        tty.write(f"\x1b_Ga=d,d=i,i={image_id};\x1b\\".encode())

        # Move cursor to target position
        tty.write(f"\x1b[{y + 1};{x + 1}H".encode())

        # Base64 encode PNG and send in chunks
        b64 = base64.standard_b64encode(png_data).decode("ascii")
        chunk_size = 4096
        total = len(b64)

        for i in range(0, total, chunk_size):
            chunk = b64[i : i + chunk_size]
            is_last = i + chunk_size >= total
            m = 0 if is_last else 1

            if i == 0:
                header = f"a=T,f=100,i={image_id},c={cols},r={rows},m={m},q=2"
            else:
                header = f"m={m}"

            tty.write(f"\x1b_G{header};{chunk}\x1b\\".encode())

        tty.flush()
    finally:
        tty.close()


def hide_image(image_id: int = 1) -> None:
    """Delete a previously displayed image."""
    try:
        tty = _open_tty()
    except OSError:
        return

    try:
        tty.write(f"\x1b_Ga=d,d=i,i={image_id};\x1b\\".encode())
        tty.flush()
    finally:
        tty.close()
