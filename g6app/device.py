"""Low-level USB HID transport for the Sound BlasterX G6 (SB1770, 041e:3256).

The G6 is a class-compliant USB audio device for playback/capture, but every
"Sound Blaster Command" setting (SBX, EQ, Scout Mode, output routing, mic boost,
DAC filter, RGB) is a vendor HID command sent to interface 4.

Frames are 64 bytes:

    0x5a  CMD  LEN  payload... (zero padded)

Settings of the DSP are floats addressed by ``(family, feature_id)``:

    0x96  playback effects (SBX, EQ)
    0x95  recording effects (Voice Clarity, mic EQ)
    0x97  decoder mode

Reading a feature:    5a 11 03 01 fam id
    answer:           5a 11 08 01 00 fam id <f32 LE>
Writing a feature:    5a 12 07 01 fam id <f32 LE>
    answer:           5a 02 0a 12 00 ...   (ACK)

Everything is done through /dev/hidrawN so the kernel keeps the interrupt
endpoint polled; libusb/pyusb would require a full USB reset (which kills audio).
"""

from __future__ import annotations

import glob
import os
import select
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

VENDOR_ID = 0x041E
PRODUCT_ID = 0x3256

MAGIC = 0x5A
REPORT_LEN = 64

# USB HID interfaces of the G6.  Interface 3 carries the volume-knob/button
# reports, interface 4 is the vendor control channel used by Sound Blaster
# Command.  We must talk to 1.4.
CONTROL_INTERFACE = "1.4"

OUTPUT_SPEAKERS = 0x02
OUTPUT_HEADPHONES = 0x04

FAMILY_RECORDING = 0x95
FAMILY_PLAYBACK = 0x96
FAMILY_DECODER = 0x97


class G6Error(RuntimeError):
    """Raised when the device cannot be found or a command fails."""


@dataclass(frozen=True)
class Frame:
    cmd: int
    payload: bytes

    @classmethod
    def decode(cls, data: bytes) -> "Frame | None":
        if len(data) < 3 or data[0] != MAGIC:
            return None
        length = data[2]
        if length > REPORT_LEN - 3:
            length = REPORT_LEN - 3
        return cls(data[1], bytes(data[3 : 3 + length]))

    def encode(self) -> bytes:
        body = bytes([MAGIC, self.cmd & 0xFF, len(self.payload) & 0xFF]) + self.payload
        return body.ljust(REPORT_LEN, b"\x00")

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.cmd:#04x} {self.payload.hex(' ')}"


# ---------------------------------------------------------------------------
# hidraw discovery
# ---------------------------------------------------------------------------


def _interface_of(sysfs_device: str) -> str:
    """Return the USB interface name (``8-3.1:1.4``) a hidraw node belongs to."""
    return os.path.basename(os.path.dirname(os.path.realpath(sysfs_device)))


def find_hidraw() -> str | None:
    """Locate the hidraw node of the G6 vendor control interface (1.4)."""
    fallback = None
    for node in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        uevent = os.path.join(node, "device", "uevent")
        try:
            with open(uevent, "r", encoding="ascii", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if f"HID_ID=0003:{VENDOR_ID:08X}:{PRODUCT_ID:08X}" not in text:
            continue
        dev = os.path.join(node, "device")
        iface = _interface_of(dev)
        candidate = f"/dev/{os.path.basename(node)}"
        if iface.endswith(":" + CONTROL_INTERFACE) or iface.endswith(CONTROL_INTERFACE):
            return candidate
        fallback = fallback or candidate
    return fallback


def find_card_index() -> int | None:
    """ALSA card index of the G6, if the snd-usb-audio driver bound it."""
    try:
        with open("/proc/asound/cards", "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if "Sound BlasterX G6" in line:
            head = line.split()[0]
            if head.isdigit():
                return int(head)
    return None


def describe_permissions(path: str | None = None) -> str:
    path = path or find_hidraw()
    if not path:
        return "Устройство не найдено. Проверьте, что Sound BlasterX G6 подключён."
    try:
        st = os.stat(path)
    except OSError as exc:
        return f"{path}: {exc.strerror}"
    if not os.access(path, os.R_OK | os.W_OK):
        return (
            f"Нет доступа к {path} (uid={st.st_uid}, mode={st.st_mode & 0o777:o}).\n"
            "Установите правило udev: sudo ./install.sh (раздел «Права доступа» в README)."
        )
    return ""


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------


class G6:
    """Synchronous wrapper around the HID control channel.

    A background thread continuously drains the interrupt endpoint: the G6
    answers every write with an ACK and spontaneously pushes new values when
    the hardware buttons or the Windows-style profile switch are used.
    """

    def __init__(self, path: str | None = None, *, timeout: float = 0.8):
        self.path = path or os.environ.get("G6_HIDRAW") or find_hidraw()
        self.timeout = timeout
        self._fd: int | None = None
        self._lock = threading.RLock()
        self._io_lock = threading.Lock()
        self._frames: list[tuple[float, Frame]] = []
        self._cond = threading.Condition()
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._listeners: list[Callable[[Frame], None]] = []
        self._failed = False
        self.last_error: str | None = None

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> "G6":
        if self._fd is not None:
            return self
        if not self.path:
            raise G6Error(describe_permissions(None))
        try:
            self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except OSError as exc:
            raise G6Error(
                f"Не удалось открыть {self.path}: {exc.strerror}. "
                "Нужны права на hidraw (правило udev, см. README)."
            ) from exc
        self._stop.clear()
        self._failed = False
        self._reader = threading.Thread(target=self._read_loop, name="g6-hid", daemon=True)
        self._reader.start()
        return self

    def close(self) -> None:
        self._stop.set()
        if self._reader is not None:
            self._reader.join(timeout=1.0)
            self._reader = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def __enter__(self) -> "G6":
        return self.open()

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __del__(self):  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass

    @property
    def connected(self) -> bool:
        return self._fd is not None and not self._stop.is_set() and not self._failed

    # -- listeners ---------------------------------------------------------

    def add_listener(self, callback: Callable[[Frame], None]) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[Frame], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    # -- raw I/O -----------------------------------------------------------

    def _read_loop(self) -> None:
        fd = self._fd
        while not self._stop.is_set() and fd is not None:
            try:
                ready, _, _ = select.select([fd], [], [], 0.25)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                data = os.read(fd, REPORT_LEN)
            except BlockingIOError:
                continue
            except OSError as exc:
                self.last_error = exc.strerror
                self._failed = True
                break
            frame = Frame.decode(data)
            if frame is None:
                continue
            now = time.monotonic()
            with self._cond:
                self._frames.append((now, frame))
                del self._frames[:-400]
                self._cond.notify_all()
            for listener in list(self._listeners):
                try:
                    listener(frame)
                except Exception:
                    pass

    def send(self, cmd: int, payload: Iterable[int] | bytes = b"") -> None:
        if self._fd is None:
            raise G6Error("Устройство не открыто")
        frame = Frame(cmd, bytes(payload))
        # hidraw wants the report ID as the first byte (0 = unnumbered report)
        buf = b"\x00" + frame.encode()
        with self._io_lock:
            try:
                os.write(self._fd, buf)
            except OSError as exc:
                if exc.errno in (19, 71, 5, 108):  # ENODEV, EPROTO, EIO, ESHUTDOWN
                    self._failed = True
                raise G6Error(f"Ошибка записи в устройство: {exc.strerror}") from exc

    def wait_for(
        self,
        match: Callable[[Frame], bool],
        *,
        since: float | None = None,
        timeout: float | None = None,
    ) -> Frame | None:
        """Wait for a frame matching ``match``, scanning already received ones."""
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        since = 0.0 if since is None else since
        with self._cond:
            while True:
                for stamp, frame in reversed(self._frames):
                    if stamp < since:
                        break
                    if match(frame):
                        return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(min(remaining, 0.1))

    def _mark(self) -> float:
        return time.monotonic()

    def command(
        self,
        cmd: int,
        payload: Iterable[int] | bytes = b"",
        *,
        reply: Callable[[Frame], bool] | None = None,
        timeout: float | None = None,
    ) -> Frame | None:
        mark = self._mark()
        time.sleep(0.005)  # ensure no stale frame matches the new request
        self.send(cmd, payload)
        if reply is None:
            reply = lambda f: f.cmd == 0x02 and bool(f.payload) and f.payload[0] == (cmd & 0xFF)
        return self.wait_for(reply, since=mark, timeout=timeout)

    # -- generic feature access -------------------------------------------

    def read_feature(self, family: int, feature: int, *, timeout: float | None = None) -> float | None:
        def match(frame: Frame) -> bool:
            p = frame.payload
            return (
                frame.cmd == 0x11
                and len(p) >= 8
                and p[0] == 0x01
                and p[2] == family
                and p[3] == feature
            )

        frame = self.command(0x11, bytes([0x01, family, feature]), reply=match, timeout=timeout)
        if frame is None:
            return None
        return struct.unpack("<f", frame.payload[4:8])[0]

    def write_feature(self, family: int, feature: int, value: float) -> bool:
        payload = bytes([0x01, family, feature]) + struct.pack("<f", float(value))

        def ack(frame: Frame) -> bool:
            return (
                frame.cmd == 0x02
                and len(frame.payload) >= 2
                and frame.payload[0] == 0x12
            )

        frame = self.command(0x12, payload, reply=ack)
        if frame is None:
            return False
        return frame.payload[1] == 0x00

    def bulk_ranges(self) -> list[tuple[int, int, float, float, float]]:
        """Feature ranges reported by the device (family, id, max, min, step)."""
        frame = self.command(
            0x15, b"\x00", reply=lambda f: f.cmd == 0x15 and len(f.payload) >= 2
        )
        if frame is None:
            return []
        data = frame.payload
        count = data[1]
        out = []
        for i in range(count):
            chunk = data[2 + i * 14 : 2 + (i + 1) * 14]
            if len(chunk) < 14:
                break
            mx, mn, st = struct.unpack("<fff", chunk[2:14])
            out.append((chunk[0], chunk[1], mx, mn, st))
        return out

    def set_global(self, feature: int, enabled: bool) -> bool:
        """SBX master (feature 1) / Scout Mode (feature 2)."""
        frame = self.command(0x26, bytes([0x07, feature, 0x00, int(bool(enabled)), 0x00]))
        return bool(frame and len(frame.payload) > 1 and frame.payload[1] == 0)

    def read_global(self) -> int | None:
        frame = self.command(
            0x26,
            b"\x08\xff\xff",
            reply=lambda f: f.cmd == 0x26 and len(f.payload) >= 4 and f.payload[0] == 0x08,
        )
        if frame is None:
            return None
        return frame.payload[3]

    def read_output(self) -> int | None:
        frame = self.command(
            0x2C,
            b"\x01",
            reply=lambda f: f.cmd == 0x2C and len(f.payload) >= 2 and f.payload[0] == 0x01,
        )
        if frame is None:
            return None
        return frame.payload[1]

    def set_output(self, mode: int) -> bool:
        if mode not in (OUTPUT_SPEAKERS, OUTPUT_HEADPHONES):
            raise ValueError(f"unknown output mode {mode}")
        frame = self.command(0x2C, bytes([0x00, mode, 0x00, 0x00, 0x00]))
        return frame is not None

    def read_mic_boost(self) -> int | None:
        frame = self.command(
            0x3C,
            b"\x01\x00",
            reply=lambda f: f.cmd == 0x3C and len(f.payload) >= 4 and f.payload[0] == 0x01,
        )
        if frame is None:
            return None
        return frame.payload[3]

    def set_mic_boost(self, db: int) -> bool:
        frame = self.command(0x3C, bytes([0x00, 0x00, 0x02, db & 0xFF]))
        return bool(frame and len(frame.payload) > 1 and frame.payload[1] == 0)

    def read_dac_filter(self) -> int | None:
        frame = self.command(
            0x6C,
            b"\x01",
            reply=lambda f: f.cmd == 0x6C and len(f.payload) >= 2 and f.payload[0] == 0x01,
        )
        if frame is None:
            return None
        return frame.payload[1]

    def set_dac_filter(self, value: int) -> bool:
        frame = self.command(0x6C, bytes([0x00, value & 0xFF, 0x00]))
        return frame is not None

    # -- Direct Mode -------------------------------------------------------

    def set_direct_mode(self, enabled: bool) -> bool:
        """Enable/disable Direct Mode.

        The G6 re-clocks its USB link here, so the control transfer itself may
        fail with EPROTO/ENODEV and the hidraw node briefly disappears. That is
        expected: the setting is still applied, the caller just has to reconnect.
        """
        try:
            self.send(0x39, bytes([0x00, 0x05, int(bool(enabled))]))
        except G6Error:
            return True
        self.wait_for(
            lambda f: f.cmd == 0x02 and len(f.payload) >= 2 and f.payload[0] == 0x39,
            timeout=0.25,
        )
        try:
            self.send(0x39, b"\x01")  # commit
        except G6Error:
            pass
        return True

    # -- lighting ----------------------------------------------------------

    def read_lighting(self) -> tuple[bool, tuple[int, int, int]] | None:
        enabled = None
        frame = self.command(
            0x3A,
            b"\x01\x07",
            reply=lambda f: f.cmd == 0x3A and len(f.payload) >= 2 and f.payload[0] == 0x07,
        )
        if frame is not None:
            enabled = bool(frame.payload[1])
        color = None
        frame = self.command(
            0x3A,
            bytes([0x06, 0x0B, 0x01, 0x00, 0x01, 0x01, 0x01]),
            reply=lambda f: f.cmd == 0x3A
            and len(f.payload) >= 9
            and f.payload[0] == 0x0B
            and f.payload[4] == 0x01,
        )
        if frame is not None:
            # payload: 0b 01 00 01 01 a b g r
            a, b, g, r = frame.payload[5:9]
            color = (r, g, b)
        if enabled is None and color is None:
            return None
        return (bool(enabled), color or (255, 255, 255))

    def set_lighting_enabled(self, enabled: bool) -> bool:
        frame = self.command(0x3A, bytes([0x06, int(bool(enabled))]))
        return frame is not None

    def set_lighting_color(self, red: int, green: int, blue: int) -> bool:
        # static color mode first, then the actual colour
        self.send(0x3A, bytes([0x04, 0x00, 0x03, 0x01, 0x00, 0x01]))
        time.sleep(0.02)
        self.send(0x3A, bytes([0x0A, 0x00, 0x03, 0x01, 0x01, 0xFF, blue & 0xFF, green & 0xFF, red & 0xFF]))
        return self.wait_for(
            lambda f: f.cmd == 0x02 and len(f.payload) >= 2 and f.payload[0] == 0x3A,
            timeout=0.4,
        ) is not None

    # -- identity ----------------------------------------------------------

    def firmware(self) -> str | None:
        frame = self.command(
            0x07,
            b"\x02",
            reply=lambda f: f.cmd == 0x07 and len(f.payload) >= 1,
        )
        if frame is None:
            return None
        return frame.payload[: frame.payload[0]].decode("ascii", "replace").strip("\x00 ") or None

    def hardware_id(self) -> int | None:
        frame = self.command(
            0x20, b"", reply=lambda f: f.cmd == 0x20 and len(f.payload) >= 1
        )
        return frame.payload[0] if frame else None

    def serial(self) -> str | None:
        frame = self.command(0x10, b"", reply=lambda f: f.cmd == 0x10 and len(f.payload) >= 8)
        return frame.payload[:8].hex() if frame else None

    def ping(self) -> bool:
        frame = self.command(
            0x06, b"\x01", reply=lambda f: f.cmd == 0x06 and f.payload[:1] == b"\x01", timeout=0.3
        )
        return frame is not None
