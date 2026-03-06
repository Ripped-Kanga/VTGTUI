"""Timeline scrubber and frame preview widgets for video trimming."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.events import MouseDown, MouseMove, MouseUp
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from vtgtui.thumbnails import ThumbnailCache, render_halfblock


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
    """Displays a half-block rendered frame from the video at a given timestamp."""

    DEFAULT_CSS = """
    FramePreview {
        height: 1fr;
        min-height: 6;
    }
    """

    preview_time: reactive[float] = reactive(0.0)

    def __init__(self, id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.video_path: Optional[str] = None
        self._cache = ThumbnailCache(max_entries=20)
        self._rendered: Optional[Text] = None
        self._loading = False
        self._last_request_time: float = 0.0

    def render(self) -> Text:
        if self._loading:
            return Text("Loading preview...", style="dim italic")
        if self._rendered is not None:
            return self._rendered
        if self.video_path is None:
            return Text("No video loaded", style="dim")
        return Text("Hover scrubber or move handles to preview", style="dim")

    def update_preview(self, timestamp: float, video_path: str) -> None:
        """Request a preview update with debounce."""
        self.video_path = video_path
        self.preview_time = timestamp
        now = time.monotonic()
        self._last_request_time = now
        # Capture dimensions on the main thread where layout is valid
        w = self.size.width - 2 if self.size.width > 2 else 80  # subtract border
        h = self.size.height - 2 if self.size.height > 2 else 10  # subtract border
        self._extract_frame(timestamp, video_path, now, w, h)

    @work(thread=True)
    def _extract_frame(
        self, timestamp: float, video_path: str, request_time: float,
        widget_w: int = 80, widget_h: int = 10,
    ) -> None:
        """Extract and render a frame in a background thread."""
        # Debounce: skip if a newer request came in
        if request_time != self._last_request_time:
            return

        self._loading = True
        self.app.call_from_thread(self.refresh)

        try:
            # Fit frame to widget: max_height = rows * 2 (half-block)
            max_h = widget_h * 2
            rgb, w, h = self._cache.get(
                video_path, timestamp,
                max_width=widget_w, max_height=max_h,
            )
            self._rendered = render_halfblock(rgb, w, h)
        except Exception:
            self._rendered = Text("[No preview available]", style="dim italic")
        finally:
            self._loading = False
            self.app.call_from_thread(self.refresh)

    def clear_preview(self) -> None:
        """Clear the preview and cache."""
        self._rendered = None
        self._cache.clear()
        self.video_path = None
        self.refresh()
