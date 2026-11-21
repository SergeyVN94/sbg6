"""High-level state: read everything from the device, write it back, keep profiles."""

from __future__ import annotations

import json
import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import features as F
from .device import (
    FAMILY_DECODER,
    FAMILY_PLAYBACK,
    G6,
    OUTPUT_HEADPHONES,
    Frame,
    G6Error,
)
from .i18n import tr

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "sbg6"
PROFILE_DIR = CONFIG_DIR / "profiles"
STATE_FILE = CONFIG_DIR / "state.json"


def feature_key(family: int, feature: int) -> str:
    return f"{family:02x}:{feature:02x}"


def parse_feature_key(key: str) -> tuple[int, int]:
    family, _, feature = key.partition(":")
    return int(family, 16), int(feature, 16)


@dataclass
class State:
    """Everything we know about the device at a given moment."""

    values: dict[tuple[int, int], float] = field(default_factory=dict)
    sbx: bool = False
    scout: bool = False
    voice_clarity: bool = False
    output: int = OUTPUT_HEADPHONES
    mic_boost: int = 0
    dac_filter: int = 1
    lighting_enabled: bool = True
    lighting_color: tuple[int, int, int] = (255, 255, 255)
    direct: bool = False
    decoder: float = 2.0
    firmware: str | None = None
    hardware_id: int | None = None

    # -- accessors ---------------------------------------------------------

    def get(self, family: int, feature: int, default: float = 0.0) -> float:
        return self.values.get((family, feature), default)

    def enabled(self, feature: int) -> bool:
        return self.get(FAMILY_PLAYBACK, feature) >= 0.5

    def eq_bands(self) -> list[float]:
        return [self.get(FAMILY_PLAYBACK, band) for band in F.PLAYBACK_EQ_BANDS]

    def preamp(self) -> float:
        return self.get(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP)

    def eq_enabled(self) -> bool:
        return self.enabled(F.PLAYBACK_EQ_TOGGLE)

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "saved": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "values": {feature_key(fam, fid): round(val, 4) for (fam, fid), val in self.values.items()},
            "sbx": self.sbx,
            "scout": self.scout,
            "output": self.output,
            "mic_boost": self.mic_boost,
            "dac_filter": self.dac_filter,
            "direct": self.direct,
            "lighting": {"enabled": self.lighting_enabled, "color": list(self.lighting_color)},
        }

    @classmethod
    def from_dict(cls, data: dict) -> State:
        state = cls()
        for key, value in (data.get("values") or {}).items():
            try:
                state.values[parse_feature_key(key)] = float(value)
            except (ValueError, TypeError):
                continue
        state.sbx = bool(data.get("sbx", False))
        state.scout = bool(data.get("scout", False))
        state.output = int(data.get("output", OUTPUT_HEADPHONES))
        state.mic_boost = int(data.get("mic_boost", 0))
        state.dac_filter = int(data.get("dac_filter", 1))
        state.direct = bool(data.get("direct", False))
        lighting = data.get("lighting") or {}
        state.lighting_enabled = bool(lighting.get("enabled", True))
        color = lighting.get("color") or [255, 255, 255]
        if isinstance(color, (list, tuple)) and len(color) == 3:
            state.lighting_color = tuple(int(c) & 0xFF for c in color)  # type: ignore[assignment]
        return state


def read_state(device: G6, *, include_lighting: bool = True) -> State:
    """Ask the device for every known setting."""
    state = State()
    for family, feature in F.STATE_FEATURES:
        value = device.read_feature(family, feature, timeout=0.35)
        if value is not None:
            state.values[(family, feature)] = value
    state.decoder = state.get(FAMILY_DECODER, F.DECODER_MODE, 2.0)

    bitmask = device.read_global()
    if bitmask is not None:
        state.sbx = bool(bitmask & 0x01)
        state.scout = bool(bitmask & 0x02)
        state.voice_clarity = bool(bitmask & 0x04)

    output = device.read_output()
    if output is not None:
        state.output = output

    boost = device.read_mic_boost()
    if boost is not None:
        state.mic_boost = boost

    dac = device.read_dac_filter()
    if dac is not None:
        state.dac_filter = dac

    if include_lighting:
        lighting = device.read_lighting()
        if lighting is not None:
            state.lighting_enabled, state.lighting_color = lighting

    state.firmware = device.firmware()
    state.hardware_id = device.hardware_id()
    return state


def apply_state(
    device: G6,
    state: State,
    *,
    only_features: bool = False,
    lighting: bool = True,
) -> None:
    """Push a stored profile to the device."""
    if lighting and not only_features:
        device.set_lighting_enabled(state.lighting_enabled)
        if state.lighting_enabled:
            device.set_lighting_color(*state.lighting_color)

    for (family, feature), value in state.values.items():
        device.write_feature(family, feature, value)

    if only_features:
        return

    if not device.set_global(1, state.sbx):
        pass
    device.set_global(2, state.scout)
    device.set_output(state.output)
    device.set_dac_filter(state.dac_filter)
    device.set_mic_boost(state.mic_boost)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


def _slug(name: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", name.strip(), flags=re.UNICODE).strip("-")
    return slug or "profile"


def list_profiles() -> list[str]:
    if not PROFILE_DIR.is_dir():
        return []
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


def profile_path(name: str) -> Path:
    return PROFILE_DIR / f"{_slug(name)}.json"


def save_profile(name: str, state: State) -> Path:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    path = profile_path(name)
    data = state.to_dict()
    data["name"] = name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_profile(name: str) -> State:
    path = profile_path(name)
    if not path.exists():
        raise FileNotFoundError(tr("err.profile_missing", name=name))
    return State.from_dict(json.loads(path.read_text(encoding="utf-8")))


def delete_profile(name: str) -> bool:
    path = profile_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def save_last_state(state: State) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def load_last_state() -> State | None:
    try:
        return State.from_dict(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Live controller used by the GUI and the CLI
# ---------------------------------------------------------------------------


class Controller:
    """Writes to the device and keeps a live State in sync.

    Listeners receive small dict events so the GUI can update only what has
    changed (the device pushes values by itself after every write, when the
    hardware buttons are used and when the output is switched).
    """

    def __init__(self, device: G6 | None = None):
        self.device = device or G6()
        self.state = State()
        self._listeners: list = []

    def open(self) -> None:
        self.device.open()
        self.device.add_listener(self._on_frame)

    def close(self) -> None:
        self.device.remove_listener(self._on_frame)
        self.device.close()

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def _emit(self, event: dict) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    def _feature_event(self, family: int, feature: int, value: float) -> None:
        self.state.values[(family, feature)] = value
        self._emit(
            {"type": "feature", "family": family, "feature": feature, "value": value}
        )

    def _on_frame(self, frame: Frame) -> None:
        payload = frame.payload
        if frame.cmd == 0x11 and len(payload) >= 8:
            count = payload[0]
            if count == 0x01:
                family, feature = payload[2], payload[3]
                self._feature_event(family, feature, struct.unpack("<f", payload[4:8])[0])
            elif count >= 0x02:
                offset = 2
                for _ in range(count):
                    chunk = payload[offset : offset + 6]
                    if len(chunk) < 6:
                        break
                    family, feature = chunk[0], chunk[1]
                    self._feature_event(family, feature, struct.unpack("<f", chunk[2:6])[0])
                    offset += 6
        elif frame.cmd == 0x26 and len(payload) >= 4 and payload[0] == 0x08:
            bitmask = payload[3]
            self.state.sbx = bool(bitmask & 0x01)
            self.state.scout = bool(bitmask & 0x02)
            self.state.voice_clarity = bool(bitmask & 0x04)
            self._emit(
                {
                    "type": "globals",
                    "sbx": self.state.sbx,
                    "scout": self.state.scout,
                    "voice_clarity": self.state.voice_clarity,
                }
            )
        elif frame.cmd == 0x2C and len(payload) >= 2 and payload[0] == 0x01:
            self.state.output = payload[1]
            self._emit({"type": "output", "value": payload[1]})
        elif frame.cmd == 0x3C and len(payload) >= 4 and payload[0] == 0x01:
            self.state.mic_boost = payload[3]
            self._emit({"type": "mic_boost", "value": payload[3]})
        elif frame.cmd == 0x6C and len(payload) >= 2 and payload[0] == 0x01:
            self.state.dac_filter = payload[1]
            self._emit({"type": "dac", "value": payload[1]})

    # -- writes ------------------------------------------------------------

    def refresh(self, *, include_lighting: bool = True) -> State:
        direct = self.state.direct  # not readable from the device
        self.state = read_state(self.device, include_lighting=include_lighting)
        self.state.direct = direct
        self._emit({"type": "snapshot", "state": self.state})
        return self.state

    def set_feature(self, family: int, feature: int, value: float) -> None:
        self.state.values[(family, feature)] = float(value)
        if not self.device.write_feature(family, feature, value):
            raise G6Error(f"Устройство отклонило запись {family:#04x}:{feature:#04x}")
        self._emit(
            {"type": "feature", "family": family, "feature": feature, "value": float(value)}
        )

    def set_toggle(self, family: int, feature: int, enabled: bool) -> None:
        self.set_feature(family, feature, 1.0 if enabled else 0.0)

    def set_sbx(self, enabled: bool) -> None:
        self.device.set_global(1, enabled)
        self.state.sbx = enabled
        if enabled:
            self.state.scout = False
        self._emit(
            {
                "type": "globals",
                "sbx": self.state.sbx,
                "scout": self.state.scout,
                "voice_clarity": self.state.voice_clarity,
            }
        )

    def set_scout(self, enabled: bool) -> None:
        self.device.set_global(2, enabled)
        self.state.scout = enabled
        if enabled:
            self.state.sbx = False
        self._emit(
            {
                "type": "globals",
                "sbx": self.state.sbx,
                "scout": self.state.scout,
                "voice_clarity": self.state.voice_clarity,
            }
        )

    def set_output(self, mode: int) -> None:
        self.device.set_output(mode)
        self.state.output = mode
        self._emit({"type": "output", "value": mode})

    def set_dac_filter(self, value: int) -> None:
        self.device.set_dac_filter(value)
        self.state.dac_filter = value
        self._emit({"type": "dac", "value": value})

    def set_mic_boost(self, db: int) -> None:
        self.device.set_mic_boost(db)
        self.state.mic_boost = db
        self._emit({"type": "mic_boost", "value": db})

    def _lighting_event(self) -> None:
        self._emit(
            {
                "type": "lighting",
                "enabled": self.state.lighting_enabled,
                "color": self.state.lighting_color,
            }
        )

    def set_lighting_enabled(self, enabled: bool) -> None:
        self.device.set_lighting_enabled(enabled)
        self.state.lighting_enabled = enabled
        self._lighting_event()

    def set_lighting_color(self, color: tuple[int, int, int]) -> None:
        self.device.set_lighting_color(*color)
        self.state.lighting_color = color
        self._lighting_event()

    def set_direct(self, enabled: bool) -> None:
        # Direct Mode re-clocks the USB link: the device re-enumerates and the
        # hidraw node we hold becomes invalid. Treat a failure as expected and
        # reconnect from scratch afterwards.
        try:
            self.device.set_direct_mode(enabled)
        except G6Error:
            pass
        self.state.direct = enabled
        self.reopen()

    def reopen(self, attempts: int = 20, delay: float = 0.4) -> bool:
        """Reconnect to a device that re-enumerated (Direct Mode, replug)."""
        try:
            self.close()
        except Exception:
            pass
        for _ in range(attempts):
            try:
                device = G6()
                device.open()
                device.add_listener(self._on_frame)
                self.device = device
                self.refresh()
                return True
            except G6Error:
                time.sleep(delay)
        return False

    def apply_eq_preset(self, preset: F.EqPreset) -> None:
        self.device.write_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP, preset.preamp)
        self._feature_event(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP, preset.preamp)
        for band, gain in zip(F.PLAYBACK_EQ_BANDS, preset.bands, strict=False):
            self.device.write_feature(FAMILY_PLAYBACK, band, gain)
            self._feature_event(FAMILY_PLAYBACK, band, gain)

    def apply_profile(self, state: State) -> None:
        for (family, feature), value in state.values.items():
            self.device.write_feature(family, feature, value)
        self.device.set_global(1, state.sbx)
        self.device.set_global(2, state.scout)
        self.device.set_output(state.output)
        self.device.set_dac_filter(state.dac_filter)
        self.device.set_mic_boost(state.mic_boost)
        self.device.set_lighting_enabled(state.lighting_enabled)
        if state.lighting_enabled:
            self.device.set_lighting_color(*state.lighting_color)
        self.state = state
        self._emit({"type": "snapshot", "state": state})
