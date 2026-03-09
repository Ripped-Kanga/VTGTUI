# VTGTUI — Codebase Summary

## Project Overview
**VTGTUI** (Video To GIF TUI) is a Python terminal UI application for converting video files to GIFs. Built with [Textual](https://textual.textualize.io/) and [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg). Version 1.0.0, MIT licensed.

## Tech Stack
- **Python** >= 3.9
- **Textual** >= 8.0.0 — TUI framework
- **imageio-ffmpeg** >= 0.5.1 — bundles ffmpeg binary (no system ffmpeg required)
- **Build**: Hatchling (`pyproject.toml`)
- **Entry point**: `vtgtui` CLI command → `vtgtui.__main__:main`

## Source Layout
```
src/vtgtui/
├── __init__.py
├── __main__.py          # Entry point (runs VTGApp)
├── app.py               # Main Textual App + modal screens
├── app.tcss             # Textual CSS stylesheet
├── browse.py            # Cross-platform native file picker dialog
├── converter.py         # ffmpeg wrapper: probe, convert, quality presets
├── kitty_graphics.py    # Kitty terminal graphics protocol (inline images)
├── scrubber.py          # TimelineScrubber + FramePreview widgets
├── thumbnails.py        # Frame extraction + ThumbnailCache
└── data/
    └── vtgtui.desktop   # Linux desktop integration file
```

## Module Responsibilities

### `app.py` — Main Application
- **`VTGApp`**: Root Textual `App`. Manages UI state, input validation, and wires together all widgets.
  - Input path, output path, start/end trim time fields
  - Quality `Select` dropdown
  - Browse button (platform-aware)
  - `TimelineScrubber` and `FramePreview` widgets
  - Conversion runs in a background thread via `@work(thread=True)`
  - Progress tracked via `ProgressBar`, logs written to `RichLog`
  - Cancel support via `Escape` key
- **`FileBrowserScreen`**: Modal Textual file browser (used on Linux). Uses `_VideoTree` (subclass of `DirectoryTree`) that filters to supported video formats only.
- **`CustomQualityScreen`**: Modal for configuring a custom `QualityPreset` (FPS, max width, colors, two-pass).

### `converter.py` — Conversion Engine
- **`VideoInfo`** dataclass: `duration`, `width`, `height`, `fps`
- **`QualityPreset`** dataclass: `name`, `fps`, `max_width`, `colors`, `two_pass`
- **`QUALITY_PRESETS`**: `low`, `medium`, `high` presets
- **`SUPPORTED_EXTENSIONS`**: `.mp4 .avi .mkv .mov .webm .wmv .flv .m4v .mpeg .mpg .3gp .ts`
- **`get_video_info()`**: Probes with `ffmpeg -i`, parses stderr (no ffprobe needed)
- **`convert_video_to_gif()`**: Dispatches to single-pass or two-pass ffmpeg conversion
  - Single-pass: `split[s0][s1];palettegen;paletteuse` in one command
  - Two-pass: separate `palettegen` → `paletteuse` with optional dithering
  - Progress via `out_time_us=` from `ffmpeg -progress pipe:1`
  - Cancellation via `cancel_check` callback

### `browse.py` — File Picker
Cross-platform native file picker (used only on macOS/Windows; Linux uses `FileBrowserScreen`):
- **macOS**: `osascript` (AppleScript)
- **Windows**: PowerShell `OpenFileDialog`
- **Linux fallback** (if called directly): tries `zenity` → `kdialog` → `yad` → `qarma` → tkinter

### `scrubber.py` — Custom Widgets
- **`TimelineScrubber`**: Focusable widget rendering a 3-line timeline bar with draggable start/end handles. Posts `StartChanged`, `EndChanged`, `CursorMoved` messages. Keyboard: arrows to nudge, Tab to switch handle, Home/End to jump.
- **`FramePreview`**: Displays a video frame using the Kitty graphics protocol. Auto-hides on unsupported terminals. Uses `ThumbnailCache`. Frames extracted in background threads.

### `thumbnails.py` — Frame Extraction
- **`extract_frame_png()`**: Runs `ffmpeg` to extract a single PNG frame at a timestamp, scaled to fit within bounds.
- **`ThumbnailCache`**: LRU-style dict cache (max 20 entries). Keyed on `(path, timestamp_rounded_to_0.1s, max_width, max_height)`. Cache is cleared on video path change.

### `kitty_graphics.py` — Terminal Image Protocol
- **`detect_kitty_support()`**: Checks `TERM_PROGRAM`, `TERM`, `KITTY_WINDOW_ID`, `GHOSTTY_RESOURCES_DIR`. Supported terminals: Kitty, Ghostty, WezTerm, Konsole.
- **`show_image()`**: Sends PNG via Kitty graphics protocol escape sequences directly to `/dev/tty` (bypasses Textual stdout). Uses `q=2` to suppress terminal responses.
- **`hide_image()`**: Deletes a displayed image by ID.

## Key Design Patterns
- All long-running work (conversion, frame extraction, native file dialogs) runs in background threads via Textual's `@work(thread=True)`. UI updates are marshalled back via `call_from_thread`.
- Modal screens (`FileBrowserScreen`, `CustomQualityScreen`) use `hide_kitty()` / `restore_kitty()` to avoid Kitty image overlap with Textual overlays.
- The scrubber and trim inputs are kept in sync bidirectionally via a `_syncing_scrubber` guard flag.
- ffmpeg is sourced exclusively from `imageio_ffmpeg.get_ffmpeg_exe()` — no system ffmpeg dependency.

## Terminal Requirements (Linux)

**Recommended terminal: [Kitty](https://sw.kovidgoyal.net/kitty/)**

Kitty is the only terminal confirmed to support all advanced features on Linux:

| Feature | Kitty | Ghostty | Alacritty | WezTerm |
|---|---|---|---|---|
| Frame preview (Kitty graphics protocol) | ✅ | ✅ | ❌ | ✅ |
| File drag-and-drop | ✅ | ❌ | ❌ | ✅ |

File drag-and-drop requires the terminal to convert Wayland/X11 XDG DnD file drops into bracketed paste. Ghostty and Alacritty do not implement this — the window focuses on drag but no paste event is sent to the app.

When developing or testing on Linux, **use Kitty** to exercise the full feature set.

## Running / Installing
```bash
pip install -e .
vtgtui
```
