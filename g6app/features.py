"""Feature map of the Sound BlasterX G6: what exists, its range and its labels.

All addresses come from USB captures of Sound Blaster Command and are verified
against the hardware (see docs/protocol.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from .device import FAMILY_DECODER, FAMILY_PLAYBACK, FAMILY_RECORDING

FAMILY_NAMES = {
    FAMILY_RECORDING: "recording",
    FAMILY_PLAYBACK: "playback",
    FAMILY_DECODER: "decoder",
}


# ---------------------------------------------------------------------------
# Playback (0x96)
# ---------------------------------------------------------------------------

PLAYBACK_SURROUND_TOGGLE = 0x00
PLAYBACK_SURROUND_LEVEL = 0x01
PLAYBACK_DIALOG_TOGGLE = 0x02
PLAYBACK_DIALOG_LEVEL = 0x03
PLAYBACK_SMARTVOL_TOGGLE = 0x04
PLAYBACK_SMARTVOL_LEVEL = 0x05
PLAYBACK_SMARTVOL_MODE = 0x06
PLAYBACK_CRYSTALIZER_TOGGLE = 0x07
PLAYBACK_CRYSTALIZER_LEVEL = 0x08
PLAYBACK_EQ_TOGGLE = 0x09
PLAYBACK_EQ_PREAMP = 0x0A
PLAYBACK_EQ_BANDS = tuple(range(0x0B, 0x15))  # 10 bands
PLAYBACK_SURROUND_DISTANCE = 0x17
PLAYBACK_BASS_TOGGLE = 0x18
PLAYBACK_BASS_LEVEL = 0x19

#: (key, title, toggle id, level id, description)
EFFECTS = (
    ("surround", "Surround", PLAYBACK_SURROUND_TOGGLE, PLAYBACK_SURROUND_LEVEL,
     "Виртуальный объём: расширяет стереосцену"),
    ("crystalizer", "Crystalizer", PLAYBACK_CRYSTALIZER_TOGGLE, PLAYBACK_CRYSTALIZER_LEVEL,
     "Подчёркивает детали и атаку в музыке и играх"),
    ("bass", "Bass", PLAYBACK_BASS_TOGGLE, PLAYBACK_BASS_LEVEL,
     "Усиление низких частот"),
    ("dialog", "Dialog+", PLAYBACK_DIALOG_TOGGLE, PLAYBACK_DIALOG_LEVEL,
     "Выделяет речь в фильмах и стримах"),
    ("smartvol", "Smart Volume", PLAYBACK_SMARTVOL_TOGGLE, PLAYBACK_SMARTVOL_LEVEL,
     "Выравнивает громкость между треками и роликами"),
)

SMART_VOLUME_MODES = ("Normal", "Loud", "Night")

EQ_FREQUENCIES = (31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)
EQ_LABELS = ("31", "62", "125", "250", "500", "1k", "2k", "4k", "8k", "16k")
EQ_MIN = -12.0
EQ_MAX = 12.0
EQ_STEP = 0.5
PREAMP_MIN = -6.0
PREAMP_MAX = 6.0
PREAMP_STEP = 0.5
SURROUND_DISTANCE_MIN = 10.0
SURROUND_DISTANCE_MAX = 300.0
SURROUND_DISTANCE_STEP = 0.5


@dataclass(frozen=True)
class EqPreset:
    name: str
    title: str
    bands: tuple[float, ...]
    preamp: float = 0.0


EQ_PRESETS: tuple[EqPreset, ...] = (
    EqPreset("flat", "Flat", (0,) * 10),
    EqPreset("gaming", "Gaming", (4, 3, 1, -1, -2, -1, 1, 3, 4, 3), -2.0),
    EqPreset("fps", "FPS / Шаги", (-3, -2, 0, 2, 4, 4, 2, -1, -3, -4), -1.0),
    EqPreset("music", "Music", (3, 2, 1, 0, -1, 0, 1, 2, 2, 1), -1.5),
    EqPreset("cinema", "Cinema", (5, 4, 1, -1, -2, 0, 2, 3, 4, 2), -2.5),
    EqPreset("bass", "Bass Boost", (9, 7, 5, 2, 0, 0, 0, 0, 0, 0), -3.0),
    EqPreset("vocal", "Vocal", (-4, -3, -1, 2, 4, 4, 3, 1, 0, -1), -1.0),
    EqPreset("night", "Ночной", (-6, -5, -3, 0, 2, 1, -1, -2, -3, -4), 0.0),
)


# ---------------------------------------------------------------------------
# Recording (0x95)
# ---------------------------------------------------------------------------

REC_AEC = 0x00
REC_NOISE_REDUCTION = 0x04
REC_NOISE_LEVEL = 0x05
REC_MIC_EQ_TOGGLE = 0x13
REC_MIC_EQ_BANDS = tuple(range(0x14, 0x1C))  # 8 bands
REC_SMART_VOLUME = 0x2C

MIC_BOOST_VALUES = (0, 10, 20, 30)

#: Mic EQ presets as dB per band (0x14..0x1b), taken from Windows captures.
MIC_EQ_PRESETS: dict[str, tuple[float, ...]] = {
    "Preset 1": (-3, -4, 0, 2, 3, -3, 4, 5),
    "Preset 2": (-3, -4, 0, 2, 4, -2, 2, 4),
    "Preset 3": (-2, -3, 3, 4, 4, -4, 3, 2),
    "Preset 4": (-3, -5, 0, 4, 0, -3, 0, 0),
    "Preset 5": (-2, -3, 2, 4, 4, 0, 3, 2),
    "Preset 6": (-5, -4, -2, 0, 3, 4, 6, 7),
    "Preset 7": (0, 3, -2, -4, -4, -2, 5, 7),
    "Preset 8": (0, 0, 2, 2, 3, -4, 2, 4),
    "Preset 9": (0, 0, 2, 2, -2, 0, -4, 4),
    "Preset 10": (0, 2, -2, 0, 3, 5, 6, 5),
    "DM_1": (0, 8, 0, 12, 12, 4, 8, 10),
}


# ---------------------------------------------------------------------------
# Decoder (0x97)
# ---------------------------------------------------------------------------

DECODER_MODE = 0x02
DECODER_MODES = ((2.0, "Normal"), (1.0, "Full"), (3.0, "Night"))


# ---------------------------------------------------------------------------
# Hardware settings
# ---------------------------------------------------------------------------

OUTPUTS = ((0x04, "Наушники", "headphones"), (0x02, "Колонки", "speakers"))

DAC_FILTERS = (
    (0x01, "Fast Roll-off, Minimum Phase"),
    (0x02, "Slow Roll-off, Minimum Phase"),
    (0x03, "NOS (без передискретизации)"),
    (0x04, "Fast Roll-off, Linear Phase"),
    (0x05, "Slow Roll-off, Linear Phase"),
)


# ---------------------------------------------------------------------------
# Full state
# ---------------------------------------------------------------------------

#: All float features that make up a playback/recording profile.
STATE_FEATURES: tuple[tuple[int, int], ...] = (
    (FAMILY_PLAYBACK, PLAYBACK_SURROUND_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_SURROUND_LEVEL),
    (FAMILY_PLAYBACK, PLAYBACK_SURROUND_DISTANCE),
    (FAMILY_PLAYBACK, PLAYBACK_CRYSTALIZER_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_CRYSTALIZER_LEVEL),
    (FAMILY_PLAYBACK, PLAYBACK_BASS_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_BASS_LEVEL),
    (FAMILY_PLAYBACK, PLAYBACK_DIALOG_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_DIALOG_LEVEL),
    (FAMILY_PLAYBACK, PLAYBACK_SMARTVOL_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_SMARTVOL_LEVEL),
    (FAMILY_PLAYBACK, PLAYBACK_SMARTVOL_MODE),
    (FAMILY_PLAYBACK, PLAYBACK_EQ_TOGGLE),
    (FAMILY_PLAYBACK, PLAYBACK_EQ_PREAMP),
    *((FAMILY_PLAYBACK, band) for band in PLAYBACK_EQ_BANDS),
    (FAMILY_RECORDING, REC_AEC),
    (FAMILY_RECORDING, REC_NOISE_REDUCTION),
    (FAMILY_RECORDING, REC_NOISE_LEVEL),
    (FAMILY_RECORDING, REC_MIC_EQ_TOGGLE),
    *((FAMILY_RECORDING, band) for band in REC_MIC_EQ_BANDS),
    (FAMILY_RECORDING, REC_SMART_VOLUME),
    (FAMILY_DECODER, DECODER_MODE),
)


def feature_name(family: int, feature: int) -> str:
    names = {PLAYBACK_SURROUND_TOGGLE: "surround", PLAYBACK_SURROUND_LEVEL: "surround_level"}
    return names.get(feature, f"{family:#04x}:{feature:#04x}")
