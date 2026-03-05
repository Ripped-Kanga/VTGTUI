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

- **Drag & drop** a video file onto the terminal (supported terminals only)
- **Type or paste** a file path into the input field
- Select a **quality preset** and click **Convert**
- Press `Escape` to cancel an in-progress conversion
- Press `q` to quit

### Quality Presets

| Preset | FPS | Max Width | Colors | Notes |
|---|---|---|---|---|
| Low | 10 | 320px | 64 | Smallest file size |
| Medium | 15 | 480px | 128 | Balanced |
| High | 20 | Original | 256 | Two-pass palette generation |
| Uncompressed | Original | Original | 256 | Best quality, largest files |

### Supported Formats

`.mp4`, `.avi`, `.mkv`, `.mov`, `.webm`, `.wmv`, `.flv`, `.m4v`, `.mpeg`, `.mpg`, `.3gp`, `.ts`

## Dependencies

All dependencies are installed automatically via pip/pipx:

- [Textual](https://textual.textualize.io/) — TUI framework
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — Bundled ffmpeg binary (no system ffmpeg required)

## License

MIT
