"""Pages of the main window: Playback, Recording, Mixer, Lighting, Settings."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import features as F
from ..device import (
    FAMILY_PLAYBACK,
    FAMILY_RECORDING,
    OUTPUT_HEADPHONES,
    OUTPUT_SPEAKERS,
)
from ..state import State
from .widgets import (
    Card,
    ColorButton,
    ColorSwatch,
    EQCurve,
    SegmentedControl,
    ToggleSwitch,
    ValueSlider,
)


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area


def _page() -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(14)
    return widget, layout


class EffectCard(QFrame):
    toggled = Signal(bool)
    levelChanged = Signal(float)

    def __init__(self, key: str, title: str, description: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName("effectCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        text.addWidget(self.title)
        desc = QLabel(description)
        desc.setObjectName("dim")
        desc.setWordWrap(True)
        text.addWidget(desc)
        top.addLayout(text, 1)
        self.toggle = ToggleSwitch()
        top.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.slider = ValueSlider(0, 1, 0.01, fmt=lambda v: f"{round(v * 100)}%")
        layout.addWidget(self.slider)
        self.extra_layout = QHBoxLayout()
        self.extra_layout.setSpacing(8)
        layout.addLayout(self.extra_layout)

        self.toggle.toggled.connect(self._on_toggle)
        self.slider.valueChanged.connect(self.levelChanged)

    def _on_toggle(self, checked: bool) -> None:
        self._apply_active(checked)
        self.toggled.emit(checked)

    def _apply_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        # Re-polishing invalidates the cached style of the children; make sure
        # the slider and the switch are repainted right away.
        self.update()
        for child in self.findChildren(QWidget):
            child.update()

    def set_active(self, active: bool) -> None:
        self.toggle.blockSignals(True)
        self.toggle.setChecked(active)
        self.toggle.blockSignals(False)
        self._apply_active(active)

    def set_level(self, value: float) -> None:
        self.slider.set_value(value)

    def set_enabled_state(self, enabled: bool) -> None:
        self.setEnabled(enabled)


class PlaybackPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        body, layout = _page()

        # -- SBX -----------------------------------------------------------
        sbx_card = Card("SBX", "Звуковые эффекты Creative для игр и музыки")
        self.sbx_toggle = ToggleSwitch()
        sbx_card.header.addWidget(self.sbx_toggle)
        self.sbx_toggle.toggled.connect(lambda value: self.win.set_sbx(value))

        grid = QGridLayout()
        grid.setSpacing(8)
        self.effects: dict[str, EffectCard] = {}
        for index, (key, title, toggle, level, description) in enumerate(F.EFFECTS):
            card = EffectCard(key, title, description)
            card.toggled.connect(lambda value, k=key, t=toggle: self._effect_toggled(k, t, value))
            card.levelChanged.connect(
                lambda value, fid=level: self.win.set_feature(FAMILY_PLAYBACK, fid, value)
            )
            grid.addWidget(card, index // 2, index % 2)
            self.effects[key] = card

        surround = self.effects["surround"]
        surround.extra_layout.addWidget(_mini_label("Дистанция"))
        self.distance = ValueSlider(
            F.SURROUND_DISTANCE_MIN,
            F.SURROUND_DISTANCE_MAX,
            F.SURROUND_DISTANCE_STEP,
            fmt=lambda value: f"{value:.0f} см",
        )
        self.distance.valueChanged.connect(
            lambda value: self.win.set_feature(FAMILY_PLAYBACK, F.PLAYBACK_SURROUND_DISTANCE, value)
        )
        surround.extra_layout.addWidget(self.distance, 1)

        smart = self.effects["smartvol"]
        smart.extra_layout.addWidget(_mini_label("Режим"))
        self.smart_mode = QComboBox()
        self.smart_mode.addItems(F.SMART_VOLUME_MODES)
        self.smart_mode.currentIndexChanged.connect(
            lambda index: self.win.set_feature(FAMILY_PLAYBACK, F.PLAYBACK_SMARTVOL_MODE, float(index))
        )
        smart.extra_layout.addWidget(self.smart_mode, 1)

        sbx_card.add_layout(grid)

        # -- equalizer -----------------------------------------------------
        eq_card = Card("Эквалайзер", "10 полос, ±12 дБ · тяните точки, двойной клик — сброс")
        self.eq_toggle = ToggleSwitch()
        eq_card.header.addWidget(self.eq_toggle)
        self.eq_toggle.toggled.connect(
            lambda value: self.win.set_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_TOGGLE, 1.0 if value else 0.0)
        )

        self.curve = EQCurve(F.EQ_FREQUENCIES, F.EQ_LABELS, F.EQ_MIN, F.EQ_MAX, F.EQ_STEP)
        self.curve.bandsChanged.connect(self._bands_changed)
        self._last_bands = [0.0] * 10
        self.curve.editingFinished.connect(self._bands_finished)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.preset = QComboBox()
        self.preset.addItem("Пресеты…", None)
        for preset in F.EQ_PRESETS:
            self.preset.addItem(preset.title, preset.name)
        self.preset.currentIndexChanged.connect(self._preset_selected)
        controls.addWidget(self.preset, 1)

        reset = QPushButton("Сбросить")
        reset.setObjectName("ghost")
        reset.clicked.connect(self._reset_eq)
        controls.addWidget(reset)
        eq_card.add_layout(controls)

        preamp_row = QHBoxLayout()
        preamp_row.addWidget(_mini_label("Pre-amp"))
        self.preamp = ValueSlider(F.PREAMP_MIN, F.PREAMP_MAX, F.PREAMP_STEP, fmt=lambda v: f"{v:+.1f} дБ")
        self.preamp.valueChanged.connect(
            lambda value: self.win.set_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP, value)
        )
        preamp_row.addWidget(self.preamp, 1)
        eq_card.add_layout(preamp_row)
        eq_card.add(self.curve)

        # -- scout ---------------------------------------------------------
        scout_card = Card("Scout Mode", "Усиливает шаги и выстрелы, убирая лишний бас")
        self.scout_toggle = ToggleSwitch()
        scout_card.header.addWidget(self.scout_toggle)
        self.scout_toggle.toggled.connect(lambda value: self.win.set_scout(value))
        scout_note = QLabel("Scout Mode и SBX взаимоисключающие — включение одного выключает другое.")
        scout_note.setObjectName("dim")
        scout_note.setWordWrap(True)
        scout_card.add(scout_note)

        layout.addWidget(sbx_card)
        layout.addWidget(eq_card)
        layout.addWidget(scout_card)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

    # -- actions -----------------------------------------------------------

    def _effect_toggled(self, key: str, toggle: int, enabled: bool) -> None:
        card = self.effects[key]
        self.win.set_feature(FAMILY_PLAYBACK, toggle, 1.0 if enabled else 0.0)
        # An effect switched on at 0 % would be inaudible; give it a sane level.
        if enabled and card.slider.value() < 0.05:
            card.set_level(0.5)
            self.win.set_feature(FAMILY_PLAYBACK, self._level_of(key), 0.5)

    def _level_of(self, key: str) -> int:
        for k, _, _, level, _ in F.EFFECTS:
            if k == key:
                return level
        raise KeyError(key)

    def _bands_changed(self, bands: list[float]) -> None:
        for index, (band, gain) in enumerate(zip(F.PLAYBACK_EQ_BANDS, bands, strict=False)):
            if abs(gain - self._last_bands[index]) < 1e-6:
                continue
            self._last_bands[index] = gain
            self.win.set_feature(FAMILY_PLAYBACK, band, gain, throttled=True)

    def _bands_finished(self, bands: list[float]) -> None:
        self._last_bands = list(bands)
        self.win.finish_eq(bands)

    def _reset_eq(self) -> None:
        self.curve.set_bands([0.0] * 10)
        self._last_bands = [0.0] * 10
        self.preamp.set_value(0.0)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(0)
        self.preset.blockSignals(False)
        self.win.finish_eq([0.0] * 10, preamp=0.0)

    def _preset_selected(self, index: int) -> None:
        name = self.preset.itemData(index)
        if not name:
            return
        preset = next(p for p in F.EQ_PRESETS if p.name == name)
        self.curve.set_bands(list(preset.bands))
        self.preamp.set_value(preset.preamp)
        self.win.apply_preset(preset)

    # -- sync --------------------------------------------------------------

    def sync(self, event: dict, state: State) -> None:
        kind = event.get("type")
        if kind == "globals":
            self.sbx_toggle.blockSignals(True)
            self.sbx_toggle.setChecked(state.sbx)
            self.sbx_toggle.blockSignals(False)
            self.scout_toggle.blockSignals(True)
            self.scout_toggle.setChecked(state.scout)
            self.scout_toggle.blockSignals(False)
            for card in self.effects.values():
                card.set_enabled_state(not state.scout)
        elif kind == "feature" and event.get("family") == FAMILY_PLAYBACK:
            feature = event.get("feature")
            value = event.get("value", 0.0)
            mapping = {
                F.PLAYBACK_SURROUND_TOGGLE: ("surround", True),
                F.PLAYBACK_CRYSTALIZER_TOGGLE: ("crystalizer", True),
                F.PLAYBACK_BASS_TOGGLE: ("bass", True),
                F.PLAYBACK_DIALOG_TOGGLE: ("dialog", True),
                F.PLAYBACK_SMARTVOL_TOGGLE: ("smartvol", True),
                F.PLAYBACK_SURROUND_LEVEL: ("surround", False),
                F.PLAYBACK_CRYSTALIZER_LEVEL: ("crystalizer", False),
                F.PLAYBACK_BASS_LEVEL: ("bass", False),
                F.PLAYBACK_DIALOG_LEVEL: ("dialog", False),
                F.PLAYBACK_SMARTVOL_LEVEL: ("smartvol", False),
            }
            if feature in mapping:
                key, is_toggle = mapping[feature]
                card = self.effects[key]
                if is_toggle:
                    card.set_active(value >= 0.5)
                else:
                    card.set_level(value)
            elif feature == F.PLAYBACK_EQ_TOGGLE:
                enabled = value >= 0.5
                self.eq_toggle.blockSignals(True)
                self.eq_toggle.setChecked(enabled)
                self.eq_toggle.blockSignals(False)
                self.curve.set_enabled_curve(enabled)
            elif feature == F.PLAYBACK_EQ_PREAMP:
                self.preamp.set_value(value)
            elif feature in F.PLAYBACK_EQ_BANDS and not self.win.is_editing():
                index = F.PLAYBACK_EQ_BANDS.index(feature)
                bands = self.curve.bands()
                bands[index] = value
                self.curve.set_bands(bands)
            elif feature == F.PLAYBACK_SMARTVOL_MODE:
                self.smart_mode.blockSignals(True)
                self.smart_mode.setCurrentIndex(int(round(value)))
                self.smart_mode.blockSignals(False)
            elif feature == F.PLAYBACK_SURROUND_DISTANCE:
                self.distance.set_value(value)
        elif kind == "snapshot":
            self.sbx_toggle.blockSignals(True)
            self.sbx_toggle.setChecked(state.sbx)
            self.sbx_toggle.blockSignals(False)
            self.scout_toggle.blockSignals(True)
            self.scout_toggle.setChecked(state.scout)
            self.scout_toggle.blockSignals(False)
            for key, _, toggle, level, _ in F.EFFECTS:
                card = self.effects[key]
                card.set_active(state.get(FAMILY_PLAYBACK, toggle) >= 0.5)
                card.set_level(state.get(FAMILY_PLAYBACK, level))
                card.set_enabled_state(not state.scout)
            self.distance.set_value(state.get(FAMILY_PLAYBACK, F.PLAYBACK_SURROUND_DISTANCE))
            self.smart_mode.blockSignals(True)
            self.smart_mode.setCurrentIndex(int(round(state.get(FAMILY_PLAYBACK, F.PLAYBACK_SMARTVOL_MODE))))
            self.smart_mode.blockSignals(False)
            self.eq_toggle.blockSignals(True)
            self.eq_toggle.setChecked(state.eq_enabled())
            self.eq_toggle.blockSignals(False)
            self.curve.set_enabled_curve(state.eq_enabled())
            if not self.win.is_editing():
                self.curve.set_bands(state.eq_bands())
            self.preamp.set_value(state.preamp())


class RecordingPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        body, layout = _page()

        clarity = Card("Voice Clarity", "Шумоподавление и чистый голос в микрофоне")
        self.clarity_toggle = ToggleSwitch()
        clarity.header.addWidget(self.clarity_toggle)
        self.clarity_toggle.toggled.connect(
            lambda value: self.win.set_feature(
                FAMILY_RECORDING, F.REC_NOISE_REDUCTION, 1.0 if value else 0.0
            )
        )

        level_row = QHBoxLayout()
        level_row.addWidget(_mini_label("Уровень"))
        self.noise_level = ValueSlider(
            0.0, 0.5, 0.005, fmt=lambda v: f"{round(v * 200)}%"
        )
        self.noise_level.valueChanged.connect(
            lambda value: self.win.set_feature(FAMILY_RECORDING, F.REC_NOISE_LEVEL, value)
        )
        level_row.addWidget(self.noise_level, 1)
        clarity.add_layout(level_row)

        self.aec = QCheckBox("Эхоподавление (AEC)")
        self.aec.toggled.connect(
            lambda value: self.win.set_feature(FAMILY_RECORDING, F.REC_AEC, 1.0 if value else 0.0)
        )
        clarity.add(self.aec)

        self.rec_smart = QCheckBox("Smart Volume для записи")
        self.rec_smart.toggled.connect(
            lambda value: self.win.set_feature(FAMILY_RECORDING, F.REC_SMART_VOLUME, 1.0 if value else 0.0)
        )
        clarity.add(self.rec_smart)

        boost_card = Card("Усиление микрофона", "Аппаратный буст входа External Mic")
        self.boost = SegmentedControl([(db, f"+{db} дБ") for db in F.MIC_BOOST_VALUES])
        self.boost.changed.connect(lambda db: self.win.set_mic_boost(int(db)))
        boost_card.add(self.boost)
        boost_hint = QLabel(
            "Буст добавляет усиление до АЦП: для тихого динамического микрофона обычно достаточно +10…+20 дБ."
        )
        boost_hint.setObjectName("dim")
        boost_hint.setWordWrap(True)
        boost_card.add(boost_hint)

        eq_card = Card("Микрофонный эквалайзер", "8 полос, пресеты из Sound Blaster Command")
        self.mic_eq_toggle = ToggleSwitch()
        eq_card.header.addWidget(self.mic_eq_toggle)
        self.mic_eq_toggle.toggled.connect(
            lambda value: self.win.set_feature(FAMILY_RECORDING, F.REC_MIC_EQ_TOGGLE, 1.0 if value else 0.0)
        )
        self.mic_preset = QComboBox()
        self.mic_preset.addItem("Пресеты…", None)
        for name in F.MIC_EQ_PRESETS:
            self.mic_preset.addItem(name, name)
        self.mic_preset.currentIndexChanged.connect(self._mic_preset)
        eq_card.add(self.mic_preset)

        layout.addWidget(clarity)
        layout.addWidget(boost_card)
        layout.addWidget(eq_card)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

    def _mic_preset(self, index: int) -> None:
        name = self.mic_preset.itemData(index)
        if not name:
            return
        for band, gain in zip(F.REC_MIC_EQ_BANDS, F.MIC_EQ_PRESETS[name], strict=False):
            self.win.set_feature(FAMILY_RECORDING, band, gain)
        self.win.set_feature(FAMILY_RECORDING, F.REC_MIC_EQ_TOGGLE, 1.0)
        self.mic_eq_toggle.blockSignals(True)
        self.mic_eq_toggle.setChecked(True)
        self.mic_eq_toggle.blockSignals(False)

    def sync(self, event: dict, state: State) -> None:
        kind = event.get("type")
        if kind == "globals":
            self.clarity_toggle.blockSignals(True)
            self.clarity_toggle.setChecked(state.voice_clarity)
            self.clarity_toggle.blockSignals(False)
        elif kind == "feature" and event.get("family") == FAMILY_RECORDING:
            feature = event.get("feature")
            value = event.get("value", 0.0)
            if feature == F.REC_NOISE_REDUCTION:
                self.clarity_toggle.blockSignals(True)
                self.clarity_toggle.setChecked(value >= 0.5)
                self.clarity_toggle.blockSignals(False)
                self.noise_level.setEnabled(value >= 0.5)
            elif feature == F.REC_NOISE_LEVEL:
                self.noise_level.set_value(value)
            elif feature == F.REC_AEC:
                self.aec.blockSignals(True)
                self.aec.setChecked(value >= 0.5)
                self.aec.blockSignals(False)
            elif feature == F.REC_SMART_VOLUME:
                self.rec_smart.blockSignals(True)
                self.rec_smart.setChecked(value >= 0.5)
                self.rec_smart.blockSignals(False)
            elif feature == F.REC_MIC_EQ_TOGGLE:
                self.mic_eq_toggle.blockSignals(True)
                self.mic_eq_toggle.setChecked(value >= 0.5)
                self.mic_eq_toggle.blockSignals(False)
        elif kind == "mic_boost":
            self.boost.set_value(int(event.get("value", 0)))
        elif kind == "snapshot":
            self.clarity_toggle.blockSignals(True)
            self.clarity_toggle.setChecked(state.voice_clarity)
            self.clarity_toggle.blockSignals(False)
            self.noise_level.set_value(state.get(FAMILY_RECORDING, F.REC_NOISE_LEVEL))
            self.noise_level.setEnabled(state.voice_clarity)
            self.aec.blockSignals(True)
            self.aec.setChecked(state.get(FAMILY_RECORDING, F.REC_AEC) >= 0.5)
            self.aec.blockSignals(False)
            self.rec_smart.blockSignals(True)
            self.rec_smart.setChecked(state.get(FAMILY_RECORDING, F.REC_SMART_VOLUME) >= 0.5)
            self.rec_smart.blockSignals(False)
            self.mic_eq_toggle.blockSignals(True)
            self.mic_eq_toggle.setChecked(state.get(FAMILY_RECORDING, F.REC_MIC_EQ_TOGGLE) >= 0.5)
            self.mic_eq_toggle.blockSignals(False)
            self.boost.set_value(state.mic_boost)


class _MixerRow(QWidget):
    def __init__(self, control: dict, window, capture: bool):
        super().__init__()
        self.win = window
        self.control = control
        self.capture = capture
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.name = QLabel(control["label"])
        self.name.setMinimumWidth(120)
        layout.addWidget(self.name)
        self.slider = ValueSlider(0, 100, 0.5, fmt=lambda v: f"{round(v)}%")
        self.slider.set_value(control.get("percent", 0))
        self.slider.valueChanged.connect(self._set)
        layout.addWidget(self.slider, 1)
        self.mute: QPushButton | None = None
        if control.get("has_switch"):
            self.mute = QPushButton("M")
            self.mute.setObjectName("ghost")
            self.mute.setCheckable(True)
            self.mute.setFixedWidth(30)
            self.mute.setToolTip("Выключить звук")
            self.mute.setChecked(control.get("muted", False))
            self.mute.clicked.connect(self._mute)
            layout.addWidget(self.mute)

    def _set(self, value: float) -> None:
        self.win.mixer_set(self.control["key"], int(round(value)), self.capture)

    def _mute(self, checked: bool) -> None:
        self.win.mixer_mute(self.control["key"], checked, self.capture)

    def update(self, control: dict) -> None:
        self.control = control
        if not self.slider.slider.isSliderDown():
            self.slider.set_value(control.get("percent", 0))
        if self.mute is not None:
            self.mute.blockSignals(True)
            self.mute.setChecked(bool(control.get("muted", False)))
            self.mute.blockSignals(False)


class MixerPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        body, self.layout = _page()
        self.playback_card = Card("Воспроизведение", "Громкость выходов и мониторинга входов")
        self.capture_card = Card("Запись", "Источник и громкость захвата")
        self.selector_card = Card("Источник записи", "Какой вход слушает система")

        self.playback_box = QVBoxLayout()
        self.playback_box.setSpacing(8)
        self.playback_card.add_layout(self.playback_box)

        self.capture_box = QVBoxLayout()
        self.capture_box.setSpacing(8)
        self.capture_card.add_layout(self.capture_box)

        self.selector_combo = QComboBox()
        self.selector_combo.currentIndexChanged.connect(self._selector_changed)
        self.selector_card.add(self.selector_combo)

        self.empty = QLabel("Микшер недоступен: ALSA-карта G6 не найдена.")
        self.empty.setObjectName("muted")

        self.layout.addWidget(self.selector_card)
        self.layout.addWidget(self.playback_card)
        self.layout.addWidget(self.capture_card)
        self.layout.addWidget(self.empty)
        self.layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))
        self._selector_key: str | None = None
        self._selector_items: list[str] = []
        self._rows: dict[str, _MixerRow] = {}
        self._structure: tuple | None = None

    def apply(self, controls: list[dict], selector: dict | None) -> None:
        """Update or rebuild the rows without disturbing a slider being dragged."""
        structure = (
            tuple((c["key"], c["kind"]) for c in controls),
            tuple(selector["items"]) if selector else None,
        )
        available = bool(controls)
        self.empty.setVisible(not available)
        self.playback_card.setVisible(available)
        self.capture_card.setVisible(available)
        self.selector_card.setVisible(selector is not None)

        if structure != self._structure:
            self._structure = structure
            self._rows.clear()
            _clear(self.playback_box)
            for control in controls:
                if control["kind"] == "playback":
                    row = _MixerRow(control, self.win, capture=False)
                    self._rows["playback:" + control["key"]] = row
                    self.playback_box.addWidget(row)
            if not self.playback_box.count():
                self.playback_box.addWidget(_LabelMuted("Нет регулируемых выходов"))

            _clear(self.capture_box)
            for control in controls:
                if control["kind"] == "capture":
                    row = _MixerRow(control, self.win, capture=True)
                    self._rows["capture:" + control["key"]] = row
                    self.capture_box.addWidget(row)
            if not self.capture_box.count():
                self.capture_box.addWidget(_LabelMuted("Нет регулируемых входов"))

            if selector:
                self._selector_key = selector["key"]
                self._selector_items = selector["items"]
                self.selector_combo.blockSignals(True)
                self.selector_combo.clear()
                self.selector_combo.addItems(selector["items"])
                self.selector_combo.setCurrentIndex(selector.get("index", 0))
                self.selector_combo.blockSignals(False)
        else:
            for control in controls:
                row = self._rows.get(control["kind"] + ":" + control["key"])
                if row is not None:
                    row.update(control)
            if selector and selector["index"] != self.selector_combo.currentIndex():
                self.selector_combo.blockSignals(True)
                self.selector_combo.setCurrentIndex(selector["index"])
                self.selector_combo.blockSignals(False)

    def _selector_changed(self, index: int) -> None:
        if self._selector_key is not None:
            self.win.mixer_select(self._selector_key, index)


class _LabelMuted(QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setObjectName("muted")


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class LightingPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        body, layout = _page()

        card = Card("Подсветка", "Кольцо вокруг регулятора громкости")
        self.toggle = ToggleSwitch()
        card.header.addWidget(self.toggle)
        self.toggle.toggled.connect(lambda value: self.win.set_lighting_enabled(value))

        custom_row = QHBoxLayout()
        custom_row.setSpacing(10)
        custom_row.addWidget(_mini_label("Свой цвет"))
        self.color = ColorButton()
        self.color.setToolTip("Открыть палитру и выбрать произвольный цвет")
        self.color.colorChanged.connect(self._apply_custom)
        custom_row.addWidget(self.color)
        self.hex_label = QLabel("")
        self.hex_label.setObjectName("muted")
        self.hex_label.setMinimumWidth(80)
        custom_row.addWidget(self.hex_label)
        custom_row.addStretch(1)
        card.add_layout(custom_row)

        presets_row = QHBoxLayout()
        presets_row.setSpacing(10)
        presets_row.addWidget(_mini_label("Готовые"))
        self.swatches: list[ColorSwatch] = []
        for rgb in (
            (255, 40, 40), (255, 140, 0), (255, 220, 0), (60, 220, 120),
            (0, 200, 255), (60, 110, 255), (170, 80, 255), (255, 255, 255),
        ):
            swatch = ColorSwatch(rgb)
            swatch.clicked.connect(lambda _=False, s=swatch: self._apply_swatch(s.color()))
            self.swatches.append(swatch)
            presets_row.addWidget(swatch)
        presets_row.addStretch(1)
        card.add_layout(presets_row)

        note = QLabel(
            "G6 поддерживает статический цвет и включение/выключение кольца. "
            "Пульсация и «дыхание» в прошивке устройства не реализованы."
        )
        note.setObjectName("dim")
        note.setWordWrap(True)
        card.add(note)

        layout.addWidget(card)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))

    def _apply_swatch(self, color: tuple[int, int, int]) -> None:
        self._refresh_color_widgets(color)
        self.win.set_lighting_color(color)

    def _apply_custom(self, color: tuple[int, int, int]) -> None:
        color = tuple(int(c) & 0xFF for c in color)
        self._refresh_color_widgets(color)
        self.win.set_lighting_color(color)

    def _refresh_color_widgets(self, color: tuple[int, int, int]) -> None:
        color = tuple(int(c) & 0xFF for c in color)
        self.color.set_color(color)
        self.hex_label.setText(f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}")
        for swatch in self.swatches:
            swatch.set_selected(swatch.color() == color)

    def sync(self, event: dict, state: State) -> None:
        if event.get("type") in ("lighting", "snapshot"):
            self.toggle.blockSignals(True)
            self.toggle.setChecked(state.lighting_enabled)
            self.toggle.blockSignals(False)
            self._refresh_color_widgets(state.lighting_color)


class SettingsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.win = window
        body, layout = _page()

        output_card = Card("Выход", "Куда G6 подаёт звук")
        self.output = SegmentedControl([(OUTPUT_HEADPHONES, "Наушники"), (OUTPUT_SPEAKERS, "Колонки")])
        self.output.changed.connect(lambda mode: self.win.set_output(int(mode)))
        output_card.add(self.output)
        out_note = QLabel(
            "Переключение меняет физический выход на самой плате. Громкость Windows/ PipeWire "
            "для наушников и колонок общая."
        )
        out_note.setObjectName("dim")
        out_note.setWordWrap(True)
        output_card.add(out_note)

        direct_card = Card("Direct Mode", "Обход всей обработки SBX для бит-перфект вывода")
        self.direct = ToggleSwitch()
        direct_card.header.addWidget(self.direct)
        self.direct.toggled.connect(lambda value: self.win.set_direct(value))
        direct_note = QLabel(
            "В Direct Mode DSP отключён: эквалайзер и эффекты не работают, но частота "
            "дискретизации и формат передаются в ЦАП без обработки. Включение меняет "
            "клокировку USB, возможен короткий щелчок."
        )
        direct_note.setObjectName("dim")
        direct_note.setWordWrap(True)
        direct_card.add(direct_note)

        dac_card = Card("Цифровой фильтр ЦАП", "CS43131: характер среза на ультравысоких частотах")
        self.dac = QComboBox()
        for value, title in F.DAC_FILTERS:
            self.dac.addItem(title, value)
        self.dac.currentIndexChanged.connect(self._dac_changed)
        dac_card.add(self.dac)

        profile_card = Card("Профили", "Сохраняйте наборы настроек и переключайте их одним щелчком")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.profile_combo = QComboBox()
        self.profile_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self.profile_combo, 1)
        load = QPushButton("Загрузить")
        load.setObjectName("primary")
        load.clicked.connect(self._load_profile)
        row.addWidget(load)
        profile_card.add_layout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.profile_name = QComboBox()
        self.profile_name.setEditable(True)
        self.profile_name.lineEdit().setPlaceholderText("Имя нового профиля")
        row2.addWidget(self.profile_name, 1)
        save = QPushButton("Сохранить текущее")
        save.clicked.connect(self._save_profile)
        row2.addWidget(save)
        delete = QPushButton("Удалить")
        delete.setObjectName("ghost")
        delete.clicked.connect(self._delete_profile)
        row2.addWidget(delete)
        profile_card.add_layout(row2)

        self.autostart = QCheckBox("Восстанавливать последнее состояние при входе в систему")
        self.autostart.toggled.connect(self.win.set_autostart)
        profile_card.add(self.autostart)

        info_card = Card("Устройство")
        self.info = QLabel("…")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_card.add(self.info)
        refresh = QPushButton("Обновить")
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self.win.refresh_state)
        info_card.header.addWidget(refresh)

        layout.addWidget(output_card)
        layout.addWidget(direct_card)
        layout.addWidget(dac_card)
        layout.addWidget(profile_card)
        layout.addWidget(info_card)
        layout.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(body))
        self.reload_profiles()

    def _dac_changed(self, index: int) -> None:
        value = self.dac.itemData(index)
        if value is not None:
            self.win.set_dac_filter(int(value))

    def _save_profile(self) -> None:
        name = self.profile_name.currentText().strip()
        if name:
            self.win.save_profile(name)
            self.reload_profiles()

    def _load_profile(self) -> None:
        name = self.profile_combo.currentData()
        if name:
            self.win.load_profile(name)

    def _delete_profile(self) -> None:
        name = self.profile_combo.currentData()
        if name:
            self.win.delete_profile(name)
            self.reload_profiles()

    def reload_profiles(self) -> None:
        from ..state import list_profiles

        names = list_profiles()
        current = self.profile_combo.currentData()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        if not names:
            self.profile_combo.addItem("Профилей пока нет", None)
            self.profile_combo.setEnabled(False)
        else:
            self.profile_combo.setEnabled(True)
            for name in names:
                self.profile_combo.addItem(name, name)
            if current in names:
                self.profile_combo.setCurrentIndex(names.index(current))
        self.profile_combo.blockSignals(False)

    def sync(self, event: dict, state: State) -> None:
        kind = event.get("type")
        if kind == "output":
            self.output.set_value(state.output)
        elif kind == "dac":
            index = self.dac.findData(state.dac_filter)
            if index >= 0:
                self.dac.blockSignals(True)
                self.dac.setCurrentIndex(index)
                self.dac.blockSignals(False)
        elif kind == "snapshot":
            self.output.set_value(state.output)
            index = self.dac.findData(state.dac_filter)
            if index >= 0:
                self.dac.blockSignals(True)
                self.dac.setCurrentIndex(index)
                self.dac.blockSignals(False)
            self.direct.blockSignals(True)
            self.direct.setChecked(state.direct)
            self.direct.blockSignals(False)
            info = f"Прошивка: {state.firmware or '?'}\n"
            if state.hardware_id:
                info += f"Hardware ID: {state.hardware_id:#04x}\n"
            info += "Интерфейс: HID (hidraw), без USB-reset\n"
            info += "Права доступа: правило packaging/70-sbg6.rules"
            self.info.setText(info)


def _mini_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    label.setMinimumWidth(70)
    return label
