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
    max_height: int | None = None,
) -> tuple[bytes, int, int]:
    """Extract a single frame as raw RGB24 bytes.

    Scales to fit within max_width x max_height preserving aspect ratio.
    Uses lanczos scaling for sharp downscaling.

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

    # Scale to fit width first
    scale_w = min(orig_w, max_width)
    scale_h = int(orig_h * (scale_w / orig_w))

    # Then constrain by height if needed
    if max_height and scale_h > max_height:
        scale_h = max_height
        scale_w = int(orig_w * (scale_h / orig_h))

    # Ensure even dimensions for ffmpeg and minimum size
    scale_w = max(scale_w + (scale_w % 2), 2)
    scale_h = max(scale_h + (scale_h % 2), 2)

    cmd = [
        ffmpeg,
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={scale_w}:{scale_h}:flags=lanczos",
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


def extract_frame_png(
    video_path: str | Path,
    timestamp: float,
    max_width: int = 800,
    max_height: int = 600,
) -> bytes:
    """Extract a single frame as PNG bytes for Kitty graphics protocol.

    Returns raw PNG data at up to max_width x max_height, preserving aspect ratio.
    """
    ffmpeg = get_ffmpeg_path()
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

    # Scale to fit within bounds preserving aspect ratio
    scale = min(max_width / orig_w, max_height / orig_h, 1.0)
    scale_w = max(int(orig_w * scale), 2)
    scale_h = max(int(orig_h * scale), 2)
    # Ensure even
    scale_w += scale_w % 2
    scale_h += scale_h % 2

    cmd = [
        ffmpeg,
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={scale_w}:{scale_h}:flags=lanczos",
        "-f", "image2pipe",
        "-vcodec", "png",
        "pipe:1",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg PNG extraction failed: {result.stderr.decode(errors='replace')}"
        )

    return result.stdout


def render_halfblock(
    rgb_bytes: bytes,
    width: int,
    height: int,
    pad_w: int = 0,
    pad_h: int = 0,
) -> Text:
    """Convert raw RGB24 pixel data to Rich Text using half-block characters.

    Each terminal row encodes 2 pixel rows:
    - Foreground color = top pixel row (▀ foreground)
    - Background color = bottom pixel row (▀ background)

    If pad_w/pad_h are given, the image is centered within that cell area.
    """
    text = Text()
    row_bytes = width * 3
    data = rgb_bytes  # local ref for speed

    img_rows = height // 2  # terminal rows the image occupies
    x_pad = max((pad_w - width) // 2, 0) if pad_w > 0 else 0
    y_pad = max((pad_h - img_rows) // 2, 0) if pad_h > 0 else 0

    # Top vertical padding
    if y_pad > 0:
        blank_line = " " * max(pad_w, width)
        for _ in range(y_pad):
            text.append(blank_line + "\n")

    for y in range(0, height - 1, 2):
        top_off = y * row_bytes
        bot_off = (y + 1) * row_bytes

        # Left horizontal padding
        if x_pad > 0:
            text.append(" " * x_pad)

        for x in range(width):
            px = x * 3
            tr = data[top_off + px]
            tg = data[top_off + px + 1]
            tb = data[top_off + px + 2]
            br = data[bot_off + px]
            bg = data[bot_off + px + 1]
            bb = data[bot_off + px + 2]

            text.append(
                "\u2580",
                style=f"rgb({tr},{tg},{tb}) on rgb({br},{bg},{bb})",
            )

        if y + 2 < height:
            text.append("\n")

    return text


class ThumbnailCache:
    """Simple cache for extracted video frames."""

    def __init__(self, max_entries: int = 20) -> None:
        self._cache: dict[tuple[str, float, int, int], tuple[bytes, int, int]] = {}
        self._png_cache: dict[tuple, bytes] = {}
        self._max = max_entries
        self._video_path: Optional[str] = None

    def get(
        self,
        video_path: str | Path,
        timestamp: float,
        max_width: int = 80,
        max_height: int | None = None,
    ) -> tuple[bytes, int, int]:
        """Get a frame, extracting and caching if needed."""
        vp = str(video_path)

        # Clear cache if video changed
        if vp != self._video_path:
            self._cache.clear()
            self._video_path = vp

        key = (vp, round(timestamp, 1), max_width, max_height or 0)

        if key not in self._cache:
            # Evict oldest if full
            if len(self._cache) >= self._max:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = extract_frame_raw(
                vp, timestamp, max_width, max_height
            )

        return self._cache[key]

    def get_png(
        self,
        video_path: str | Path,
        timestamp: float,
        max_width: int = 800,
        max_height: int = 600,
    ) -> bytes:
        """Get a frame as PNG bytes, extracting and caching if needed."""
        vp = str(video_path)

        if vp != self._video_path:
            self._cache.clear()
            self._png_cache.clear()
            self._video_path = vp

        key = (vp, round(timestamp, 1), max_width, max_height)

        if key not in self._png_cache:
            if len(self._png_cache) >= self._max:
                oldest = next(iter(self._png_cache))
                del self._png_cache[oldest]
            self._png_cache[key] = extract_frame_png(
                vp, timestamp, max_width, max_height
            )

        return self._png_cache[key]

    def clear(self) -> None:
        """Clear all cached frames."""
        self._cache.clear()
        self._png_cache.clear()
        self._video_path = None
