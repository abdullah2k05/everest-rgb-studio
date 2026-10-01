"""Software effect engine.

Renders animation frames off the GUI thread and hands them to a callback
(which queues them for the hardware). Frames that did not change are not
emitted, so a static per-key map is written to the keyboard exactly once.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from ..models.lighting import LightingState
from .base import Effect, RenderContext, RGB
from .standard import EFFECTS

log = logging.getLogger(__name__)

FrameCallback = Callable[[list[RGB], list[RGB], int], None]


def get_effect(name: str) -> Effect | None:
    return EFFECTS.get(name)


def effect_names() -> list[str]:
    return list(EFFECTS)


class EffectEngine:
    """Own render thread: state in, frames out."""

    def __init__(
        self,
        on_frame: FrameCallback,
        *,
        fps: int = 25,
        state: LightingState | None = None,
    ):
        self._on_frame = on_frame
        self._fps = max(5, min(60, int(fps)))
        self._state = state.copy() if state else LightingState()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._wake = threading.Event()
        self._pressed: set[int] = set()
        self._last_frame: tuple[tuple[RGB, ...], tuple[RGB, ...]] | None = None
        self.frames_rendered = 0
        self.frames_sent = 0

    # -- control -----------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def fps(self) -> int:
        return self._fps

    @fps.setter
    def fps(self, value: int) -> None:
        self._fps = max(5, min(60, int(value)))

    def set_state(self, state: LightingState) -> None:
        with self._lock:
            self._state = state.copy()

    def set_pressed(self, indices: list[int]) -> None:
        with self._lock:
            self._pressed = set(indices)

    def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="everest-fx", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        if not self.running:
            return
        self._stopping.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def invalidate(self) -> None:
        """Force the next frame to be emitted even if unchanged."""
        self._last_frame = None

    # -- rendering ---------------------------------------------------------

    def render_once(self, state: LightingState | None = None) -> tuple[list[RGB], list[RGB]]:
        """Render a single frame synchronously (used on apply / restore)."""
        with self._lock:
            ctx = RenderContext(
                state=(state or self._state).copy(),
                t=time.monotonic(),
                dt=0.0,
                pressed=tuple(self._pressed),
            )
        effect = EFFECTS.get(ctx.state.effect) or EFFECTS["static"]
        return effect.render(ctx)

    def _run(self) -> None:
        interval = 1.0 / self._fps
        last = time.monotonic()
        log.debug("effect engine started at %d fps", self._fps)
        while not self._stopping.is_set():
            started = time.monotonic()
            with self._lock:
                state = self._state.copy()
                pressed = tuple(self._pressed)

            ctx = RenderContext(
                state=state,
                t=started,
                dt=min(0.25, started - last),
                pressed=pressed,
            )
            last = started
            effect = EFFECTS.get(state.effect) or EFFECTS["static"]
            try:
                keys, side = effect.render(ctx)
            except Exception:  # pragma: no cover - effect bugs must not kill the thread
                log.exception("effect %s crashed", state.effect)
                keys, side = list(state.key_colors), list(state.side_colors)

            self.frames_rendered += 1
            signature = (tuple(keys), tuple(side))
            if signature != self._last_frame or not effect.editable:
                self._last_frame = signature
                try:
                    self._on_frame(keys, side, state.brightness)
                except Exception:
                    log.exception("frame callback failed")
                self.frames_sent += 1

            elapsed = time.monotonic() - started
            self._wake.wait(timeout=max(0.0, interval - elapsed))
            self._wake.clear()
