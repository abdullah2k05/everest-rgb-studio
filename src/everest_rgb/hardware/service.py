"""Background hardware service.

All HID traffic runs on one worker thread so the GUI never blocks. Jobs are
queued (and coalesced where sensible), connection state is tracked, and the
keyboard is reconnected and restored automatically when it reappears.
"""

from __future__ import annotations

import concurrent.futures
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..models.lighting import LightingState
from ..utils.config import Settings
from .everest60 import Everest60, Everest60Error

log = logging.getLogger(__name__)

_UNSET = object()


@dataclass
class ServiceSnapshot:
    connected: bool = False
    connecting: bool = False
    name: str = "Everest 60"
    path: str = ""
    interface: int = -1
    last_error: str = ""
    tx_count: int = 0
    rx_count: int = 0
    busy: bool = False
    message: str = ""

    @property
    def status_text(self) -> str:
        if self.connected:
            return f"● {self.name} Connected"
        if self.connecting:
            return f"◌ {self.name} Connecting…"
        if self.last_error:
            return f"○ {self.name} Disconnected"
        return f"○ {self.name} Disconnected"


@dataclass
class _Job:
    func: Callable[..., Any]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    key: str | None = None
    future: concurrent.futures.Future = field(default_factory=concurrent.futures.Future)


class HardwareService:
    """Serialises every hardware operation onto a single worker thread."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        debug: bool = False,
        controller: Everest60 | None = None,
    ):
        self.settings = settings or Settings()
        self._debug = debug
        self.controller = controller or Everest60(debug=debug)
        self.desired_state = LightingState()

        self._queue: "queue.Queue[_Job | None]" = queue.Queue()
        self._pending: dict[str, _Job] = {}
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._dirty_state = False
        self._dirty_frame: tuple | None = None
        self._last_connect_attempt = 0.0
        self._connect_failed = False

        self._snapshot = ServiceSnapshot()
        self._listeners: list[Callable[[ServiceSnapshot], None]] = []
        self._listener_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stopping.clear()
        self._thread = threading.Thread(
            target=self._run, name="everest-hw", daemon=True
        )
        self._thread.start()
        log.debug("hardware worker started")

    def stop(self, *, timeout: float = 3.0) -> None:
        if not self.running:
            return
        self._stopping.set()
        self._queue.put(None)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None
        try:
            self.controller.disconnect()
        except Exception:  # pragma: no cover
            pass
        log.debug("hardware worker stopped")

    # -- observation -------------------------------------------------------

    def snapshot(self) -> ServiceSnapshot:
        with self._lock:
            status = self.controller.status
            snap = ServiceSnapshot(
                connected=status.connected,
                connecting=(
                    not status.connected
                    and self.running
                    and not self._connect_failed
                    and (self.desired_state is not None)
                    and bool(self.settings.auto_reconnect)
                ),
                name=status.name or "Everest 60",
                path=status.path,
                interface=status.interface,
                last_error=status.last_error,
                tx_count=status.tx_count,
                rx_count=status.rx_count,
                busy=bool(self._pending) or not self._queue.empty(),
            )
            snap.message = self._message
            return snap

    @property
    def _message(self) -> str:
        if self._snapshot_message:
            return self._snapshot_message
        return ""

    _snapshot_message: str = ""

    def add_listener(self, callback: Callable[[ServiceSnapshot], None]) -> None:
        with self._listener_lock:
            self._listeners.append(callback)

    def _notify(self) -> None:
        snap = self.snapshot()
        with self._listener_lock:
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback(snap)
            except Exception:  # pragma: no cover - listener bugs must not kill worker
                log.exception("hardware listener failed")

    def set_message(self, message: str) -> None:
        self._snapshot_message = message

    # -- job submission ----------------------------------------------------

    def submit(
        self,
        func: Callable[..., Any],
        *args: Any,
        coalesce_key: str | None = None,
        **kwargs: Any,
    ) -> concurrent.futures.Future:
        """Queue a callable to run on the hardware thread."""
        job = _Job(func=func, args=args, kwargs=kwargs, key=coalesce_key)
        with self._lock:
            if coalesce_key:
                old = self._pending.pop(coalesce_key, None)
                if old is not None and not old.future.done():
                    old.future.set_result(None)
            self._pending[coalesce_key or f"{id(job)}"] = job
        self._queue.put(job)
        return job.future

    def connect_now(self) -> concurrent.futures.Future:
        return self.submit(self._connect, coalesce_key="connect")

    def apply_state(self, state: LightingState | None = None) -> concurrent.futures.Future:
        """Queue an apply of the desired lighting state (coalesced)."""
        if state is not None:
            with self._lock:
                self.desired_state = state
        with self._lock:
            self._dirty_state = True
        return self.submit(self._flush_state, coalesce_key="state")

    def push_frame(
        self,
        key_colors: list[tuple[int, int, int]],
        side_colors: list[tuple[int, int, int]] | None = None,
        brightness: int = 100,
    ) -> None:
        """Queue the newest animation frame (older frames are dropped)."""
        with self._lock:
            self._dirty_frame = (list(key_colors), side_colors, brightness)
            if self._pending.get("frame") is not None:
                return
            self._pending["frame"] = _Job(
                func=self._flush_frame, key="frame"
            )
            job = self._pending["frame"]
        self._queue.put(job)

    # -- worker ------------------------------------------------------------

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                job = self._queue.get(timeout=0.25)
            except queue.Empty:
                job = None

            if job is not None:
                self._run_job(job)
                continue

            self._maybe_reconnect()

    def _run_job(self, job: _Job) -> None:
        with self._lock:
            stored = self._pending.get(job.key or "")
            if stored is not job:
                # superseded by a newer coalesced job
                if not job.future.done():
                    job.future.set_result(None)
                return
            self._pending.pop(job.key or "", None)

        self._maybe_reconnect(pre_connect=False)
        if not self.controller.is_connected and job.key not in ("connect", "disconnect"):
            # Never run hardware work while unplugged.
            if not job.future.done():
                job.future.set_exception(
                    Everest60Error("Everest 60 is not connected")
                )
            self._notify()
            return

        try:
            result = job.func(*job.args, **job.kwargs)
        except BaseException as exc:  # noqa: BLE001 - surfaced through the future
            log.debug("job %s failed: %s", job.func.__name__, exc, exc_info=True)
            if not job.future.done():
                job.future.set_exception(exc)
        else:
            if not job.future.done():
                job.future.set_result(result)
        self._notify()

    def _maybe_reconnect(self, *, pre_connect: bool = True) -> None:
        if self._stopping.is_set():
            return
        if self.controller.is_connected:
            self._connect_failed = False
            return
        if not self.settings.auto_reconnect and not pre_connect:
            return
        now = time.monotonic()
        interval = max(1.0, float(self.settings.reconnect_interval_s))
        if now - self._last_connect_attempt < interval:
            return
        self._last_connect_attempt = now
        try:
            self._connect()
        except Everest60Error as exc:
            if not self._connect_failed:
                log.info("keyboard not available: %s", exc)
            self._connect_failed = True
            self._notify()

    def _connect(self) -> None:
        status = self.controller.connect()
        self._connect_failed = False
        log.info("connected: %s @ %s", status.name, status.path)
        if self.settings.remember_last_state and self.settings.restore_on_connect:
            with self._lock:
                self._dirty_state = True
            try:
                self._flush_state()
            except Everest60Error as exc:
                log.warning("could not restore state: %s", exc)
        self._notify()

    def _flush_state(self) -> None:
        with self._lock:
            if not self._dirty_state:
                return
            state = self.desired_state.copy()
            self._dirty_state = False
            self._dirty_frame = None
        self._apply(state)

    def _flush_frame(self) -> None:
        with self._lock:
            dirty = self._dirty_frame
            self._dirty_frame = None
            if dirty is None:
                return
            if self._dirty_state:
                # a full state apply is pending; frames can wait for it
                return
        key_colors, side_colors, brightness = dirty
        self.controller.apply_custom_map(
            key_colors, side_colors=side_colors, brightness=brightness
        )

    def _apply(self, state: LightingState) -> None:
        if state.mode == "hardware":
            if state.effect == "off":
                self.controller.set_off(brightness=state.brightness)
                return
            self.controller.set_effect(
                state.effect,
                speed=state.speed,
                brightness=state.brightness,
                color1=state.color1,
                color2=state.color2,
                color_mode=state.color_mode,
                direction=_direction_value(state.direction),
            )
            return

        keys: list = list(state.key_colors)
        side: list = list(state.side_colors)
        if state.mode == "software":
            keys, side = _render_frame(state)
        self.controller.apply_custom_map(
            keys, side_colors=side, brightness=state.brightness
        )

    # -- convenience for CLI ----------------------------------------------

    def run_sync(self, func: Callable[..., Any], *args: Any, timeout: float = 10.0, **kwargs: Any) -> Any:
        """Run something on the worker thread and block for the result."""
        if not self.running:
            # Allow synchronous use without the worker (CLI one-shots).
            self._maybe_connect_inline()
            return func(*args, **kwargs)
        return self.submit(func, *args, **kwargs).result(timeout=timeout)

    def _maybe_connect_inline(self) -> None:
        if not self.controller.is_connected:
            self.controller.connect()


def _direction_value(name: str) -> int:
    from . import protocol

    return protocol.DIRECTIONS.get(name, 0)


def _render_frame(state: LightingState):
    """Render one frame of a software effect (used for one-shot applies)."""
    import time as _time

    from ..effects.base import RenderContext
    from ..effects.standard import EFFECTS

    effect = EFFECTS.get(state.effect) or EFFECTS["static"]
    ctx = RenderContext(state=state.copy(), t=_time.monotonic(), dt=0.0)
    return effect.render(ctx)
