"""HID transport: thin, defensive wrapper around python-hidapi.

Owns exactly one open device. All raw feature report I/O happens here so the
protocol layer can be tested without hardware.
"""

from __future__ import annotations

import errno
import logging
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


_ERRNO_MAP = {
    errno.EACCES: PermissionDenied,
    errno.EPERM: PermissionDenied,
    errno.ENODEV: DeviceDisconnected,
    errno.ENOENT: DeviceDisconnected,
    errno.ENXIO: DeviceDisconnected,
    errno.EBUSY: DeviceBusy,
    errno.EIO: DeviceDisconnected,
}


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
        return DeviceDisconnected(f"{path} disconnected: {exc}")
    if isinstance(exc, OSError):
        # hidapi reports ENODEV-ish failures as plain OSError strings too.
        message = str(exc)
        if "No such device" in message or "Disconnected" in message:
            return DeviceDisconnected(f"{path}: {message}")
        if "Permission" in message or "denied" in message:
            return PermissionDenied(f"{path}: {message}")
    return TransportError(f"{path}: {exc}")


class HidTransport:
    """Single open HID device with validated feature report I/O."""

    def __init__(
        self,
        path: bytes | str,
        *,
        report_size: int = protocol.REPORT_SIZE,
        debug: bool = False,
        logger: logging.Logger | None = None,
    ):
        self._path_bytes = path if isinstance(path, bytes) else path.encode()
        self._path_str = self._path_bytes.decode(errors="replace")
        self._report_size = report_size
        self._debug = debug
        self._log = logger or log
        self._device = None
        self._closed = False
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
        self._log.debug("opened %s", self._path_str)

    def close(self) -> None:
        self._closed = True
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

    def send_feature_report(self, packet: bytes, expected_cmd: int | None = None) -> bytes:
        """Validate and send one 65 byte feature report, then read the echo."""
        if not self.is_open:
            raise DeviceDisconnected(f"{self._path_str} is not open")
        protocol.validate_packet(packet, expected_cmd)

        if self._debug:
            self._log.debug("TX %s", packet.hex(" "))

        try:
            written = self._device.send_feature_report(packet)
        except BaseException as exc:
            raise _translate(exc, self._path_str) from exc

        self.tx_count += 1
        if written not in (None, -1) and written != len(packet):
            raise ReportFailed(
                f"short write for command {packet[1]:#04x}: {written}/{len(packet)} bytes"
            )
        if self._debug:
            self._log.debug("write returned %s", written)
        return packet

    def read_feature_report(self, size: int | None = None) -> bytes:
        if not self.is_open:
            raise DeviceDisconnected(f"{self._path_str} is not open")
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
        fast (~0.4 ms measured), so no artificial delay is inserted - we only
        pause when the echo does not match yet (device still busy).
        """
        response: bytes | None = None
        last_error: TransportError | None = None
        for attempt in range(retries):
            try:
                self.send_feature_report(packet, expected_cmd)
            except TransportError as exc:
                last_error = exc
                if isinstance(exc, (DeviceDisconnected, PermissionDenied)):
                    raise
                if attempt + 1 < retries:
                    time.sleep(retry_delay * 10)
                    continue
                raise
            if not verify_echo:
                return None
            response = self.read_feature_report()
            if len(response) >= 2 and response[1] == expected_cmd:
                return response
            self._log.debug(
                "echo mismatch (attempt %d): got cmd %s, want %s",
                attempt + 1,
                response[1] if len(response) >= 2 else "<short>",
                f"{expected_cmd:#04x}",
            )
            time.sleep(retry_delay)
        if last_error is not None:
            raise last_error
        if response is not None and len(response) >= 2:
            raise ReportFailed(
                f"device did not echo command {expected_cmd:#04x} "
                f"(got {response[1]:#04x} after {retries} attempts)"
            )
        return response
