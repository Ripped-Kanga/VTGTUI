"""Frame extraction and half-block terminal rendering for video thumbnails."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from rich.text import Text

from vtgtui.converter import get_ffmpeg_path, get_ffprobe_path


def extract_frame_raw(
    video_path: str | Path,
    timestamp: float,
    max_width: int = 80,
) -> tuple[bytes, int, int]:
    """Extract a single frame as raw RGB24 bytes, scaled to fit width.

    Scales the frame to max_width preserving aspect ratio. The caller is
    responsible for cropping the rendered output to fit the display height.

    Returns (rgb_bytes, width, height).
    """
    ffmpeg = get_ffmpeg_path()

    # First probe the video to get dimensions for correct output size
    ffprobe = get_ffprobe_path()
    probe_cmd = [
        ffprobe, "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-print_format", "csv=p=0:s=x",
        str(video_path),
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
    if probe_result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {probe_result.stderr}")

    parts = probe_result.stdout.strip().split("x")
    orig_w, orig_h = int(parts[0]), int(parts[1])

    # Scale to fit width, preserving aspect ratio
    scale_w = min(orig_w, max_width)
    scale_h = int(orig_h * (scale_w / orig_w))

    # Ensure even dimensions for ffmpeg and minimum size
    scale_w = max(scale_w + (scale_w % 2), 2)
    scale_h = max(scale_h + (scale_h % 2), 2)

    cmd = [
        ffmpeg,
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={scale_w}:{scale_h}",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "pipe:1",
    ]
    result = subprocess.run(
        cmd, capture_output=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {result.stderr.decode(errors='replace')}")

    rgb_bytes = result.stdout
    expected = scale_w * scale_h * 3
    if len(rgb_bytes) < expected:
        raise RuntimeError(
            f"Incomplete frame data: got {len(rgb_bytes)} bytes, expected {expected}"
        )

    return rgb_bytes[:expected], scale_w, scale_h


def render_halfblock(
    rgb_bytes: bytes, width: int, height: int, max_rows: int | None = None,
) -> Text:
    """Convert raw RGB24 pixel data to Rich Text using half-block characters.

    Each terminal row encodes 2 pixel rows:
    - Foreground color = top pixel row
    - Background color = bottom pixel row
    - Character = upper half block (U+2580)

    If max_rows is set and the image would produce more terminal rows,
    the output is center-cropped vertically to fit.
    """
    text = Text()
    row_bytes = width * 3

    # Total terminal rows the full image would need
    total_term_rows = height // 2

    # Determine vertical pixel range to render (center crop)
    if max_rows and total_term_rows > max_rows:
        # Skip pixel rows to center the crop
        skip_pixels = (total_term_rows - max_rows)  # in terminal rows
        y_start = skip_pixels  # skip this many pixel-pairs from top
        y_start = y_start + (y_start % 2)  # ensure even for pixel-pair alignment
        y_end = y_start + max_rows * 2
    else:
        y_start = 0
        y_end = height

    first = True
    for y in range(y_start, min(y_end, height - 1), 2):
        if not first:
            text.append("\n")
        first = False

        top_offset = y * row_bytes
        bot_offset = (y + 1) * row_bytes

        for x in range(width):
            px = x * 3
            # Top pixel (foreground)
            tr = rgb_bytes[top_offset + px]
            tg = rgb_bytes[top_offset + px + 1]
            tb = rgb_bytes[top_offset + px + 2]
            # Bottom pixel (background)
            br = rgb_bytes[bot_offset + px]
            bg = rgb_bytes[bot_offset + px + 1]
            bb = rgb_bytes[bot_offset + px + 2]

            text.append(
                "\u2580",  # Upper half block
                style=f"rgb({tr},{tg},{tb}) on rgb({br},{bg},{bb})",
            )

    return text


class ThumbnailCache:
    """Simple cache for extracted video frames."""

    def __init__(self, max_entries: int = 20) -> None:
        self._cache: dict[tuple[str, float, int], tuple[bytes, int, int]] = {}
        self._max = max_entries
        self._video_path: Optional[str] = None

    def get(
        self,
        video_path: str | Path,
        timestamp: float,
        max_width: int = 80,
    ) -> tuple[bytes, int, int]:
        """Get a frame, extracting and caching if needed."""
        vp = str(video_path)

        # Clear cache if video changed
        if vp != self._video_path:
            self._cache.clear()
            self._video_path = vp

        # Include width in key so resizes get fresh frames
        key = (vp, round(timestamp, 1), max_width)

        if key not in self._cache:
            # Evict oldest if full
            if len(self._cache) >= self._max:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = extract_frame_raw(vp, timestamp, max_width)

        return self._cache[key]

    def clear(self) -> None:
        """Clear all cached frames."""
        self._cache.clear()
        self._video_path = None
