"""Frame extraction for video thumbnails (Kitty graphics protocol)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from vtgtui.converter import get_ffmpeg_path, probe_dimensions


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
    orig_w, orig_h = probe_dimensions(video_path)

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


class ThumbnailCache:
    """Simple cache for extracted PNG video frames."""

    def __init__(self, max_entries: int = 20) -> None:
        self._png_cache: dict[tuple, bytes] = {}
        self._max = max_entries
        self._video_path: Optional[str] = None

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
        self._png_cache.clear()
        self._video_path = None
