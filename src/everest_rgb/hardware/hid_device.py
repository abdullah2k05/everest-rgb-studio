"""HID transport: thin, defensive wrapper around python-hidapi.

Owns exactly one open device. All raw feature report I/O happens here so the
protocol layer can be tested without hardware.
"""

from __future__ import annotations

import errno
import logging
import os
import time

from . import protocol

log = logging.getLogger(__name__)

try:
    import hid
except Exception:  # pragma: no cover
    hid = None  # type: ignore[assignment]


class TransportError(RuntimeError):
    """Base class for HID transport failures."""


class PermissionDenied(TransportError):
    """The user is not allowed to open the device (missing udev rule)."""


class DeviceDisconnected(TransportError):
    """The device disappeared while (or before) it was opened."""


class DeviceBusy(TransportError):
    """The device is open elsewhere or temporarily refused the request."""


class ReportFailed(TransportError):
    """The device rejected a report or returned an unexpected echo."""


class TransientError(TransportError):
    """Temporary I/O hiccup (queue overrun, interrupted read) - retry, do not
    treat as a disconnect."""


_ERRNO_MAP = {
    errno.EACCES: PermissionDenied,
    errno.EPERM: PermissionDenied,
    errno.ENODEV: DeviceDisconnected,
    errno.ENOENT: DeviceDisconnected,
    errno.ENXIO: DeviceDisconnected,
    errno.EBUSY: DeviceBusy,
    errno.EIO: DeviceDisconnected,
    errno.EAGAIN: TransientError,
    errno.EWOULDBLOCK: TransientError,
    errno.EINTR: TransientError,
}

_TRANSIENT_MARKERS = (
    "read error",
    "write error",
    "resource temporarily unavailable",
    "try again",
    "interrupted",
)


def _translate(exc: BaseException, path: str) -> TransportError:
    if isinstance(exc, TransportError):
        return exc
    code = getattr(exc, "errno", None)
    cls = _ERRNO_MAP.get(code)
    if cls is not None:
        if cls is PermissionDenied:
            return PermissionDenied(
                f"permission denied opening {path} - install the udev rule "
                f"(see README) or check group membership"
            )
        if cls is DeviceBusy:
            return DeviceBusy(f"{path} is busy: {exc}")
        if cls is TransientError:
            return TransientError(f"{path}: {exc}")
        return DeviceDisconnected(f"{path} disconnected: {exc}")
    if isinstance(exc, OSError):
        # hidapi reports ENODEV-ish failures as plain OSError strings too.
        message = str(exc)
        if "No such device" in message or "Disconnected" in message:
            return DeviceDisconnected(f"{path}: {message}")
        if "Permission" in message or "denied" in message:
            return PermissionDenied(f"{path}: {message}")
        if any(marker in message.lower() for marker in _TRANSIENT_MARKERS):
            return TransientError(f"{path}: {message}")
    return TransportError(f"{path}: {exc}")


class HidTransport:
    """Single open HID device with validated feature report I/O."""

    #: Minimum observed gap that lets colour payloads through. The firmware
    #: needs wall-clock time after a feature report even though the echo comes
    #: back: back-to-back writes are ACKed and then dropped, while 10 ms gaps
    #: apply every time. 20 ms leaves margin for a slower firmware build.
    DEFAULT_INTER_PACKET_DELAY = 0.020

    #: Quiet period after ``0x03`` before the next command. The reset blanks the
    #: LEDs and the firmware restarts its lighting task: 20 ms is still too soon
    #: (the following packets are acknowledged and then dropped, leaving the
    #: board dark), 60 ms and longer apply reliably. 200 ms is the value the
    #: working capture used.
    DEFAULT_RESET_SETTLE = 0.200

    def __init__(
        self,
        path: bytes | str,
        *,
        report_size: int = protocol.REPORT_SIZE,
        inter_packet_delay: float | None = None,
        reset_settle: float | None = None,
        debug: bool = False,
        logger: logging.Logger | None = None,
    ):
        self._path_bytes = path if isinstance(path, bytes) else path.encode()
        self._path_str = self._path_bytes.decode(errors="replace")
        self._report_size = report_size
        self._inter_packet_delay = (
            self.DEFAULT_INTER_PACKET_DELAY if inter_packet_delay is None else inter_packet_delay
        )
        self._reset_settle = self.DEFAULT_RESET_SETTLE if reset_settle is None else reset_settle
        self._debug = debug
        self._log = logger or log
        self._device = None
        self._closed = False
        self._consecutive_transient = 0
        self._handshake_done = False
        self.tx_count = 0
        self.rx_count = 0

    # -- lifecycle ---------------------------------------------------------

    @property
    def path(self) -> str:
        return self._path_str

    @property
    def is_open(self) -> bool:
        return self._device is not None and not self._closed

    def open(self) -> None:
        if hid is None:
            raise TransportError("python-hidapi is not installed (pacman: python-hidapi)")
        if self._device is not None:
            return
        try:
            device = hid.device()
            device.open_path(self._path_bytes)
        except BaseException as exc:
            raise _translate(exc, self._path_str) from exc
        self._device = device
        self._closed = False
        self._handshake_done = False
        self._log.debug("opened %s", self._path_str)

    def _ensure_handshake(self) -> None:
        """Reset the lighting state machine before the first colour traffic.

        Without this the firmware ACKs ``0x17``/``0x35`` but drops the colour
        payload, so effects switch while the requested colour never appears -
        the exact failure this transport exists to prevent.

        Deferred until the first command rather than sent from ``open()``:
        ``0x03`` blanks the LEDs, so merely connecting (``status``, a probe)
        must not turn the keyboard dark. One handshake per open matches the
        OpenRGB controller.
        """
        if self._handshake_done:
            return
        self._handshake_done = True
        self._log.debug("sending reset handshake")
        try:
            self.exchange(protocol.build_reset(), expected_cmd=protocol.CMD_RESET)
            if self._reset_settle > 0:
                time.sleep(self._reset_settle)
        except ReportFailed as exc:
            self._handshake_done = False
            raise ReportFailed(
                f"{self._path_str}: reset handshake (0x03) not acknowledged - "
                f"the keyboard will ignore colour changes: {exc}"
            ) from exc
        except BaseException:
            self._handshake_done = False
            raise

    def close(self) -> None:
        self._closed = True
        self._handshake_done = False
        device, self._device = self._device, None
        if device is not None:
            try:
                device.close()
            except Exception as exc:  # pragma: no cover
                self._log.debug("close(%s) failed: %s", self._path_str, exc)

    def __enter__(self) -> "HidTransport":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- I/O ---------------------------------------------------------------

    def _ensure_alive(self) -> None:
        """Fail fast when the hidraw node vanished (unplug / re-enumeration).

        A stale fd can otherwise keep 'succeeding' or failing as a transient
        I/O hiccup forever, leaving the UI connected to nothing.
        """
        if not os.path.exists(self._path_str):
            raise DeviceDisconnected(
                f"{self._path_str} no longer exists (device removed or re-enumerated)"
            )

    def send_feature_report(self, packet: bytes, expected_cmd: int | None = None) -> bytes:
        """Validate and send one 65 byte feature report, then read the echo."""
        if not self.is_open:
            raise DeviceDisconnected(f"{self._path_str} is not open")
        self._ensure_alive()
        protocol.validate_packet(packet, expected_cmd)

        if self._debug:
            self._log.debug("TX %s", packet.hex(" "))

        try:
            written = self._device.send_feature_report(packet)
        except BaseException as exc:
            raise _translate(exc, self._path_str) from exc

        self.tx_count += 1
        if written == -1:
            # hidapi reports write failures as a bare -1 (no exception).
            raise TransientError(f"{self._path_str}: feature report write failed")
        if written not in (None,) and written != len(packet):
            raise ReportFailed(
                f"short write for command {packet[1]:#04x}: {written}/{len(packet)} bytes"
            )
        if self._debug:
            self._log.debug("write returned %s", written)
        return packet

    def read_feature_report(self, size: int | None = None) -> bytes:
        if not self.is_open:
            raise DeviceDisconnected(f"{self._path_str} is not open")
        self._ensure_alive()
        size = size or self._report_size
        try:
            response = self._device.get_feature_report(protocol.REPORT_ID, size)
        except BaseException as exc:
            raise _translate(exc, self._path_str) from exc
        self.rx_count += 1
        response = bytes(response)
        if self._debug:
            self._log.debug("RX %s", response.hex(" "))
        return response

    def _pace(self) -> None:
        """Give the firmware time to finish with the packet just written."""
        if self._inter_packet_delay > 0:
            time.sleep(self._inter_packet_delay)

    def exchange(
        self,
        packet: bytes,
        *,
        expected_cmd: int,
        retries: int = 3,
        retry_delay: float = 0.005,
        verify_echo: bool = True,
    ) -> bytes | None:
        """Send a packet and wait for the command echo, retrying on mismatch.

        The keyboard echoes the command byte at response[1]. Round trips are
        fast (~0.4 ms measured), but the firmware still needs wall-clock time
        before the next packet: back-to-back writes are echoed and then
        discarded, which is why every exchange is followed by
        ``inter_packet_delay``. ``0x03`` is also sent automatically before the
        first packet of a session.
        """
        self._ensure_handshake()
        response: bytes | None = None
        last_error: TransportError | None = None
        # Transient I/O hiccups (hidapi "read error" under load) get extra
        # attempts with backoff; real disconnects abort immediately.
        attempts = max(retries, 6)
        for attempt in range(attempts):
            try:
                self.send_feature_report(packet, expected_cmd)
            except TransportError as exc:
                last_error = exc
                if isinstance(exc, (DeviceDisconnected, PermissionDenied)):
                    raise
                if isinstance(exc, TransientError) and attempt + 1 < attempts:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                if attempt + 1 < retries:
                    time.sleep(retry_delay)
                    continue
                break
            if not verify_echo:
                self._consecutive_transient = 0
                self._pace()
                return None
            try:
                response = self.read_feature_report()
            except TransportError as exc:
                last_error = exc
                if isinstance(exc, (DeviceDisconnected, PermissionDenied)):
                    raise
                if attempt + 1 < attempts:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                break
            if len(response) >= 2 and response[1] == expected_cmd:
                self._consecutive_transient = 0
                self._pace()
                return response
            self._log.debug(
                "echo mismatch (attempt %d): got cmd %s, want %s",
                attempt + 1,
                response[1] if len(response) >= 2 else "<short>",
                f"{expected_cmd:#04x}",
            )
            time.sleep(retry_delay)
        if last_error is not None:
            if isinstance(last_error, TransientError):
                # A single hiccup is survivable (streaming load), but several
                # fully exhausted exchanges in a row mean the device is gone.
                self._consecutive_transient += 1
                if self._consecutive_transient >= 3:
                    self._consecutive_transient = 0
                    raise DeviceDisconnected(
                        f"{self._path_str}: device not responding after repeated "
                        f"I/O errors"
                    ) from last_error
            raise last_error
        if response is not None and len(response) >= 2:
            raise ReportFailed(
                f"device did not echo command {expected_cmd:#04x} "
                f"(got {response[1]:#04x} after {retries} attempts)"
            )
        return response
