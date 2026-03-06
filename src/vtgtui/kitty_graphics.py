"""Kitty terminal graphics protocol for inline high-resolution images.

Sends PNG image data directly to the terminal via escape sequences.
Supported by: Kitty, Ghostty, WezTerm, Konsole.

Reference: https://sw.kovidgoyal.net/kitty/graphics-protocol/
"""

from __future__ import annotations

import base64
import os


def detect_kitty_support() -> bool:
    """Check if the terminal likely supports the Kitty graphics protocol."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    term = os.environ.get("TERM", "").lower()

    # Direct matches
    supported = {"kitty", "ghostty", "wezterm"}
    if term_program in supported:
        return True

    # TERM-based detection
    if "xterm-kitty" in term or "xterm-ghostty" in term:
        return True

    # Environment variable detection
    if os.environ.get("GHOSTTY_RESOURCES_DIR"):
        return True
    if os.environ.get("KITTY_WINDOW_ID"):
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

    Uses the Kitty graphics protocol (KgpOld / cursor-based approach).
    Writes directly to /dev/tty to avoid conflicts with Textual's stdout.

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
        # Save cursor position
        tty.write(b"\x1b7")

        # Delete any previous image with this ID
        tty.write(f"\x1b_Ga=d,d=i,i={image_id},q=2;\x1b\\".encode())

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
                # a=T: transmit+display, f=100: PNG format
                # c/r: display size in cells, C=1: don't move cursor
                # q=2: suppress terminal responses, z=-1: behind text
                header = (
                    f"a=T,f=100,i={image_id},"
                    f"c={cols},r={rows},"
                    f"C=1,z=-1,q=2,m={m}"
                )
            else:
                header = f"m={m}"

            tty.write(f"\x1b_G{header};{chunk}\x1b\\".encode())

        # Restore cursor position
        tty.write(b"\x1b8")
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
        tty.write(f"\x1b_Ga=d,d=i,i={image_id},q=2;\x1b\\".encode())
        tty.flush()
    finally:
        tty.close()
