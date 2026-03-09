"""Timeline scrubber and frame preview widgets for video trimming."""

from __future__ import annotations

import time
from typing import Optional

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.events import MouseDown, MouseMove, MouseUp, Resize
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from vtgtui.kitty_graphics import detect_kitty_support, hide_image, show_image
from vtgtui.thumbnails import ThumbnailCache


class TimelineScrubber(Widget, can_focus=True):
    """Interactive timeline bar for selecting video start/end trim points.

    Renders as a 3-line widget:
      Line 0: Time labels (0.0s ... duration)
      Line 1: Bar with handles (░░░▓▓▓▓▓▓▓▓░░░)
      Line 2: Handle time labels (▲ start   ▲ end)
    """

    BINDINGS = [
        Binding("left", "nudge(-0.1)", "Nudge left", show=False),
        Binding("right", "nudge(0.1)", "Nudge right", show=False),
        Binding("shift+left", "nudge(-1.0)", "Nudge left 1s", show=False),
        Binding("shift+right", "nudge(1.0)", "Nudge right 1s", show=False),
        Binding("tab", "switch_handle", "Switch handle", show=False),
        Binding("home", "jump_start", "Jump to start", show=False),
        Binding("end", "jump_end", "Jump to end", show=False),
    ]

    duration: reactive[float] = reactive(0.0)
    start_time: reactive[float] = reactive(0.0)
    end_time: reactive[float] = reactive(0.0)
    cursor_time: reactive[float] = reactive(0.0)

    class StartChanged(Message):
        """Posted when the start handle is moved."""

        def __init__(self, value: float) -> None:
            super().__init__()
            self.value = value

    class EndChanged(Message):
        """Posted when the end handle is moved."""

        def __init__(self, value: float) -> None:
            super().__init__()
            self.value = value

    class CursorMoved(Message):
        """Posted when cursor/hover position changes."""

        def __init__(self, value: float) -> None:
            super().__init__()
            self.value = value

    def __init__(
        self,
        id: Optional[str] = None,
    ) -> None:
        super().__init__(id=id)
        self._dragging: Optional[str] = None  # "start", "end", or None
        self._active_handle: str = "start"  # which handle keyboard controls
        self.video_path: Optional[str] = None

    def _time_to_x(self, t: float, w: int | None = None) -> int:
        """Convert a time value to an x-coordinate within the widget."""
        if w is None:
            w = self.size.width
        if w <= 2 or self.duration <= 0:
            return 0
        return int((t / self.duration) * (w - 1))

    def _x_to_time(self, x: int) -> float:
        """Convert an x-coordinate to a time value."""
        w = self.size.width
        if w <= 1 or self.duration <= 0:
            return 0.0
        return max(0.0, min(self.duration, (x / (w - 1)) * self.duration))

    def render(self) -> Text:
        """Render the 3-line scrubber as a single Text object."""
        w = self.size.width
        if w < 4 or self.duration <= 0:
            return Text("No video loaded", style="dim")

        text = Text()

        # Line 0: time range labels
        start_label = self._fmt_time(0.0)
        end_label = self._fmt_time(self.duration)
        text.append(start_label, style="dim")
        gap = w - len(start_label) - len(end_label)
        if gap > 0:
            text.append(" " * gap)
        text.append(end_label, style="dim")
        text.append("\n")

        # Line 1: bar with handles
        start_x = self._time_to_x(self.start_time, w)
        end_x = self._time_to_x(self.end_time, w)
        focused = self.has_focus

        for x in range(w):
            if x == start_x:
                style = "bold green" if (focused and self._active_handle == "start") else "green"
                text.append("\u2590", style=style)
            elif x == end_x:
                style = "bold red" if (focused and self._active_handle == "end") else "red"
                text.append("\u258c", style=style)
            elif start_x < x < end_x:
                text.append("\u2593", style="green")
            else:
                text.append("\u2591", style="dim")
        text.append("\n")

        # Line 2: handle time labels
        start_lbl = f"\u25b2 {self._fmt_time(self.start_time)}"
        end_lbl = f"\u25b2 {self._fmt_time(self.end_time)}"
        buf = [" "] * w
        styles: dict[int, str] = {}

        for i, ch in enumerate(start_lbl):
            pos = start_x + i
            if 0 <= pos < w:
                buf[pos] = ch
                styles[pos] = "green"

        for i, ch in enumerate(end_lbl):
            pos = end_x + i
            if 0 <= pos < w:
                buf[pos] = ch
                styles[pos] = "red"

        for i, ch in enumerate(buf):
            text.append(ch, style=styles.get(i, "dim"))

        return text

    @staticmethod
    def _fmt_time(t: float) -> str:
        """Format time as compact string."""
        if t < 60:
            return f"{t:.1f}s"
        mins = int(t // 60)
        secs = t % 60
        return f"{mins}:{secs:04.1f}"

    def _on_mouse_down(self, event: MouseDown) -> None:
        """Start dragging a handle."""
        if self.duration <= 0:
            return
        start_x = self._time_to_x(self.start_time)
        end_x = self._time_to_x(self.end_time)
        x = event.x

        # Determine which handle is closer
        dist_start = abs(x - start_x)
        dist_end = abs(x - end_x)

        if dist_start <= 2 and dist_start <= dist_end:
            self._dragging = "start"
            self._active_handle = "start"
        elif dist_end <= 2:
            self._dragging = "end"
            self._active_handle = "end"
        else:
            # Click in empty area - move nearest handle
            if dist_start < dist_end:
                self._dragging = "start"
                self._active_handle = "start"
                self._move_handle("start", self._x_to_time(x))
            else:
                self._dragging = "end"
                self._active_handle = "end"
                self._move_handle("end", self._x_to_time(x))

        self.capture_mouse()
        self.focus()
        event.stop()

    def _on_mouse_move(self, event: MouseMove) -> None:
        """Update handle position while dragging."""
        if self._dragging and self.duration > 0:
            t = self._x_to_time(event.x)
            self._move_handle(self._dragging, t)
            self.cursor_time = t
            self.post_message(self.CursorMoved(t))
            event.stop()

    def _on_mouse_up(self, event: MouseUp) -> None:
        """Finish dragging."""
        if self._dragging:
            self.release_mouse()
            handle = self._dragging
            self._dragging = None
            if handle == "start":
                self.post_message(self.StartChanged(self.start_time))
            else:
                self.post_message(self.EndChanged(self.end_time))
            event.stop()

    def _move_handle(self, handle: str, t: float) -> None:
        """Move a handle to a new time, enforcing constraints."""
        t = max(0.0, min(self.duration, t))
        if handle == "start":
            t = min(t, self.end_time - 0.1)
            self.start_time = max(0.0, t)
        else:
            t = max(t, self.start_time + 0.1)
            self.end_time = min(self.duration, t)

    def action_nudge(self, delta: float) -> None:
        """Nudge the active handle by delta seconds."""
        delta = float(delta)
        if self._active_handle == "start":
            self._move_handle("start", self.start_time + delta)
            self.post_message(self.StartChanged(self.start_time))
        else:
            self._move_handle("end", self.end_time + delta)
            self.post_message(self.EndChanged(self.end_time))

    def action_switch_handle(self) -> None:
        """Switch between start and end handles."""
        self._active_handle = "end" if self._active_handle == "start" else "start"
        self.refresh()

    def action_jump_start(self) -> None:
        """Jump active handle to the beginning."""
        if self._active_handle == "start":
            self._move_handle("start", 0.0)
            self.post_message(self.StartChanged(self.start_time))
        else:
            self._move_handle("end", self.start_time + 0.1)
            self.post_message(self.EndChanged(self.end_time))

    def action_jump_end(self) -> None:
        """Jump active handle to the end."""
        if self._active_handle == "end":
            self._move_handle("end", self.duration)
            self.post_message(self.EndChanged(self.end_time))
        else:
            self._move_handle("start", self.end_time - 0.1)
            self.post_message(self.StartChanged(self.start_time))

    def watch_start_time(self) -> None:
        self.refresh()

    def watch_end_time(self) -> None:
        self.refresh()

    def watch_duration(self) -> None:
        self.refresh()


class FramePreview(Widget):
    """Displays a video frame preview using the Kitty graphics protocol.

    Only visible in terminals that support Kitty graphics (Kitty, Ghostty,
    WezTerm, Konsole).  The widget hides itself on unsupported terminals.
    """

    DEFAULT_CSS = """
    FramePreview {
        height: 1fr;
        min-height: 6;
    }
    """

    KITTY_IMAGE_ID = 42

    #: ``True`` when the running terminal supports Kitty graphics.
    supports_preview: bool = detect_kitty_support()

    preview_time: reactive[float] = reactive(0.0)

    def __init__(self, id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.video_path: Optional[str] = None
        self._cache = ThumbnailCache(max_entries=20)
        self._loading = False
        self._last_request_time: float = 0.0
        self._kitty_shown = False
        self._pending_png: Optional[bytes] = None
        self._last_kitty_png: Optional[bytes] = None

    def on_mount(self) -> None:
        """Hide the widget when Kitty graphics are not available."""
        if not self.supports_preview:
            self.display = False

    def render(self) -> Text:
        if self._loading:
            return Text("Loading preview...", style="dim italic")
        if self._kitty_shown:
            return Text("")
        if self.video_path is None:
            return Text("No video loaded", style="dim")
        return Text("Hover scrubber or move handles to preview", style="dim")

    def update_preview(self, timestamp: float, video_path: str) -> None:
        """Request a preview update.  No-op when Kitty is not supported."""
        if not self.supports_preview:
            return
        self.video_path = video_path
        self.preview_time = timestamp
        now = time.monotonic()
        self._last_request_time = now
        w = self.size.width - 2 if self.size.width > 2 else 80
        h = self.size.height - 2 if self.size.height > 2 else 10
        self._extract_frame(timestamp, video_path, now, w, h)

    @work(thread=True)
    def _extract_frame(
        self, timestamp: float, video_path: str, request_time: float,
        widget_w: int = 80, widget_h: int = 10,
    ) -> None:
        """Extract a PNG frame in a background thread."""
        if request_time != self._last_request_time:
            return

        self._loading = True
        self.app.call_from_thread(self.refresh)

        try:
            max_px_w = min(widget_w * 12, 1920)
            max_px_h = min(widget_h * 24, 1080)
            self._pending_png = self._cache.get_png(
                video_path, timestamp,
                max_width=max_px_w, max_height=max_px_h,
            )
        except Exception:
            self._kitty_shown = False
            self._pending_png = None
        finally:
            self._loading = False
            self.app.call_from_thread(self._finish_render)

    def _finish_render(self) -> None:
        """Called on main thread after frame extraction completes."""
        self.refresh()
        if self._pending_png:
            self.set_timer(0.05, self._display_kitty_image)

    def _aspect_fit(self, region_w: int, region_h: int) -> tuple[int, int, int, int]:
        """Calculate cols/rows that fit the image aspect ratio within the region.

        Terminal cells are ~2:1 (each cell is roughly twice as tall as wide in
        pixels), so 1 row ≈ 2 cols worth of vertical space.

        Returns (cols, rows, x_offset, y_offset) for centering.
        """
        if not self._pending_png and not self._last_kitty_png:
            return region_w, region_h, 0, 0

        png = self._pending_png or self._last_kitty_png
        # Parse image dimensions from PNG header (IHDR chunk at offset 16)
        img_w = int.from_bytes(png[16:20], "big")
        img_h = int.from_bytes(png[20:24], "big")

        if img_w <= 0 or img_h <= 0:
            return region_w, region_h, 0, 0

        # Image aspect ratio in cell units (each row ≈ 2 cols of height)
        cell_aspect = 2.0  # rows are ~2x taller than cols are wide
        img_aspect = img_w / img_h

        # Try fitting to full width
        cols = region_w
        rows = int(cols / img_aspect / cell_aspect + 0.5)

        if rows > region_h:
            # Too tall, fit to height instead
            rows = region_h
            cols = int(rows * img_aspect * cell_aspect + 0.5)

        cols = max(cols, 1)
        rows = max(rows, 1)

        # Center offsets
        x_off = (region_w - cols) // 2
        y_off = (region_h - rows) // 2

        return cols, rows, x_off, y_off

    def _display_kitty_image(self) -> None:
        """Display the pending Kitty protocol image after Textual has rendered."""
        if not self._pending_png:
            return
        region = self.content_region
        cols, rows, x_off, y_off = self._aspect_fit(region.width, region.height)
        show_image(
            self._pending_png,
            x=region.x + x_off, y=region.y + y_off,
            cols=cols, rows=rows,
            image_id=self.KITTY_IMAGE_ID,
        )
        self._last_kitty_png = self._pending_png
        self._kitty_shown = True
        self._pending_png = None

    def clear_preview(self) -> None:
        """Clear the preview and cache."""
        if self._kitty_shown:
            hide_image(self.KITTY_IMAGE_ID)
            self._kitty_shown = False
        self._pending_png = None
        self._cache.clear()
        self.video_path = None
        self.refresh()

    def on_resize(self, event: Resize) -> None:
        """Redraw kitty image at new position/size when the widget resizes."""
        if self._kitty_shown and self._last_kitty_png:
            hide_image(self.KITTY_IMAGE_ID)
            self.set_timer(0.05, self._display_kitty_redraw)

    def hide_kitty(self) -> None:
        """Temporarily hide the kitty image (e.g. when a modal opens)."""
        if self._kitty_shown:
            hide_image(self.KITTY_IMAGE_ID)

    def restore_kitty(self) -> None:
        """Re-display the kitty image after it was temporarily hidden."""
        if self._kitty_shown and self._last_kitty_png:
            self.set_timer(0.05, self._display_kitty_redraw)

    def _display_kitty_redraw(self) -> None:
        """Redraw the last kitty image."""
        if not self._last_kitty_png:
            return
        region = self.content_region
        cols, rows, x_off, y_off = self._aspect_fit(region.width, region.height)
        show_image(
            self._last_kitty_png,
            x=region.x + x_off, y=region.y + y_off,
            cols=cols, rows=rows,
            image_id=self.KITTY_IMAGE_ID,
        )
