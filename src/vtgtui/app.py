"""VTGTUI - Video to GIF TUI Application."""

from __future__ import annotations

import os
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
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
    QualityPreset,
    SUPPORTED_EXTENSIONS,
    convert_video_to_gif,
    get_video_info,
    is_supported_format,
)
from vtgtui.scrubber import FramePreview, TimelineScrubber


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


class CustomQualityScreen(ModalScreen[QualityPreset | None]):
    """Modal screen for configuring custom quality settings."""

    CSS = """
    CustomQualityScreen {
        align: center middle;
    }
    #custom-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #custom-dialog .field-row {
        height: 3;
        margin-bottom: 1;
        layout: horizontal;
    }
    #custom-dialog .field-label {
        width: 16;
        height: 3;
        content-align: left middle;
        text-align: left;
        padding: 0 1 0 0;
    }
    #custom-dialog .field-input {
        width: 1fr;
    }
    #custom-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        width: 100%;
    }
    #custom-buttons {
        height: 3;
        margin-top: 1;
        layout: horizontal;
        align: center middle;
    }
    #custom-buttons Button {
        margin: 0 1;
    }
    #two-pass-row {
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="custom-dialog"):
            yield Label("Custom Quality Settings", id="custom-title")

            with Horizontal(classes="field-row"):
                yield Label("FPS:", classes="field-label")
                yield Input(value="20", id="custom-fps", classes="field-input")

            with Horizontal(classes="field-row"):
                yield Label("Max Width:", classes="field-label")
                yield Input(
                    placeholder="No limit",
                    id="custom-max-width",
                    classes="field-input",
                )

            with Horizontal(classes="field-row"):
                yield Label("Colors (2-256):", classes="field-label")
                yield Input(value="256", id="custom-colors", classes="field-input")

            yield Checkbox("Two-pass (better quality, slower)", value=True, id="custom-two-pass")

            with Horizontal(id="custom-buttons"):
                yield Button("Apply", variant="primary", id="custom-apply")
                yield Button("Cancel", variant="default", id="custom-cancel")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "custom-cancel":
            self.dismiss(None)
            return

        if event.button.id == "custom-apply":
            # Validate and build preset
            try:
                fps_str = self.query_one("#custom-fps", Input).value.strip()
                fps = int(fps_str) if fps_str else None
                if fps is not None and fps < 1:
                    raise ValueError("FPS must be at least 1")
            except ValueError as e:
                self.notify(f"Invalid FPS: {e}", severity="error")
                return

            try:
                width_str = self.query_one("#custom-max-width", Input).value.strip()
                max_width = int(width_str) if width_str else None
                if max_width is not None and max_width < 1:
                    raise ValueError("Width must be at least 1")
            except ValueError as e:
                self.notify(f"Invalid max width: {e}", severity="error")
                return

            try:
                colors_str = self.query_one("#custom-colors", Input).value.strip()
                colors = int(colors_str) if colors_str else 256
                if colors < 2 or colors > 256:
                    raise ValueError("Must be between 2 and 256")
            except ValueError as e:
                self.notify(f"Invalid colors: {e}", severity="error")
                return

            two_pass = self.query_one("#custom-two-pass", Checkbox).value

            preset = QualityPreset(
                name="Custom",
                fps=fps,
                max_width=max_width,
                colors=colors,
                two_pass=two_pass,
            )
            self.dismiss(preset)


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
        self._custom_preset: QualityPreset | None = None
        self._syncing_scrubber = False

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

            yield TimelineScrubber(id="scrubber")
            yield FramePreview(id="frame-preview")

            with Horizontal(id="quality-row"):
                yield Label("Quality:", id="quality-label")
                yield Select(
                    [(p.name, key) for key, p in QUALITY_PRESETS.items()]
                    + [("Custom", "custom")],
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

            # Update scrubber
            scrubber = self.query_one("#scrubber", TimelineScrubber)
            scrubber.video_path = path
            scrubber.duration = info.duration
            scrubber.start_time = 0.0
            scrubber.end_time = info.duration

            # Set video path on frame preview
            preview = self.query_one("#frame-preview", FramePreview)
            preview.video_path = path
            preview.update_preview(0.0, path)
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "input-path" and event.value:
            path = event.value.strip().strip("'\"")
            if os.path.isfile(path):
                self.set_input_file(path)
            else:
                self.log_message(f"[red]File not found:[/] {path}")

    @on(TimelineScrubber.StartChanged)
    def _on_scrubber_start_changed(self, event: TimelineScrubber.StartChanged) -> None:
        if self._syncing_scrubber:
            return
        self._syncing_scrubber = True
        self.query_one("#trim-start", Input).value = f"{event.value:.1f}"
        self._syncing_scrubber = False
        # Update frame preview at start handle position
        scrubber = self.query_one("#scrubber", TimelineScrubber)
        if scrubber.video_path:
            self.query_one("#frame-preview", FramePreview).update_preview(
                event.value, scrubber.video_path
            )

    @on(TimelineScrubber.EndChanged)
    def _on_scrubber_end_changed(self, event: TimelineScrubber.EndChanged) -> None:
        if self._syncing_scrubber:
            return
        self._syncing_scrubber = True
        self.query_one("#trim-end", Input).value = f"{event.value:.1f}"
        self._syncing_scrubber = False
        # Update frame preview at end handle position
        scrubber = self.query_one("#scrubber", TimelineScrubber)
        if scrubber.video_path:
            self.query_one("#frame-preview", FramePreview).update_preview(
                event.value, scrubber.video_path
            )

    @on(TimelineScrubber.CursorMoved)
    def _on_scrubber_cursor_moved(self, event: TimelineScrubber.CursorMoved) -> None:
        scrubber = self.query_one("#scrubber", TimelineScrubber)
        if scrubber.video_path:
            self.query_one("#frame-preview", FramePreview).update_preview(
                event.value, scrubber.video_path
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._syncing_scrubber:
            return

        # Sync trim inputs to scrubber
        if event.input.id in ("trim-start", "trim-end"):
            scrubber = self.query_one("#scrubber", TimelineScrubber)
            if scrubber.duration > 0:
                try:
                    val = float(event.value) if event.value.strip() else None
                except ValueError:
                    val = None
                if val is not None:
                    self._syncing_scrubber = True
                    if event.input.id == "trim-start":
                        scrubber.start_time = max(0.0, min(val, scrubber.end_time - 0.1))
                    else:
                        scrubber.end_time = max(scrubber.start_time + 0.1, min(val, scrubber.duration))
                    self._syncing_scrubber = False

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

    @on(Select.Changed, "#quality-select")
    def on_quality_changed(self, event: Select.Changed) -> None:
        if event.value == "custom":
            self.push_screen(CustomQualityScreen(), self._on_custom_quality_result)

    def _on_custom_quality_result(self, preset: QualityPreset | None) -> None:
        select = self.query_one("#quality-select", Select)
        if preset is None:
            # User cancelled — revert to previous non-custom value
            select.value = "high"
            return
        self._custom_preset = preset
        desc = (
            f"Custom: {preset.fps or 'orig'}fps, "
            f"{'no limit' if preset.max_width is None else str(preset.max_width) + 'px'}, "
            f"{preset.colors} colors"
        )
        self.log_message(f"[bold]{desc}[/]")

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

        quality_value = self.query_one("#quality-select", Select).value

        if quality_value == "custom" and self._custom_preset is None:
            self.log_message("[red]No custom preset configured. Select Custom again to configure.[/]")
            return

        quality = self._custom_preset if quality_value == "custom" else quality_value

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
        quality: str | QualityPreset,
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

        preset_name = quality.name if isinstance(quality, QualityPreset) else QUALITY_PRESETS[quality].name
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
