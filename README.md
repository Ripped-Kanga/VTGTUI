# VTGTUI

A TUI application written in Python to convert video files to GIFs.

## Installation

```bash
pipx install git+https://github.com/Ripped-Kanga/VTGTUI.git
```

Or install from a local clone:

```bash
git clone https://github.com/Ripped-Kanga/VTGTUI.git
cd VTGTUI
pipx install .
```

For development:

```bash
pip install -e .
```

## Usage

Launch the TUI:

```bash
vtgtui
```

Or run as a module:

```bash
python -m vtgtui
```

### Controls

- **Browse** (`Ctrl+B`) to open a native file picker, or type a path into the input field
- **Trim** the video by setting start and end times (in seconds), or drag the timeline scrubber handles
- Select a **quality preset** (or configure **Custom** settings) and click **Convert**
- The **spec panels** show input video details alongside the expected GIF output specs, updating live as you change quality or trim settings
- Press `Escape` to cancel an in-progress conversion
- Press `q` to quit

### Quality Presets

| Preset | FPS | Max Width | Colors | Notes |
|---|---|---|---|---|
| Low | 10 | 480px | 128 | Smallest file size |
| Medium | 15 | 640px | 192 | Two-pass, balanced |
| High | 20 | 800px | 256 | Two-pass, best built-in preset |
| Custom | Configurable | Configurable | 2–256 | Opens a settings dialog |

The **Custom** option launches a modal where you can configure FPS, max width, color count, and whether to use two-pass palette generation.

### Video Trimming

Set the **Start** and **End** time fields (in seconds) to convert only a portion of the video. When a file is selected, these fields are automatically populated with the full video duration. Use the interactive timeline scrubber to visually adjust the trim range.

### Supported Formats

`.mp4`, `.avi`, `.mkv`, `.mov`, `.webm`, `.wmv`, `.flv`, `.m4v`, `.mpeg`, `.mpg`, `.3gp`, `.ts`

### Desktop Entry (Linux)

Install a `.desktop` file so VTGTUI appears in your application launcher:

```bash
vtgtui --install-desktop
```

To remove it:

```bash
vtgtui --uninstall-desktop
```

The desktop file is installed to `~/.local/share/applications/vtgtui.desktop`.

## Dependencies

All dependencies are installed automatically via pip/pipx:

- [Textual](https://textual.textualize.io/) — TUI framework
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — Bundled ffmpeg binary (no system ffmpeg required)

## License

MIT
