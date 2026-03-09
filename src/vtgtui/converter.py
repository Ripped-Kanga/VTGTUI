"""Video to GIF conversion using ffmpeg via imageio-ffmpeg."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import imageio_ffmpeg

_TIME_PATTERN = re.compile(r"out_time_us=(\d+)")

SUPPORTED_EXTENSIONS = {
    ".mp4", ".avi", ".mkv", ".mov", ".webm", ".wmv",
    ".flv", ".m4v", ".mpeg", ".mpg", ".3gp", ".ts",
}


@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float


@dataclass
class QualityPreset:
    name: str
    fps: Optional[int]  # None means use original
    max_width: Optional[int]  # None means no scaling
    colors: int
    two_pass: bool


QUALITY_PRESETS: dict[str, QualityPreset] = {
    "low": QualityPreset(name="Low", fps=10, max_width=480, colors=128, two_pass=False),
    "medium": QualityPreset(name="Medium", fps=15, max_width=640, colors=192, two_pass=True),
    "high": QualityPreset(name="High", fps=20, max_width=800, colors=256, two_pass=True),
}


def get_ffmpeg_path() -> str:
    """Get the path to the ffmpeg binary bundled with imageio-ffmpeg."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def get_ffprobe_path() -> str:
    """Get the path to ffprobe, falling back to system ffprobe."""
    ffmpeg = get_ffmpeg_path()
    ffmpeg_dir = Path(ffmpeg).parent

    # Try with and without .exe for cross-platform support
    for name in ("ffprobe", "ffprobe.exe"):
        candidate = ffmpeg_dir / name
        if candidate.exists():
            return str(candidate)

    # Fall back to system ffprobe
    return "ffprobe"


def is_supported_format(path: str | Path) -> bool:
    """Check if the file has a supported video extension."""
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def get_video_info(path: str | Path) -> VideoInfo:
    """Probe a video file for duration, resolution, and fps."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)

    # Find the video stream
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if video_stream is None:
        raise ValueError("No video stream found in file")

    width = int(video_stream["width"])
    height = int(video_stream["height"])

    # Parse fps from r_frame_rate (e.g. "30/1" or "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den) if float(den) != 0 else 30.0

    # Duration from format or stream
    duration = float(data.get("format", {}).get("duration", 0))
    if duration == 0:
        duration = float(video_stream.get("duration", 0))

    return VideoInfo(duration=duration, width=width, height=height, fps=fps)


def _build_filter(preset: QualityPreset, video_info: VideoInfo) -> str:
    """Build the ffmpeg filter string for the given quality preset."""
    fps = preset.fps if preset.fps is not None else min(video_info.fps, 50)
    parts = [f"fps={fps}"]

    if preset.max_width and video_info.width > preset.max_width:
        parts.append(f"scale={preset.max_width}:-1:flags=lanczos")

    return ",".join(parts)


def _build_trim_args(start_time: Optional[float], end_time: Optional[float]) -> list[str]:
    """Build ffmpeg input args for trimming."""
    args: list[str] = []
    if start_time is not None and start_time > 0:
        args.extend(["-ss", str(start_time)])
    if end_time is not None and end_time > 0:
        args.extend(["-to", str(end_time)])
    return args


def _effective_duration(
    video_info: VideoInfo,
    start_time: Optional[float],
    end_time: Optional[float],
) -> float:
    """Calculate the effective duration after trimming for progress tracking."""
    start = start_time if start_time and start_time > 0 else 0.0
    end = end_time if end_time and end_time > 0 else video_info.duration
    return max(end - start, 0.1)


def convert_video_to_gif(
    input_path: str | Path,
    output_path: str | Path,
    quality: str | QualityPreset = "high",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> None:
    """Convert a video file to GIF using ffmpeg.

    Args:
        input_path: Path to the input video file.
        output_path: Path for the output GIF file.
        quality: Preset name ('low', 'medium', 'high') or a QualityPreset.
        start_time: Start time in seconds for trimming (None = from beginning).
        end_time: End time in seconds for trimming (None = to end).
        progress_callback: Called with progress percentage (0-100).
        cancel_check: Called to check if conversion should be cancelled.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    ffmpeg = get_ffmpeg_path()
    preset = quality if isinstance(quality, QualityPreset) else QUALITY_PRESETS[quality]

    video_info = get_video_info(input_path)
    filter_str = _build_filter(preset, video_info)
    trim_args = _build_trim_args(start_time, end_time)
    duration = _effective_duration(video_info, start_time, end_time)

    if preset.two_pass:
        _convert_two_pass(
            ffmpeg, input_path, output_path, filter_str, preset,
            video_info, progress_callback, cancel_check, trim_args, duration,
        )
    else:
        _convert_single_pass(
            ffmpeg, input_path, output_path, filter_str, preset,
            video_info, progress_callback, cancel_check, trim_args, duration,
        )


def _convert_single_pass(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    filter_str: str,
    preset: QualityPreset,
    video_info: VideoInfo,
    progress_callback: Optional[Callable[[float], None]],
    cancel_check: Optional[Callable[[], bool]],
    trim_args: Optional[list[str]] = None,
    duration: Optional[float] = None,
) -> None:
    """Single-pass conversion for lower quality presets."""
    split_filter = f"{filter_str},split[s0][s1];[s0]palettegen=max_colors={preset.colors}[p];[s1][p]paletteuse"
    cmd = [
        ffmpeg,
        "-y",
        "-progress", "pipe:1",
        *(trim_args or []),
        "-i", str(input_path),
        "-lavfi", split_filter,
        "-loop", "0",
        str(output_path),
    ]
    _run_ffmpeg(cmd, duration or video_info.duration, progress_callback, cancel_check)


def _convert_two_pass(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    filter_str: str,
    preset: QualityPreset,
    video_info: VideoInfo,
    progress_callback: Optional[Callable[[float], None]],
    cancel_check: Optional[Callable[[], bool]],
    trim_args: Optional[list[str]] = None,
    duration: Optional[float] = None,
) -> None:
    """Two-pass conversion for higher quality presets using palettegen."""
    effective_duration = duration or video_info.duration
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        palette_path = tmp.name

    try:
        # Pass 1: Generate palette
        cmd_palette = [
            ffmpeg,
            "-y",
            "-progress", "pipe:1",
            *(trim_args or []),
            "-i", str(input_path),
            "-vf", f"{filter_str},palettegen=max_colors={preset.colors}:stats_mode=diff",
            str(palette_path),
        ]

        def pass1_progress(pct: float) -> None:
            if progress_callback:
                progress_callback(pct * 0.4)  # Pass 1 is 40% of total

        _run_ffmpeg(cmd_palette, effective_duration, pass1_progress, cancel_check)

        if cancel_check and cancel_check():
            return

        # Pass 2: Apply palette
        dither = "sierra2_4a" if quality_needs_dither(preset) else "none"
        cmd_gif = [
            ffmpeg,
            "-y",
            "-progress", "pipe:1",
            *(trim_args or []),
            "-i", str(input_path),
            "-i", str(palette_path),
            "-lavfi", f"{filter_str}[x];[x][1:v]paletteuse=dither={dither}",
            "-loop", "0",
            str(output_path),
        ]

        def pass2_progress(pct: float) -> None:
            if progress_callback:
                progress_callback(40 + pct * 0.6)  # Pass 2 is 60% of total

        _run_ffmpeg(cmd_gif, effective_duration, pass2_progress, cancel_check)
    finally:
        if os.path.exists(palette_path):
            os.unlink(palette_path)


def quality_needs_dither(preset: QualityPreset) -> bool:
    """Determine if dithering should be used based on quality preset."""
    return preset.colors < 256


def _run_ffmpeg(
    cmd: list[str],
    duration: float,
    progress_callback: Optional[Callable[[float], None]],
    cancel_check: Optional[Callable[[], bool]],
) -> None:
    """Run an ffmpeg command and parse progress from stdout."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        for line in iter(process.stdout.readline, ""):
            if cancel_check and cancel_check():
                process.terminate()
                process.wait()
                return

            match = _TIME_PATTERN.search(line)
            if match and duration > 0 and progress_callback:
                current_us = int(match.group(1))
                current_s = current_us / 1_000_000
                pct = min((current_s / duration) * 100, 100)
                progress_callback(pct)

        process.wait()
        if process.returncode != 0:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"ffmpeg failed (exit {process.returncode}): {stderr}")
    except Exception:
        process.kill()
        process.wait()
        raise
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
