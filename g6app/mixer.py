"""ALSA mixer access through libasound (ctypes), used for the Mixer tab.

The Windows "Mixer"/"Recording" volume sliders are not HID commands: they are
standard USB Audio Class Feature Unit requests.  On Linux those are exposed by
snd-usb-audio as ALSA simple mixer controls, so the cleanest equivalent is to
speak the ALSA mixer API directly - no amixer/alsa-utils required.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass, field

SND_MIXER_SCHN_FRONT_LEFT = 0
SND_MIXER_SCHN_FRONT_RIGHT = 1

SND_CTL_ELEM_IFACE_MIXER = 2


class AlsaError(RuntimeError):
    pass


_lib: ctypes.CDLL | None = None


def _load() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    name = ctypes.util.find_library("asound")
    if not name:
        raise AlsaError("libasound.so не найдена")
    lib = ctypes.CDLL(name)

    vp = ctypes.c_void_p
    cp = ctypes.c_char_p
    ci = ctypes.c_int
    cl = ctypes.c_long

    lib.snd_mixer_open.argtypes = [ctypes.POINTER(vp), ci]
    lib.snd_mixer_open.restype = ci
    lib.snd_mixer_attach.argtypes = [vp, cp]
    lib.snd_mixer_attach.restype = ci
    lib.snd_mixer_selem_register.argtypes = [vp, vp, vp]
    lib.snd_mixer_selem_register.restype = ci
    lib.snd_mixer_load.argtypes = [vp]
    lib.snd_mixer_load.restype = ci
    lib.snd_mixer_close.argtypes = [vp]
    lib.snd_mixer_close.restype = ci
    lib.snd_mixer_first_elem.argtypes = [vp]
    lib.snd_mixer_first_elem.restype = vp
    lib.snd_mixer_elem_next.argtypes = [vp]
    lib.snd_mixer_elem_next.restype = vp

    lib.snd_mixer_selem_get_id.argtypes = [vp, vp]
    lib.snd_mixer_selem_get_id.restype = ci
    lib.snd_mixer_selem_id_malloc.argtypes = [ctypes.POINTER(vp)]
    lib.snd_mixer_selem_id_malloc.restype = ci
    lib.snd_mixer_selem_id_free.argtypes = [vp]
    lib.snd_mixer_selem_id_get_name.argtypes = [vp]
    lib.snd_mixer_selem_id_get_name.restype = cp
    lib.snd_mixer_selem_id_get_index.argtypes = [vp]
    lib.snd_mixer_selem_id_get_index.restype = ctypes.c_uint

    lib.snd_mixer_selem_get_name.argtypes = [vp]
    lib.snd_mixer_selem_get_name.restype = cp
    lib.snd_mixer_selem_has_playback_volume.argtypes = [vp]
    lib.snd_mixer_selem_has_playback_volume.restype = ci
    lib.snd_mixer_selem_has_capture_volume.argtypes = [vp]
    lib.snd_mixer_selem_has_capture_volume.restype = ci
    lib.snd_mixer_selem_has_playback_switch.argtypes = [vp]
    lib.snd_mixer_selem_has_playback_switch.restype = ci
    lib.snd_mixer_selem_has_capture_switch.argtypes = [vp]
    lib.snd_mixer_selem_has_capture_switch.restype = ci
    lib.snd_mixer_selem_is_enumerated.argtypes = [vp]
    lib.snd_mixer_selem_is_enumerated.restype = ci

    lib.snd_mixer_selem_get_playback_volume_range.argtypes = [vp, ctypes.POINTER(cl), ctypes.POINTER(cl)]
    lib.snd_mixer_selem_get_playback_volume_range.restype = ci
    lib.snd_mixer_selem_get_capture_volume_range.argtypes = [vp, ctypes.POINTER(cl), ctypes.POINTER(cl)]
    lib.snd_mixer_selem_get_capture_volume_range.restype = ci
    lib.snd_mixer_selem_get_playback_volume.argtypes = [vp, ci, ctypes.POINTER(cl)]
    lib.snd_mixer_selem_get_playback_volume.restype = ci
    lib.snd_mixer_selem_get_capture_volume.argtypes = [vp, ci, ctypes.POINTER(cl)]
    lib.snd_mixer_selem_get_capture_volume.restype = ci
    lib.snd_mixer_selem_set_playback_volume_all.argtypes = [vp, cl]
    lib.snd_mixer_selem_set_playback_volume_all.restype = ci
    lib.snd_mixer_selem_set_capture_volume_all.argtypes = [vp, cl]
    lib.snd_mixer_selem_set_capture_volume_all.restype = ci
    lib.snd_mixer_selem_get_playback_switch.argtypes = [vp, ci, ctypes.POINTER(ci)]
    lib.snd_mixer_selem_get_playback_switch.restype = ci
    lib.snd_mixer_selem_get_capture_switch.argtypes = [vp, ci, ctypes.POINTER(ci)]
    lib.snd_mixer_selem_get_capture_switch.restype = ci
    lib.snd_mixer_selem_set_playback_switch_all.argtypes = [vp, ci]
    lib.snd_mixer_selem_set_playback_switch_all.restype = ci
    lib.snd_mixer_selem_set_capture_switch_all.argtypes = [vp, ci]
    lib.snd_mixer_selem_set_capture_switch_all.restype = ci

    lib.snd_mixer_selem_get_enum_items.argtypes = [vp]
    lib.snd_mixer_selem_get_enum_items.restype = ci
    lib.snd_mixer_selem_get_enum_item_name.argtypes = [vp, ctypes.c_uint, ctypes.c_size_t, cp]
    lib.snd_mixer_selem_get_enum_item_name.restype = ci
    lib.snd_mixer_selem_get_enum_item.argtypes = [vp, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
    lib.snd_mixer_selem_get_enum_item.restype = ci
    lib.snd_mixer_selem_set_enum_item.argtypes = [vp, ctypes.c_uint, ctypes.c_uint]
    lib.snd_mixer_selem_set_enum_item.restype = ci

    _lib = lib
    return lib


@dataclass
class Control:
    name: str
    index: int
    playback: bool
    capture: bool
    playback_range: tuple[int, int] = (0, 0)
    capture_range: tuple[int, int] = (0, 0)
    enum_items: list[str] = field(default_factory=list)
    playback_switch: bool = False
    capture_switch: bool = False
    _elem: int = 0

    @property
    def key(self) -> str:
        return f"{self.name}|{self.index}|{id(self)}"

    @property
    def is_selector(self) -> bool:
        return bool(self.enum_items)

    def percent(self, capture: bool) -> int:
        lib = _load()
        channel = SND_MIXER_SCHN_FRONT_LEFT
        value = ctypes.c_long()
        ok = (
            lib.snd_mixer_selem_get_capture_volume(self._elem, channel, ctypes.byref(value))
            if capture
            else lib.snd_mixer_selem_get_playback_volume(self._elem, channel, ctypes.byref(value))
        )
        if ok != 0:
            return 0
        lo, hi = self.capture_range if capture else self.playback_range
        if hi <= lo:
            return 0
        return round((value.value - lo) * 100 / (hi - lo))

    def set_percent(self, percent: int, capture: bool) -> None:
        lib = _load()
        lo, hi = self.capture_range if capture else self.playback_range
        raw = int(lo + (hi - lo) * max(0, min(100, percent)) / 100)
        if capture:
            lib.snd_mixer_selem_set_capture_volume_all(self._elem, ctypes.c_long(raw))
        else:
            lib.snd_mixer_selem_set_playback_volume_all(self._elem, ctypes.c_long(raw))

    def muted(self, capture: bool) -> bool:
        lib = _load()
        value = ctypes.c_int(1)
        channel = SND_MIXER_SCHN_FRONT_LEFT
        ok = (
            lib.snd_mixer_selem_get_capture_switch(self._elem, channel, ctypes.byref(value))
            if capture
            else lib.snd_mixer_selem_get_playback_switch(self._elem, channel, ctypes.byref(value))
        )
        return ok == 0 and value.value == 0

    def set_muted(self, muted: bool, capture: bool) -> None:
        lib = _load()
        if capture:
            lib.snd_mixer_selem_set_capture_switch_all(self._elem, 0 if muted else 1)
        else:
            lib.snd_mixer_selem_set_playback_switch_all(self._elem, 0 if muted else 1)

    def enum_index(self) -> int:
        lib = _load()
        value = ctypes.c_uint(0)
        if lib.snd_mixer_selem_get_enum_item(self._elem, 0, ctypes.byref(value)) != 0:
            return 0
        return int(value.value)

    def set_enum_index(self, index: int) -> None:
        lib = _load()
        lib.snd_mixer_selem_set_enum_item(self._elem, 0, ctypes.c_uint(max(0, index)))


class Mixer:
    """Simple mixer of the G6 card."""

    def __init__(self, card_index: int):
        self.card_index = card_index
        self._handle = ctypes.c_void_p()
        self._controls: list[Control] = []

    def __enter__(self) -> "Mixer":
        self.open()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def open(self) -> None:
        lib = _load()
        handle = ctypes.c_void_p()
        rc = lib.snd_mixer_open(ctypes.byref(handle), 0)
        if rc != 0:
            raise AlsaError(f"snd_mixer_open: {rc}")
        device = f"hw:{self.card_index}".encode()
        for step, args in (
            ("attach", (handle, device)),
        ):
            rc = lib.snd_mixer_attach(*args)
            if rc != 0:
                lib.snd_mixer_close(handle)
                raise AlsaError(f"snd_mixer_{step}: {rc}")
        lib.snd_mixer_selem_register(handle, None, None)
        rc = lib.snd_mixer_load(handle)
        if rc != 0:
            lib.snd_mixer_close(handle)
            raise AlsaError(f"snd_mixer_load: {rc}")
        self._handle = handle
        self._controls = self._scan()

    def close(self) -> None:
        if self._handle:
            _load().snd_mixer_close(self._handle)
            self._handle = ctypes.c_void_p()

    def _scan(self) -> list[Control]:
        lib = _load()
        controls: list[Control] = []
        elem = lib.snd_mixer_first_elem(self._handle)
        while elem:
            name = (lib.snd_mixer_selem_get_name(elem) or b"?").decode("utf-8", "replace")
            index = 0
            sid = ctypes.c_void_p()
            if lib.snd_mixer_selem_id_malloc(ctypes.byref(sid)) == 0:
                if lib.snd_mixer_selem_get_id(elem, sid) == 0:
                    index = lib.snd_mixer_selem_id_get_index(sid)
                lib.snd_mixer_selem_id_free(sid)
            control = Control(
                name=name,
                index=index,
                playback=bool(lib.snd_mixer_selem_has_playback_volume(elem)),
                capture=bool(lib.snd_mixer_selem_has_capture_volume(elem)),
                playback_switch=bool(lib.snd_mixer_selem_has_playback_switch(elem)),
                capture_switch=bool(lib.snd_mixer_selem_has_capture_switch(elem)),
                _elem=elem,
            )
            if lib.snd_mixer_selem_is_enumerated(elem):
                count = lib.snd_mixer_selem_get_enum_items(elem)
                buf = ctypes.create_string_buffer(64)
                for i in range(max(0, count)):
                    if lib.snd_mixer_selem_get_enum_item_name(elem, i, 64, buf) == 0:
                        control.enum_items.append(buf.value.decode("utf-8", "replace"))
            if control.playback:
                lo, hi = ctypes.c_long(), ctypes.c_long()
                if lib.snd_mixer_selem_get_playback_volume_range(elem, ctypes.byref(lo), ctypes.byref(hi)) == 0:
                    control.playback_range = (lo.value, hi.value)
            if control.capture:
                lo, hi = ctypes.c_long(), ctypes.c_long()
                if lib.snd_mixer_selem_get_capture_volume_range(elem, ctypes.byref(lo), ctypes.byref(hi)) == 0:
                    control.capture_range = (lo.value, hi.value)
            controls.append(control)
            elem = lib.snd_mixer_elem_next(elem)
        return controls

    @property
    def controls(self) -> list[Control]:
        return self._controls

    def playback_controls(self) -> list[Control]:
        return [
            c
            for c in self._controls
            if (c.playback and c.playback_range[1] > c.playback_range[0]) or c.is_selector
        ]

    def capture_controls(self) -> list[Control]:
        return [
            c
            for c in self._controls
            if c.capture and c.capture_range[1] > c.capture_range[0]
        ]

    def find(self, key: str) -> Control | None:
        for control in self._controls:
            if control.key == key:
                return control
        return None
