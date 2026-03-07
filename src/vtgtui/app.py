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
    VideoInfo,
    convert_video_to_gif,
    get_video_info,
    is_supported_format,
)
from vtgtui.browse import browse_for_video
from vtgtui.scrubber import FramePreview, TimelineScrubber


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
        Binding("ctrl+b", "browse", "Browse", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._converting = False
        self._cancelled = False
        self._custom_preset: QualityPreset | None = None
        self._syncing_scrubber = False
        self._current_input_file: str | None = None
        self._video_info: VideoInfo | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main-container"):
            with Horizontal(classes="field-row"):
                yield Label("Input:", classes="field-label")
                yield Input(
                    placeholder="Path to video file...",
                    id="input-path",
                    classes="field-input",
                )
                yield Button("Browse", variant="primary", id="browse-btn", classes="browse-btn")

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

            with Horizontal(id="spec-panels"):
                yield Static("", id="input-specs")
                yield Static("", id="output-specs")

            yield Button("Convert", variant="primary", id="convert-btn")

            with Horizontal(id="progress-container"):
                yield ProgressBar(total=100, show_eta=False, id="progress-bar")
                yield Label("0%", id="progress-label")

            yield RichLog(highlight=True, markup=True, id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#progress-bar", ProgressBar).update(progress=0)
        self.log_message("[dim]Ready. Enter a path or browse to select a video file.[/]")
        formats = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        self.log_message(f"[dim]Supported formats: {formats}[/]")

    def _get_active_preset(self) -> QualityPreset:
        """Return the currently selected quality preset."""
        quality_value = self.query_one("#quality-select", Select).value
        if quality_value == "custom" and self._custom_preset is not None:
            return self._custom_preset
        return QUALITY_PRESETS.get(quality_value, QUALITY_PRESETS["high"])

    def _update_spec_panels(self) -> None:
        """Update the input and output spec panels."""
        input_panel = self.query_one("#input-specs", Static)
        output_panel = self.query_one("#output-specs", Static)

        if self._video_info is None:
            input_panel.update("[dim]No video selected[/]")
            output_panel.update("[dim]—[/]")
            return

        info = self._video_info
        mins, secs = divmod(info.duration, 60)
        input_panel.update(
            f"[bold]Input Video[/]\n"
            f"  {info.width}x{info.height} @ {info.fps:.1f} fps\n"
            f"  Duration: {int(mins)}m {secs:.1f}s"
        )

        preset = self._get_active_preset()
        out_fps = preset.fps if preset.fps is not None else min(info.fps, 50)
        if preset.max_width and info.width > preset.max_width:
            out_w = preset.max_width
            out_h = int(info.height * (preset.max_width / info.width))
        else:
            out_w = info.width
            out_h = info.height

        # Trim duration
        start_str = self.query_one("#trim-start", Input).value.strip()
        end_str = self.query_one("#trim-end", Input).value.strip()
        try:
            start = float(start_str) if start_str else 0.0
        except ValueError:
            start = 0.0
        try:
            end = float(end_str) if end_str else info.duration
        except ValueError:
            end = info.duration
        out_dur = max(end - start, 0.0)
        out_mins, out_secs = divmod(out_dur, 60)

        pass_str = "two-pass" if preset.two_pass else "single-pass"
        output_panel.update(
            f"[bold]Output GIF ({preset.name})[/]\n"
            f"  {out_w}x{out_h} @ {out_fps} fps, {preset.colors} colors\n"
            f"  Duration: {int(out_mins)}m {out_secs:.1f}s ({pass_str})"
        )

    def set_input_file(self, path: str) -> None:
        """Set the input file path and auto-generate output path."""
        resolved = str(Path(path).resolve())
        if self._current_input_file == resolved:
            return
        self._current_input_file = resolved

        input_widget = self.query_one("#input-path", Input)
        input_widget.value = path

        # Auto-generate output path
        p = Path(path)
        output = p.with_suffix(".gif")
        self.query_one("#output-path", Input).value = str(output)

        self.log_message(f"Selected: [bold]{p.name}[/]")

        # Probe video and show duration, pre-fill trim fields
        try:
            info = get_video_info(path)
            self._video_info = info
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

            self._update_spec_panels()
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
        self._update_spec_panels()

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
        self._update_spec_panels()

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
            self._update_spec_panels()

        if event.input.id == "input-path" and event.value:
            path = event.value.strip().strip("'\"")
            if os.path.isfile(path) and is_supported_format(path):
                self.set_input_file(path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "convert-btn":
            self.action_convert()
        elif event.button.id == "browse-btn":
            self.action_browse()

    def action_focus_input(self) -> None:
        self.query_one("#input-path", Input).focus()

    def action_browse(self) -> None:
        """Open the native file browser dialog in a background thread."""
        browse_btn = self.query_one("#browse-btn", Button)
        browse_btn.disabled = True
        self._do_browse()

    @work(thread=True)
    def _do_browse(self) -> None:
        path = browse_for_video()
        browse_btn = self.query_one("#browse-btn", Button)
        self.call_from_thread(browse_btn.__setattr__, "disabled", False)
        if path:
            self.call_from_thread(self.set_input_file, path)
        else:
            self.call_from_thread(self.log_message, "[dim]No file selected.[/]")

    @on(Select.Changed, "#quality-select")
    def on_quality_changed(self, event: Select.Changed) -> None:
        if event.value == "custom":
            self.query_one("#frame-preview", FramePreview).hide_kitty()
            self.push_screen(CustomQualityScreen(), self._on_custom_quality_result)
        else:
            self._update_spec_panels()

    def _on_custom_quality_result(self, preset: QualityPreset | None) -> None:
        select = self.query_one("#quality-select", Select)
        preview = self.query_one("#frame-preview", FramePreview)
        if preset is None:
            # User cancelled — revert to previous non-custom value
            select.value = "high"
            preview.restore_kitty()
            return
        self._custom_preset = preset
        desc = (
            f"Custom: {preset.fps or 'orig'}fps, "
            f"{'no limit' if preset.max_width is None else str(preset.max_width) + 'px'}, "
            f"{preset.colors} colors"
        )
        self.log_message(f"[bold]{desc}[/]")
        self._update_spec_panels()
        preview.restore_kitty()

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
