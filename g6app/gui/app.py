"""Main window, worker thread and application entry point."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import features as F
from ..device import (
    FAMILY_PLAYBACK,
    G6,
    OUTPUT_HEADPHONES,
    OUTPUT_SPEAKERS,
    G6Error,
    find_card_index,
)
from ..i18n import get_language, set_language, tr
from ..mixer import Mixer
from ..state import (
    Controller,
    State,
    list_profiles,
    save_last_state,
)
from ..state import (
    delete_profile as delete_profile_file,
)
from ..state import (
    load_profile as load_profile_file,
)
from ..state import (
    save_profile as save_profile_file,
)
from . import theme
from .pages import LightingPage, MixerPage, PlaybackPage, RecordingPage, SettingsPage
from .widgets import SegmentedControl

ROOT = Path(__file__).resolve().parent.parent.parent


def asset_path(name: str) -> Path:
    """Find a bundled asset both in the source tree and in frozen builds."""
    candidates: list[Path] = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS))
    candidates.append(ROOT)
    candidates.append(Path(sys.executable).resolve().parent)
    for base in candidates:
        path = base / "assets" / name
        if path.exists():
            return path
    return ROOT / "assets" / name


ICON_PATH = asset_path("sbg6.svg")

MIXER_PLAYBACK = ("Speaker", "Line In", "External Mic", "S/PDIF In")
MIXER_CAPTURE = ("Line In", "External Mic", "S/PDIF In", "What U Hear")


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------


def app_icon() -> QIcon:
    icon = QIcon(str(ICON_PATH))
    if not icon.isNull():
        return icon
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#20242c"))
    painter.setPen(QColor("#3a4250"))
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    painter.setPen(QColor("#4fd1c5"))
    for i, height in enumerate((10, 24, 38, 28, 16)):
        painter.drawRoundedRect(14 + i * 8, 32 - height // 2, 5, height, 2.5, 2.5)
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# Worker plumbing
# ---------------------------------------------------------------------------


class Bridge(QObject):
    event = Signal(dict)
    error = Signal(str)
    connected = Signal(bool)


class Worker(threading.Thread):
    """Serialises all device/ALSA access on a background thread."""

    def __init__(self, bridge: Bridge):
        super().__init__(name="g6-worker", daemon=True)
        self.bridge = bridge
        self.queue: queue.Queue = queue.Queue()
        self.controller: Controller | None = None
        self.mixer: Mixer | None = None
        self.mixer_card: int | None = None
        self.bridge_connected = False

    def submit(self, fn) -> None:
        self.queue.put(fn)

    def shutdown(self) -> None:
        if self.controller is not None:
            try:
                self.controller.close()
            except Exception:
                pass
            self.controller = None
        if self.mixer is not None:
            try:
                self.mixer.close()
            except Exception:
                pass
            self.mixer = None

    def run(self) -> None:
        while True:
            fn = self.queue.get()
            if fn is None:
                return
            try:
                fn()
            except Exception as exc:  # keep the worker alive
                self.bridge.error.emit(str(exc))

    # -- device ------------------------------------------------------------

    def check_connection(self) -> None:
        controller = self.controller
        if controller is not None and controller.device.connected:
            if not self.bridge_connected:
                self.bridge.connected.emit(True)
            return
        self.bridge_connected = False
        self.connect_device()

    def connect_device(self) -> bool:
        if self.controller is not None:
            try:
                self.controller.close()
            except Exception:
                pass
            self.controller = None
        try:
            controller = Controller(G6())
            controller.open()
            controller.add_listener(self.bridge.event.emit)
            self.controller = controller
            self.bridge_connected = True
            self.bridge.connected.emit(True)
            controller.refresh()
            self.emit_mixer()
            return True
        except Exception as exc:
            self.bridge.connected.emit(False)
            self.bridge.error.emit(str(exc))
            return False

    # -- alsa mixer --------------------------------------------------------

    def emit_mixer(self) -> None:
        try:
            card = find_card_index()
            if card is None:
                raise RuntimeError("ALSA-карта G6 не найдена")
            if self.mixer is None or self.mixer_card != card:
                self.mixer = Mixer(card)
                self.mixer.open()
                self.mixer_card = card
            controls = []
            for control in self.mixer.playback_controls():
                if control.is_selector:
                    continue
                if control.name in MIXER_PLAYBACK:
                    controls.append(
                        {
                            "key": control.key,
                            "label": control.name,
                            "kind": "playback",
                            "percent": control.percent(False),
                            "muted": control.muted(False),
                            "has_switch": control.playback_switch,
                        }
                    )
            for control in self.mixer.capture_controls():
                if control.name in MIXER_CAPTURE:
                    controls.append(
                        {
                            "key": control.key,
                            "label": control.name,
                            "kind": "capture",
                            "percent": control.percent(True),
                            "muted": control.muted(True),
                            "has_switch": control.capture_switch,
                        }
                    )
            selector = None
            for control in self.mixer.controls:
                if control.name == "PCM Capture Source" and control.enum_items:
                    selector = {
                        "key": control.key,
                        "label": "Источник",
                        "items": control.enum_items,
                        "index": control.enum_index(),
                    }
                    break
            self.bridge.event.emit({"type": "mixer", "controls": controls, "selector": selector})
        except Exception as exc:
            self.bridge.error.emit(f"Микшер: {exc}")

    def mixer_set(self, key: str, value: int, capture: bool) -> None:
        if not self.mixer:
            return
        control = self.mixer.find(key)
        if control:
            control.set_percent(value, capture)
            self.emit_mixer()

    def mixer_mute(self, key: str, muted: bool, capture: bool) -> None:
        if not self.mixer:
            return
        control = self.mixer.find(key)
        if control:
            control.set_muted(muted, capture)
            self.emit_mixer()

    def mixer_select(self, key: str, index: int) -> None:
        if not self.mixer:
            return
        control = self.mixer.find(key)
        if control:
            control.set_enum_index(index)
            self.emit_mixer()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = State()
        self.bridge = Bridge()
        self.worker = Worker(self.bridge)
        self.worker.start()
        self.pending: dict[tuple[int, int], float] = {}
        self._edit_until = 0.0
        self._connected = False

        self.setWindowTitle("Sound Blaster G6")
        self.setMinimumSize(980, 700)
        self.resize(1140, 840)
        self.setWindowIcon(app_icon())

        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(80)
        self.flush_timer.setSingleShot(True)
        self.flush_timer.timeout.connect(self._flush)

        self.retry_timer = QTimer(self)
        self.retry_timer.setInterval(2000)
        self.retry_timer.timeout.connect(self._attempt_connect)
        self.retry_timer.start()

        self._build_ui()
        self.bridge.event.connect(self._on_event)
        self.bridge.error.connect(self._on_error)
        self.bridge.connected.connect(self._on_connected)

        QTimer.singleShot(50, self._attempt_connect)
        QTimer.singleShot(300, self._sync_autostart)

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 20, 14, 16)
        side.setSpacing(6)

        title = QLabel("Sound Blaster")
        title.setObjectName("heroTitle")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        side.addWidget(title)
        subtitle = QLabel(tr("app.tagline"))
        subtitle.setObjectName("muted")
        side.addWidget(subtitle)
        side.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.pages = QStackedWidget()
        self.page_playback = PlaybackPage(self)
        self.page_recording = RecordingPage(self)
        self.page_mixer = MixerPage(self)
        self.page_lighting = LightingPage(self)
        self.page_settings = SettingsPage(self)
        entries = (
            (tr("nav.playback"), self.page_playback),
            (tr("nav.recording"), self.page_recording),
            (tr("nav.mixer"), self.page_mixer),
            (tr("nav.lighting"), self.page_lighting),
            (tr("nav.settings"), self.page_settings),
        )
        for index, (label, page) in enumerate(entries):
            button = QPushButton(label)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setChecked(index == 0)
            self.nav_group.addButton(button, index)
            side.addWidget(button)
            self.pages.addWidget(page)
        self.nav_group.idClicked.connect(self.pages.setCurrentIndex)
        side.addStretch(1)

        self.status_dot = QLabel(f"●  {tr('status.disconnected')}")
        self.status_dot.setObjectName("muted")
        side.addWidget(self.status_dot)
        version = QLabel("v0.1 · hidraw")
        version.setObjectName("dim")
        side.addWidget(version)

        # content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("pageHeader")
        header.setStyleSheet(
            f"QFrame#pageHeader {{ background: {theme.BG};"
            f" border-bottom: 1px solid {theme.BORDER}; }}"
        )
        head = QHBoxLayout(header)
        head.setContentsMargins(22, 14, 22, 14)
        head.setSpacing(14)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.device_title = QLabel("Sound BlasterX G6")
        self.device_title.setObjectName("heroTitle")
        titles.addWidget(self.device_title)
        self.device_sub = QLabel(tr("status.searching"))
        self.device_sub.setObjectName("muted")
        titles.addWidget(self.device_sub)
        head.addLayout(titles)
        head.addStretch(1)

        self.output_switch = SegmentedControl(
            [
                (OUTPUT_HEADPHONES, tr("header.output.headphones")),
                (OUTPUT_SPEAKERS, tr("header.output.speakers")),
            ]
        )
        self.output_switch.changed.connect(lambda mode: self.set_output(int(mode)))
        head.addWidget(self.output_switch)

        refresh = QPushButton(tr("header.refresh"))
        refresh.setObjectName("ghost")
        refresh.clicked.connect(self.refresh_state)
        head.addWidget(refresh)

        content_layout.addWidget(header)
        content_layout.addWidget(self.pages, 1)

        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {theme.BG_ALT}; color: {theme.MUTED}; }}"
        )
        self.status(tr("status.ready"))

        self._build_tray()
        QShortcut(QKeySequence.StandardKey.Quit, self, activated=self.quit)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("Sound Blaster G6")
        menu = QMenu()
        menu.addAction(tr("tray.open"), self._show_window)
        menu.addSeparator()
        self.tray_output = menu.addMenu(tr("tray.output"))
        self.tray_output_headphones = self.tray_output.addAction(tr("header.output.headphones"))
        self.tray_output_headphones.triggered.connect(lambda: self.set_output(OUTPUT_HEADPHONES))
        self.tray_output_speakers = self.tray_output.addAction(tr("header.output.speakers"))
        self.tray_output_speakers.triggered.connect(lambda: self.set_output(OUTPUT_SPEAKERS))
        self.tray_sbx = menu.addAction("SBX")
        self.tray_sbx.setCheckable(True)
        self.tray_sbx.triggered.connect(self.set_sbx)
        self.tray_scout = menu.addAction("Scout Mode")
        self.tray_scout.setCheckable(True)
        self.tray_scout.triggered.connect(self.set_scout)
        self.tray_eq = menu.addAction(tr("tray.eq"))
        self.tray_eq.setCheckable(True)
        self.tray_eq.triggered.connect(
            lambda checked: self.set_feature(FAMILY_PLAYBACK, F.PLAYBACK_EQ_TOGGLE, 1.0 if checked else 0.0)
        )
        self.tray_profiles = menu.addMenu(tr("tray.profiles"))
        menu.addSeparator()
        menu.addAction(tr("tray.quit"), self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.show()
        self._reload_tray_profiles()

    def _reload_tray_profiles(self) -> None:
        self.tray_profiles.clear()
        names = list_profiles()
        if not names:
            action = self.tray_profiles.addAction(tr("tray.no_profiles"))
            action.setEnabled(False)
            return
        for name in names:
            action = self.tray_profiles.addAction(name)
            action.triggered.connect(lambda _=False, n=name: self.load_profile(n))

    def _tray_clicked(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        if self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.status(tr("status.minimized"))
        else:
            self.quit()

    def quit(self) -> None:
        self._save_last()
        self.worker.submit(self.worker.shutdown)
        self.worker.submit(None)
        self.worker.join(timeout=2.0)
        QApplication.quit()

    # -- connection --------------------------------------------------------

    def _attempt_connect(self) -> None:
        self.worker.submit(self.worker.check_connection)

    def _on_connected(self, connected: bool) -> None:
        self._connected = connected
        if connected:
            self.status_dot.setText(f"●  {tr('status.connected')}")
            self.status_dot.setStyleSheet(
                f"color: {theme.OK}; font-size: 9pt;"
            )
        else:
            self.status_dot.setText(f"●  {tr('status.disconnected')}")
            self.status_dot.setStyleSheet(f"color: {theme.ACCENT}; font-size: 9pt;")
            self.device_sub.setText(tr("status.device_missing"))

    def _on_error(self, message: str) -> None:
        self.status(message, error=True)

    def status(self, message: str, *, error: bool = False) -> None:
        self.statusBar().setStyleSheet(
            f"QStatusBar {{ background: {theme.BG_ALT}; color: "
            f"{theme.ACCENT if error else theme.MUTED}; }}"
        )
        self.statusBar().showMessage(message, 6000 if error else 3500)

    # -- events ------------------------------------------------------------

    def _on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "feature":
            self.state.values[(event["family"], event["feature"])] = event["value"]
        elif kind == "globals":
            self.state.sbx = event.get("sbx", self.state.sbx)
            self.state.scout = event.get("scout", self.state.scout)
            self.state.voice_clarity = event.get("voice_clarity", self.state.voice_clarity)
        elif kind == "output":
            self.state.output = event["value"]
        elif kind == "mic_boost":
            self.state.mic_boost = event["value"]
        elif kind == "dac":
            self.state.dac_filter = event["value"]
        elif kind == "lighting":
            self.state.lighting_enabled = event["enabled"]
            self.state.lighting_color = tuple(event["color"])
        elif kind == "snapshot":
            self.state = event["state"]
            output = (
                tr("header.output.headphones")
                if self.state.output == OUTPUT_HEADPHONES
                else tr("header.output.speakers")
            )
            self.device_sub.setText(
                tr("status.firmware_output", firmware=self.state.firmware or "?", output=output)
            )
            self.output_switch.set_value(self.state.output)
            save_last_state(self.state)
        elif kind == "mixer":
            self.page_mixer.apply(event.get("controls", []), event.get("selector"))
        elif kind == "profiles":
            self.page_settings.reload_profiles()
            self._reload_tray_profiles()

        for page in (
            self.page_playback,
            self.page_recording,
            self.page_lighting,
            self.page_settings,
        ):
            page.sync(event, self.state)
        self._sync_tray()

    def _sync_tray(self) -> None:
        self.tray_sbx.blockSignals(True)
        self.tray_sbx.setChecked(self.state.sbx)
        self.tray_sbx.blockSignals(False)
        self.tray_scout.blockSignals(True)
        self.tray_scout.setChecked(self.state.scout)
        self.tray_scout.blockSignals(False)
        self.tray_eq.blockSignals(True)
        self.tray_eq.setChecked(self.state.eq_enabled())
        self.tray_eq.blockSignals(False)
        self.tray_output_headphones.setCheckable(True)
        self.tray_output_speakers.setCheckable(True)
        self.tray_output_headphones.setChecked(self.state.output == OUTPUT_HEADPHONES)
        self.tray_output_speakers.setChecked(self.state.output == OUTPUT_SPEAKERS)
        if self.state.output == OUTPUT_HEADPHONES:
            self.output_switch.set_value(OUTPUT_HEADPHONES)
        else:
            self.output_switch.set_value(OUTPUT_SPEAKERS)

    # -- editing state -----------------------------------------------------

    def is_editing(self) -> bool:
        return time.monotonic() < self._edit_until

    def begin_edit(self, seconds: float = 0.6) -> None:
        self._edit_until = time.monotonic() + seconds

    # -- writes ------------------------------------------------------------

    def _submit(self, fn) -> None:
        self.worker.submit(fn)

    def set_feature(self, family: int, feature: int, value: float, *, throttled: bool = False) -> None:
        if family == FAMILY_PLAYBACK and feature in F.PLAYBACK_EQ_BANDS:
            self.begin_edit(0.8)
        self.state.values[(family, feature)] = float(value)
        if throttled:
            self.pending[(family, feature)] = float(value)
            if not self.flush_timer.isActive():
                self.flush_timer.start()
            return
        self._submit(lambda: self._write_one(family, feature, value))

    def _write_one(self, family: int, feature: int, value: float) -> None:
        controller = self.worker.controller
        if controller:
            controller.set_feature(family, feature, value)

    def _flush(self) -> None:
        items = list(self.pending.items())
        self.pending.clear()
        if not items:
            return
        self._submit(lambda: self._write_many(items))

    def _write_many(self, items) -> None:
        controller = self.worker.controller
        if not controller:
            return
        for (family, feature), value in items:
            controller.set_feature(family, feature, value)

    def finish_eq(self, bands: list[float], preamp: float | None = None) -> None:
        self.pending.clear()
        self.begin_edit(0.5)
        family = FAMILY_PLAYBACK
        payload = list(zip(F.PLAYBACK_EQ_BANDS, bands, strict=False))
        if preamp is not None:
            payload.insert(0, (F.PLAYBACK_EQ_PREAMP, preamp))
        for feature, value in payload:
            self.state.values[(family, feature)] = float(value)
        self._submit(lambda: self._write_many(payload))

    def apply_preset(self, preset: F.EqPreset) -> None:
        self.pending.clear()
        self.begin_edit(1.0)
        for band, gain in zip(F.PLAYBACK_EQ_BANDS, preset.bands, strict=False):
            self.state.values[(FAMILY_PLAYBACK, band)] = gain
        self.state.values[(FAMILY_PLAYBACK, F.PLAYBACK_EQ_PREAMP)] = preset.preamp
        self._submit(lambda: self._apply_preset(preset))

    def _apply_preset(self, preset: F.EqPreset) -> None:
        controller = self.worker.controller
        if controller:
            controller.apply_eq_preset(preset)

    def set_sbx(self, enabled: bool) -> None:
        self._submit(lambda: self.worker.controller and self.worker.controller.set_sbx(enabled))

    def set_scout(self, enabled: bool) -> None:
        self._submit(lambda: self.worker.controller and self.worker.controller.set_scout(enabled))

    def set_direct(self, enabled: bool) -> None:
        self.state.direct = enabled
        self._submit(lambda: self.worker.controller and self.worker.controller.set_direct(enabled))

    def set_output(self, mode: int) -> None:
        self.state.output = mode
        self.output_switch.set_value(mode)
        self._submit(lambda: self.worker.controller and self.worker.controller.set_output(mode))

    def set_dac_filter(self, value: int) -> None:
        self.state.dac_filter = value
        self._submit(lambda: self.worker.controller and self.worker.controller.set_dac_filter(value))

    def set_mic_boost(self, db: int) -> None:
        self.state.mic_boost = db
        self._submit(lambda: self.worker.controller and self.worker.controller.set_mic_boost(db))

    def set_lighting_enabled(self, enabled: bool) -> None:
        self.state.lighting_enabled = enabled
        self._submit(
            lambda: self.worker.controller and self.worker.controller.set_lighting_enabled(enabled)
        )

    def set_lighting_color(self, color: tuple[int, int, int]) -> None:
        self.state.lighting_color = tuple(color)
        self._submit(
            lambda: self.worker.controller and self.worker.controller.set_lighting_color(tuple(color))
        )

    def refresh_state(self) -> None:
        self._submit(lambda: self.worker.controller and self.worker.controller.refresh())

    # -- mixer -------------------------------------------------------------

    def mixer_set(self, key: str, value: int, capture: bool) -> None:
        self.begin_edit(0.4)
        self._submit(lambda: self.worker.mixer_set(key, value, capture))

    def mixer_mute(self, key: str, muted: bool, capture: bool) -> None:
        self._submit(lambda: self.worker.mixer_mute(key, muted, capture))

    def mixer_select(self, key: str, index: int) -> None:
        self._submit(lambda: self.worker.mixer_select(key, index))

    # -- profiles ----------------------------------------------------------

    def save_profile(self, name: str) -> None:
        def job() -> None:
            controller = self.worker.controller
            if not controller:
                raise G6Error(tr("err.no_device"))
            save_profile_file(name, controller.refresh())
            self.bridge.event.emit({"type": "profiles"})

        self._submit(job)
        self.status(tr("status.profile_saved", name=name))

    def load_profile(self, name: str) -> None:
        def job() -> None:
            state = load_profile_file(name)
            controller = self.worker.controller
            if not controller:
                raise G6Error(tr("err.no_device"))
            controller.apply_profile(state)

        self._submit(job)
        self.status(tr("status.profile_loaded", name=name))

    def delete_profile(self, name: str) -> None:
        delete_profile_file(name)
        self._reload_tray_profiles()
        self.page_settings.reload_profiles()
        self.status(tr("status.profile_deleted", name=name))

    # -- autostart ---------------------------------------------------------

    def set_autostart(self, enabled: bool) -> None:
        action = "enable" if enabled else "disable"
        try:
            result = subprocess.run(
                ["systemctl", "--user", action, "sbg6-restore.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                self.status(tr("status.autostart_missing"), error=True)
                return
            if enabled:
                subprocess.run(
                    ["systemctl", "--user", "start", "sbg6-restore.service"],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            self.status(tr("status.autostart_on") if enabled else tr("status.autostart_off"))
        except (OSError, subprocess.SubprocessError) as exc:
            self.status(tr("status.systemctl", error=exc), error=True)

    def _sync_autostart(self) -> None:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "sbg6-restore.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            enabled = result.stdout.strip() == "enabled"
        except (OSError, subprocess.SubprocessError):
            enabled = False
        self.page_settings.autostart.blockSignals(True)
        self.page_settings.autostart.setChecked(enabled)
        self.page_settings.autostart.blockSignals(False)

    def change_language(self, code: str) -> None:
        if code == get_language():
            return
        set_language(code)
        QTimer.singleShot(120, self._rebuild_ui)

    def _rebuild_ui(self) -> None:
        """Recreate the window so every label is built in the new language."""
        app = QApplication.instance()
        theme.apply(app)
        self._save_last()
        self.retry_timer.stop()
        self.tray.hide()
        self.worker.submit(self.worker.shutdown)
        self.worker.submit(None)
        self.worker.join(timeout=2.0)
        replacement = MainWindow()
        replacement.show()
        app._main_window = replacement
        self.hide()
        self.deleteLater()

    def _save_last(self) -> None:
        save_last_state(self.state)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    device = None
    if "--device" in argv:
        index = argv.index("--device")
        if index + 1 < len(argv):
            device = argv[index + 1]
            del argv[index : index + 2]
    if device:
        os.environ["G6_HIDRAW"] = device

    app = QApplication(sys.argv[:1] + argv)
    app.setApplicationName("Sound Blaster G6")
    app.setApplicationDisplayName("Sound Blaster G6")
    app.setDesktopFileName("sbg6")
    app.setWindowIcon(app_icon())
    theme.apply(app)
    window = MainWindow()
    window.show()
    app._main_window = window
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
