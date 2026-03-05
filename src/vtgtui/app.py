"""VTGTUI - Video to GIF TUI Application."""

from __future__ import annotations

import os
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Static,
)

from vtgtui.converter import (
    QUALITY_PRESETS,
    SUPPORTED_EXTENSIONS,
    convert_video_to_gif,
    get_video_info,
    is_supported_format,
)


def _parse_dropped_paths(text: str) -> list[str]:
    """Extract file paths from pasted/dropped text.

    Terminals emit file drag-and-drop as paste events. Paths may be:
    - Single path on one line
    - Multiple paths separated by newlines
    - Quoted paths (single or double quotes)
    - file:// URIs
    """
    paths = []
    for line in text.strip().splitlines():
        line = line.strip().strip("'\"")
        # Handle file:// URIs
        if line.startswith("file://"):
            line = line[7:]
        if line and os.path.exists(line):
            paths.append(line)
    return paths


class DropZone(Static):
    """A zone that accepts drag-and-dropped files via terminal paste events."""

    def __init__(self) -> None:
        super().__init__(
            "Drag & drop a video file here\nor enter the path below",
            id="drop-zone",
        )

    def _on_paste(self, event) -> None:
        """Handle paste events (file drag-and-drop in supported terminals)."""
        paths = _parse_dropped_paths(event.text)
        video_paths = [p for p in paths if is_supported_format(p)]
        if video_paths:
            self.app.set_input_file(video_paths[0])
        elif paths:
            self.app.log_message(f"[red]Unsupported format:[/] {Path(paths[0]).suffix}")
        event.stop()


class VTGApp(App):
    """Video to GIF TUI Application."""

    TITLE = "VTGTUI - Video to GIF"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+o", "focus_input", "Open", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._converting = False
        self._cancelled = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            yield DropZone()

            with Horizontal(classes="field-row"):
                yield Label("Input:", classes="field-label")
                yield Input(
                    placeholder="Path to video file...",
                    id="input-path",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Output:", classes="field-label")
                yield Input(
                    placeholder="Output GIF path (auto-generated if empty)",
                    id="output-path",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Start:", classes="field-label")
                yield Input(
                    placeholder="Start time in seconds (e.g. 0.0)",
                    id="trim-start",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("End:", classes="field-label")
                yield Input(
                    placeholder="End time in seconds (leave empty for full)",
                    id="trim-end",
                    classes="field-input",
                )

            with Horizontal(id="quality-row"):
                yield Label("Quality:", id="quality-label")
                yield Select(
                    [(p.name, key) for key, p in QUALITY_PRESETS.items()],
                    value="high",
                    id="quality-select",
                    allow_blank=False,
                )

            yield Button("Convert", variant="primary", id="convert-btn")

            with Horizontal(id="progress-container"):
                yield ProgressBar(total=100, show_eta=False, id="progress-bar")
                yield Label("0%", id="progress-label")

            yield RichLog(highlight=True, markup=True, id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#progress-bar", ProgressBar).update(progress=0)
        self.log_message("[dim]Ready. Drop a video file or enter a path to begin.[/]")
        formats = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        self.log_message(f"[dim]Supported formats: {formats}[/]")

    def set_input_file(self, path: str) -> None:
        """Set the input file path and auto-generate output path."""
        input_widget = self.query_one("#input-path", Input)
        input_widget.value = path

        # Auto-generate output path
        p = Path(path)
        output = p.with_suffix(".gif")
        self.query_one("#output-path", Input).value = str(output)

        # Update drop zone
        drop_zone = self.query_one("#drop-zone", DropZone)
        drop_zone.update(f"[green]{p.name}[/]")
        drop_zone.add_class("has-file")

        self.log_message(f"Selected: [bold]{p.name}[/]")

        # Probe video and show duration, pre-fill trim fields
        try:
            info = get_video_info(path)
            mins, secs = divmod(info.duration, 60)
            self.log_message(
                f"  Duration: {int(mins)}m {secs:.1f}s | "
                f"{info.width}x{info.height} @ {info.fps:.1f} fps"
            )
            self.query_one("#trim-start", Input).value = "0"
            self.query_one("#trim-end", Input).value = f"{info.duration:.1f}"
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-path" and event.value:
            path = event.value.strip().strip("'\"")
            if os.path.isfile(path):
                self.set_input_file(path)
            else:
                self.log_message(f"[red]File not found:[/] {path}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "input-path" and event.value:
            path = event.value.strip().strip("'\"")
            if os.path.isfile(path) and is_supported_format(path):
                p = Path(path)
                output = p.with_suffix(".gif")
                output_input = self.query_one("#output-path", Input)
                if not output_input.value:
                    output_input.value = str(output)

    def _on_paste(self, event) -> None:
        """Handle paste at the app level as fallback."""
        paths = _parse_dropped_paths(event.text)
        video_paths = [p for p in paths if is_supported_format(p)]
        if video_paths:
            self.set_input_file(video_paths[0])
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "convert-btn":
            self.action_convert()

    def action_focus_input(self) -> None:
        self.query_one("#input-path", Input).focus()

    def action_cancel(self) -> None:
        if self._converting:
            self._cancelled = True
            self.log_message("[yellow]Cancelling conversion...[/]")

    def action_convert(self) -> None:
        if self._converting:
            self.log_message("[yellow]Conversion already in progress.[/]")
            return

        input_path = self.query_one("#input-path", Input).value.strip().strip("'\"")
        if not input_path:
            self.log_message("[red]No input file specified.[/]")
            return

        if not os.path.isfile(input_path):
            self.log_message(f"[red]File not found:[/] {input_path}")
            return

        if not is_supported_format(input_path):
            self.log_message(f"[red]Unsupported format:[/] {Path(input_path).suffix}")
            return

        output_path = self.query_one("#output-path", Input).value.strip()
        if not output_path:
            output_path = str(Path(input_path).with_suffix(".gif"))
            self.query_one("#output-path", Input).value = output_path

        quality = self.query_one("#quality-select", Select).value

        # Parse trim values
        start_time = None
        end_time = None
        start_str = self.query_one("#trim-start", Input).value.strip()
        end_str = self.query_one("#trim-end", Input).value.strip()
        try:
            if start_str:
                start_time = float(start_str)
        except ValueError:
            self.log_message("[red]Invalid start time. Use seconds (e.g. 1.5)[/]")
            return
        try:
            if end_str:
                end_time = float(end_str)
        except ValueError:
            self.log_message("[red]Invalid end time. Use seconds (e.g. 10.0)[/]")
            return

        if start_time is not None and end_time is not None and start_time >= end_time:
            self.log_message("[red]Start time must be less than end time.[/]")
            return

        self._run_conversion(input_path, output_path, quality, start_time, end_time)

    @work(thread=True)
    def _run_conversion(
        self,
        input_path: str,
        output_path: str,
        quality: str,
        start_time: float | None = None,
        end_time: float | None = None,
    ) -> None:
        """Run the conversion in a background thread."""
        self._converting = True
        self._cancelled = False

        btn = self.query_one("#convert-btn", Button)
        self.call_from_thread(btn.__setattr__, "disabled", True)
        self.call_from_thread(btn.__setattr__, "label", "Converting...")

        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_label = self.query_one("#progress-label", Label)
        self.call_from_thread(progress_bar.update, progress=0)
        self.call_from_thread(progress_label.update, "0%")

        preset_name = QUALITY_PRESETS[quality].name
        trim_info = ""
        if start_time is not None and start_time > 0:
            trim_info += f" from {start_time:.1f}s"
        if end_time is not None and end_time > 0:
            trim_info += f" to {end_time:.1f}s"
        self.call_from_thread(
            self.log_message,
            f"Converting with [bold]{preset_name}[/] quality{trim_info}...",
        )

        def on_progress(pct: float) -> None:
            clamped = min(int(pct), 100)
            self.call_from_thread(progress_bar.update, progress=clamped)
            self.call_from_thread(progress_label.update, f"{clamped}%")

        def check_cancel() -> bool:
            return self._cancelled

        try:
            convert_video_to_gif(
                input_path=input_path,
                output_path=output_path,
                quality=quality,
                start_time=start_time,
                end_time=end_time,
                progress_callback=on_progress,
                cancel_check=check_cancel,
            )

            if self._cancelled:
                self.call_from_thread(self.log_message, "[yellow]Conversion cancelled.[/]")
                # Clean up partial output
                if os.path.exists(output_path):
                    os.unlink(output_path)
            else:
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                self.call_from_thread(
                    self.log_message,
                    f"[green]Done![/] Saved to [bold]{output_path}[/] ({size_mb:.1f} MB)",
                )
                on_progress(100)

        except Exception as e:
            self.call_from_thread(
                self.log_message,
                f"[red]Error:[/] {e}",
            )
        finally:
            self._converting = False
            self._cancelled = False
            self.call_from_thread(btn.__setattr__, "disabled", False)
            self.call_from_thread(btn.__setattr__, "label", "Convert")

    def log_message(self, message: str) -> None:
        log = self.query_one("#log", RichLog)
        log.write(message)
