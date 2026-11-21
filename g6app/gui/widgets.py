"""Custom widgets: cards, switches, sliders, segmented controls and the EQ curve."""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import theme


class Card(QFrame):
    """Rounded panel with an optional title row."""

    def __init__(self, title: str | None = None, subtitle: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(10)
        if title:
            labels = QVBoxLayout()
            labels.setSpacing(2)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("cardTitle")
            labels.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setObjectName("muted")
                self.subtitle_label.setWordWrap(True)
                labels.addWidget(self.subtitle_label)
            self.header.addLayout(labels, 1)
            self.header.addStretch(0)
            self._layout.addLayout(self.header)
        else:
            self.title_label = None
            self.subtitle_label = None

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)


class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("sectionTitle")


class ToggleSwitch(QAbstractButton):
    """iOS-style switch, animated."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(130)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(46, 26)

    def minimumSizeHint(self) -> QSize:
        return QSize(46, 26)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._offset = 1.0 if checked else 0.0
        if self._animation.state() != QPropertyAnimation.State.Running:
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 2, 44, 22)
        off = QColor("#38414d")
        if self.isEnabled():
            track = QColor(theme.ACCENT) if self._offset > 0.01 else off
            if 0.01 < self._offset < 0.99:
                track = _blend(off, QColor(theme.ACCENT), self._offset)
        else:
            track = QColor("#2a3038")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, 11, 11)
        knob_x = rect.left() + 3 + (rect.width() - 6 - 16) * self._offset
        painter.setBrush(QColor("#ffffff") if self.isEnabled() else QColor("#6a7481"))
        painter.drawEllipse(QRectF(knob_x, rect.top() + 3, 16, 16))
        painter.end()


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


class ValueSlider(QWidget):
    """Slider with a live value readout.

    The public value is a float between ``minimum`` and ``maximum``; the Qt
    slider itself works in integer steps scaled by ``step``.
    """

    valueChanged = Signal(float)
    editingFinished = Signal(float)

    def __init__(
        self,
        minimum: float = 0.0,
        maximum: float = 1.0,
        step: float = 0.01,
        fmt=lambda value: f"{value:.0f}%",
        parent=None,
    ):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self._fmt = fmt
        self._scale = max(1, round(1 / step))
        self._guard = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumHeight(26)
        self.slider.setRange(0, round((maximum - minimum) * self._scale))
        self.slider.setPageStep(max(1, round(0.1 * (maximum - minimum) * self._scale)))
        layout.addWidget(self.slider, 1)
        self.readout = QLabel("", self)
        self.readout.setObjectName("value")
        self.readout.setMinimumWidth(64)
        self.readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.readout)

        self.slider.valueChanged.connect(self._on_slider)
        self.slider.sliderReleased.connect(lambda: self.editingFinished.emit(self.value()))

    def _on_slider(self, raw: int) -> None:
        self.readout.setText(self._fmt(self.value()))
        if not self._guard:
            self.valueChanged.emit(self.value())

    def value(self) -> float:
        return self.minimum + self.slider.value() / self._scale

    def set_value(self, value: float, *, emit: bool = False) -> None:
        if self.slider.isSliderDown():
            return
        self._guard = True
        raw = round((value - self.minimum) * self._scale)
        self.slider.setValue(max(0, min(self.slider.maximum(), raw)))
        self.readout.setText(self._fmt(self.value()))
        self._guard = False
        if emit:
            self.valueChanged.emit(self.value())


class SegmentedControl(QFrame):
    """Exclusive row of flat buttons."""

    changed = Signal(object)

    def __init__(self, options: list[tuple[object, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"QFrame#card {{ background: {theme.BG_ALT}; border-radius: 10px; padding: 3px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[object, QPushButton] = {}
        for value, label in options:
            button = QPushButton(label)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[value] = button
            button.clicked.connect(lambda _=False, v=value: self.changed.emit(v))

    def set_value(self, value: object, *, emit: bool = False) -> None:
        for key, button in self._buttons.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == value)
            button.blockSignals(blocked)
        if emit:
            self.changed.emit(value)


class ColorSwatch(QAbstractButton):
    """A plain colour chip: clicking applies the colour immediately."""

    def __init__(self, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self._color = tuple(int(c) & 0xFF for c in color)
        self._selected = False
        self._hover = False
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        r, g, b = self._color
        self.setToolTip(f"#{r:02x}{g:02x}{b:02x}")

    def color(self) -> tuple[int, int, int]:
        return self._color

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def enterEvent(self, _event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(6, 6, 18, 18)
        if self._selected:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(3.5, 3.5, 23, 23))
        elif self._hover:
            painter.setPen(QPen(QColor("#ffffff66"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(4.25, 4.25, 21.5, 21.5))
        painter.setPen(QPen(QColor("#00000040"), 1))
        painter.setBrush(QColor(*self._color))
        painter.drawEllipse(rect)
        painter.end()


class ColorButton(QPushButton):
    colorChanged = Signal(tuple)

    def __init__(self, color: tuple[int, int, int] = (255, 255, 255), parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color = color
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self) -> None:
        r, g, b = self._color
        border = "#ffffff" if (r * 299 + g * 587 + b * 114) / 1000 < 40 else "#26000000"
        self.setStyleSheet(
            f"QPushButton {{ background: rgb({r},{g},{b}); border: 2px solid {border};"
            " border-radius: 17px; }"
        )

    def set_color(self, color: tuple[int, int, int], *, emit: bool = False) -> None:
        self._color = tuple(int(c) & 0xFF for c in color)
        self._refresh()
        if emit:
            self.colorChanged.emit(self._color)

    def color(self) -> tuple[int, int, int]:
        return self._color

    def _pick(self) -> None:
        r, g, b = self._color
        chosen = QColorDialog.getColor(QColor(r, g, b), self, "Цвет подсветки")
        if chosen.isValid():
            self.set_color((chosen.red(), chosen.green(), chosen.blue()), emit=True)


# ---------------------------------------------------------------------------
# Equalizer curve
# ---------------------------------------------------------------------------


class EQCurve(QWidget):
    """Interactive 10-band response curve.

    Drag a handle vertically to change a band, double-click it to reset,
    use the wheel for fine steps.  Values are in dB.
    """

    bandsChanged = Signal(list)
    editingFinished = Signal(list)

    def __init__(
        self,
        frequencies: tuple[int, ...],
        labels: tuple[str, ...],
        minimum: float = -12.0,
        maximum: float = 12.0,
        step: float = 0.5,
        parent=None,
    ):
        super().__init__(parent)
        self.frequencies = frequencies
        self.labels = labels
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self._bands = [0.0] * len(frequencies)
        self._enabled = True
        self._active: int | None = None
        self._hover: int | None = None
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # -- public ------------------------------------------------------------

    def bands(self) -> list[float]:
        return list(self._bands)

    def set_bands(self, bands: list[float], *, emit: bool = False) -> None:
        self._bands = [
            max(self.minimum, min(self.maximum, round(float(v) / self.step) * self.step))
            for v in bands
        ][: len(self.frequencies)]
        self.update()
        if emit:
            self.bandsChanged.emit(self.bands())

    def set_enabled_curve(self, enabled: bool) -> None:
        self._enabled = enabled
        self.update()

    # -- geometry ----------------------------------------------------------

    def _plot_rect(self) -> QRectF:
        return QRectF(34, 12, self.width() - 44, self.height() - 42)

    def _x_of(self, index: int) -> float:
        rect = self._plot_rect()
        lo = math.log10(self.frequencies[0])
        hi = math.log10(self.frequencies[-1])
        return rect.left() + rect.width() * (math.log10(self.frequencies[index]) - lo) / (hi - lo)

    def _y_of(self, gain: float) -> float:
        rect = self._plot_rect()
        return rect.top() + rect.height() * (self.maximum - gain) / (self.maximum - self.minimum)

    def _gain_of(self, y: float) -> float:
        rect = self._plot_rect()
        value = self.maximum - (y - rect.top()) / rect.height() * (self.maximum - self.minimum)
        return max(self.minimum, min(self.maximum, round(value / self.step) * self.step))

    def _nearest(self, x: float) -> int:
        return min(range(len(self.frequencies)), key=lambda i: abs(self._x_of(i) - x))

    def _response(self, count: int = 240) -> list[QPointF]:
        rect = self._plot_rect()
        xs = [math.log10(self.frequencies[i]) for i in range(len(self.frequencies))]
        ys = list(self._bands)
        slopes = _pchip_slopes(xs, ys)
        points: list[QPointF] = []
        lo, hi = xs[0], xs[-1]
        for step in range(count + 1):
            x = lo + (hi - lo) * step / count
            gain = _pchip_eval(xs, ys, slopes, x)
            px = rect.left() + rect.width() * (x - lo) / (hi - lo)
            points.append(QPointF(px, self._y_of(gain)))
        return points

    # -- painting ----------------------------------------------------------

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0d1116"))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

        font = QFont(self.font())
        font.setPointSizeF(8.0)
        painter.setFont(font)

        # horizontal grid
        for gain in (self.maximum, 6.0, 0.0, -6.0, self.minimum):
            y = self._y_of(gain)
            pen = QPen(QColor("#2b3440"))
            pen.setWidth(1)
            if gain == 0.0:
                pen.setColor(QColor("#3d4a59"))
            painter.setPen(pen)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(theme.DIM))
            text = "0" if gain == 0 else f"{gain:+.0f}"
            painter.drawText(QRectF(0, y - 8, rect.left() - 6, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)

        # vertical band grid + labels
        for index, label in enumerate(self.labels):
            x = self._x_of(index)
            painter.setPen(QPen(QColor("#232b35")))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.setPen(QColor(theme.DIM))
            painter.drawText(
                QRectF(x - 20, rect.bottom() + 4, 40, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        curve = self._response()
        area = QPainterPath()
        area.moveTo(curve[0].x(), self._y_of(0))
        for point in curve:
            area.lineTo(point)
        area.lineTo(curve[-1].x(), self._y_of(0))
        area.closeSubpath()

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        top = QColor(theme.CURVE_TOP)
        bottom = QColor(theme.CURVE_BOTTOM)
        top.setAlpha(90 if self._enabled else 30)
        bottom.setAlpha(18 if self._enabled else 8)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(area)

        path = QPainterPath(curve[0])
        for point in curve[1:]:
            path.lineTo(point)
        pen = QPen(QColor(theme.TEAL) if self._enabled else QColor(theme.DIM))
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # handles
        for index, gain in enumerate(self._bands):
            x = self._x_of(index)
            y = self._y_of(gain)
            active = index == self._active or index == self._hover
            radius = 6.5 if active else 4.5
            painter.setPen(QPen(QColor(theme.TEAL), 2 if active else 1.4))
            painter.setBrush(QColor("#ffffff") if active else QColor("#121820"))
            painter.drawEllipse(QPointF(x, y), radius, radius)
            if active:
                text = f"{gain:+.1f}"
                painter.setPen(QColor("#ffffff"))
                painter.drawText(
                    QRectF(x - 30, y - 30, 60, 16),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    text,
                )
        painter.end()

    # -- interaction -------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._nearest(event.position().x())
            self._active = index
            self._apply(event.position().y(), index)
        elif event.button() == Qt.MouseButton.RightButton:
            self.set_bands([0.0] * len(self.frequencies), emit=True)
            self.editingFinished.emit(self.bands())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        index = self._nearest(event.position().x())
        self._bands[index] = 0.0
        self.update()
        self.bandsChanged.emit(self.bands())
        self.editingFinished.emit(self.bands())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._active is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._apply(event.position().y(), self._active)
        else:
            hover = self._nearest(event.position().x())
            if hover != self._hover:
                self._hover = hover
                self.update()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        if self._active is not None:
            self._active = None
            self.update()
            self.editingFinished.emit(self.bands())

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        index = self._nearest(event.position().x())
        delta = self.step if event.angleDelta().y() > 0 else -self.step
        self._bands[index] = max(self.minimum, min(self.maximum, self._bands[index] + delta))
        self.update()
        self.bandsChanged.emit(self.bands())
        self.editingFinished.emit(self.bands())

    def _apply(self, y: float, index: int) -> None:
        gain = self._gain_of(y)
        if gain != self._bands[index]:
            self._bands[index] = gain
            self.update()
            self.bandsChanged.emit(self.bands())


# ---------------------------------------------------------------------------
# Monotone cubic interpolation (PCHIP) for a natural-looking EQ curve
# ---------------------------------------------------------------------------


def _pchip_slopes(xs: list[float], ys: list[float]) -> list[float]:
    n = len(xs)
    if n < 2:
        return [0.0] * n
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    delta = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    slopes = [0.0] * n
    slopes[0] = delta[0]
    slopes[-1] = delta[-1]
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0:
            slopes[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            slopes[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
    return slopes


def _pchip_eval(xs: list[float], ys: list[float], slopes: list[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    h = xs[hi] - xs[lo]
    t = (x - xs[lo]) / h
    t2 = t * t
    t3 = t2 * t
    h00 = 2 * t3 - 3 * t2 + 1
    h10 = t3 - 2 * t2 + t
    h01 = -2 * t3 + 3 * t2
    h11 = t3 - t2
    return h00 * ys[lo] + h10 * h * slopes[lo] + h01 * ys[hi] + h11 * h * slopes[hi]
