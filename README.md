# VTGTUI

(Video to GIF Terminal User Interface) A TUI application written in Python by Claude AI to convert video files to GIFs.

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

| Key | Action |
|---|---|
| `Ctrl+B` | Open native file picker |
| `Ctrl+O` | Focus the input path field |
| `Escape` | Cancel an in-progress conversion |
| `q` | Quit |

### Video Trimming

Set the **Start** and **End** time fields (in seconds) to convert only a portion of the video. When a file is selected, these fields are automatically populated with the full video duration.

The interactive **timeline scrubber** lets you visually drag start/end handles. When focused:

| Key | Action |
|---|---|
| `Left` / `Right` | Nudge active handle by 0.1s |
| `Shift+Left` / `Shift+Right` | Nudge active handle by 1.0s |
| `Tab` | Switch between start and end handles |
| `Home` | Jump active handle to the start |
| `End` | Jump active handle to the end |

### Frame Preview

A live frame preview updates as you scrub through the timeline. In terminals that support the **Kitty graphics protocol** (Kitty, Ghostty, WezTerm, Konsole), frames are displayed at high resolution. The preview preserves the video's aspect ratio and centers within the available space.

### Drag and Drop

Drag a video file from your file manager directly onto the terminal window to load it instantly. The app detects the dropped file path and populates all fields automatically.

> **Linux:** This requires a terminal that converts file drag-and-drop to bracketed paste. **[Kitty](https://sw.kovidgoyal.net/kitty/) is recommended** — it fully supports this on both X11 and Wayland. Ghostty and Alacritty do not currently support file drag-and-drop.

### Quality Presets

| Preset | FPS | Max Width | Colors | Notes |
|---|---|---|---|---|
| Low | 10 | 480px | 128 | Smallest file size |
| Medium | 15 | 640px | 192 | Two-pass, balanced |
| High | 20 | 800px | 256 | Two-pass, best built-in preset |
| Custom | Configurable | Configurable | 2–256 | Opens a settings dialog |

The **Custom** option launches a modal where you can configure FPS, max width, color count, and whether to use two-pass palette generation.

The **spec panels** show input video details alongside the expected GIF output specs, updating live as you change quality or trim settings.

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
