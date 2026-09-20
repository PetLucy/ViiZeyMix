from __future__ import annotations

import math
import sys

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from audio_backend import AudioNode, PipeWireBackend
from effects import format_intellipan, map_intellipan
from version import __version__


APP_QSS = """
QWidget {
    background: #17131d;
    color: #f4ecf8;
    font-family: Inter, "Noto Sans", sans-serif;
    font-size: 13px;
}
QMainWindow { background: #110e16; }
#TopBar { background: #201827; border-bottom: 1px solid #3b2c47; }
#Title { font-size: 23px; font-weight: 750; }
#Subtle { color: #a99db2; }
#ChannelStrip {
    background: #211a28;
    border: 1px solid #44334f;
    border-radius: 14px;
}
#BusCard {
    background: #201827;
    border: 1px solid #51395d;
    border-radius: 14px;
}
#MeterWell {
    background: #0d0a10;
    border: 1px solid #3c3045;
    border-radius: 6px;
}
#MeterFill { background: #d35ca9; border-radius: 4px; }
QPushButton {
    background: #34273e;
    border: 1px solid #594067;
    border-radius: 7px;
    padding: 6px 9px;
}
QPushButton:hover { background: #443050; }
QPushButton:checked { background: #9d4f92; border-color: #d97fc9; }
QPushButton#MuteButton:checked { background: #b24763; border-color: #ef718e; }
QTabWidget::pane { border: 0; background: #17131d; }
QTabBar::tab {
    background: #201827;
    color: #bdb0c6;
    border: 1px solid #3b2c47;
    border-bottom: 0;
    padding: 11px 24px;
    min-width: 155px;
}
QTabBar::tab:selected {
    background: #382541;
    color: #fff4fd;
    border-top: 2px solid #dd75c7;
}
QSlider::groove:vertical { width: 7px; background: #0e0b12; border-radius: 3px; }
QSlider::sub-page:vertical { background: #4e395c; border-radius: 3px; }
QSlider::add-page:vertical { background: #d35ca9; border-radius: 3px; }
QSlider::handle:vertical {
    height: 15px;
    margin: 0 -5px;
    background: #f0b8e5;
    border: 1px solid #ffffff;
    border-radius: 7px;
}
QSlider::groove:horizontal { height: 6px; background: #0e0b12; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #9d4f92; border-radius: 3px; }
QSlider::handle:horizontal {
    width: 13px;
    margin: -4px 0;
    background: #f0b8e5;
    border: 1px solid #ffffff;
    border-radius: 6px;
}
QScrollArea { border: 0; }
QComboBox {
    background: #2a2032;
    border: 1px solid #594067;
    border-radius: 7px;
    padding: 6px 8px;
}
QComboBox:disabled { color: #8d8294; }
"""


class IntelliPan(QWidget):
    """Three-mode XY controller modelled after VoiceMeeter's IntelliPan."""

    effect_changed = Signal(str, float, float, dict)
    MODES = ("Color", "Modulation", "Position")

    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(205, 190)
        self.setCursor(Qt.CrossCursor)
        self.setToolTip(
            "Drag to shape the effect. Right-click cycles modes. "
            "Double-click resets the current mode to neutral."
        )
        self.mode_index = 0
        self.positions = {mode: QPointF(0.0, 0.0) for mode in self.MODES}
        self.dragging = False

    @property
    def mode(self) -> str:
        return self.MODES[self.mode_index]

    def plot_rect(self) -> QRectF:
        return QRectF(9, 34, self.width() - 18, self.height() - 43)

    def cycle_mode(self) -> None:
        self.mode_index = (self.mode_index + 1) % len(self.MODES)
        self.update()
        self.emit_state()

    def reset_current(self) -> None:
        self.positions[self.mode] = QPointF(0.0, 0.0)
        self.update()
        self.emit_state()

    def set_from_mouse(self, point: QPointF) -> None:
        rect = self.plot_rect()
        x = max(rect.left(), min(point.x(), rect.right()))
        y = max(rect.top(), min(point.y(), rect.bottom()))
        nx = ((x - rect.left()) / rect.width()) * 2.0 - 1.0
        ny = 1.0 - ((y - rect.top()) / rect.height()) * 2.0
        self.positions[self.mode] = QPointF(nx, ny)
        self.update()
        self.emit_state()

    def parameters(self) -> dict[str, float | str]:
        pos = self.positions[self.mode]
        return map_intellipan(self.mode, pos.x(), pos.y())

    def summary(self) -> str:
        return format_intellipan(self.mode, self.parameters())

    def emit_state(self) -> None:
        pos = self.positions[self.mode]
        self.effect_changed.emit(self.mode, pos.x(), pos.y(), self.parameters())

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            self.cycle_mode()
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.set_from_mouse(event.position())

    def mouseMoveEvent(self, event) -> None:
        if self.dragging:
            self.set_from_mouse(event.position())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.reset_current()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        panel = self.plot_rect()

        painter.setPen(QPen(QColor("#5a4764"), 1))
        painter.setBrush(QColor("#110e16"))
        painter.drawRoundedRect(panel, 9, 9)

        painter.setFont(QFont("Noto Sans", 8, QFont.DemiBold))
        painter.setPen(QColor("#d9cce1"))
        painter.drawText(QRectF(9, 5, 105, 22), Qt.AlignLeft | Qt.AlignVCenter, self.mode.upper())
        painter.setPen(QColor("#9d8ea6"))
        painter.drawText(QRectF(116, 5, 80, 22), Qt.AlignRight | Qt.AlignVCenter, "INTELLIPAN")

        for index, mode in enumerate(self.MODES):
            active = self.positions[mode].manhattanLength() > 0.015
            color = QColor("#ef6d72") if active else QColor("#5b5362")
            if index == self.mode_index and not active:
                color = QColor("#b7aabe")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(91 + index * 10, 16), 3.5, 3.5)

        painter.setPen(QPen(QColor("#4a3a53"), 1))
        if self.mode == "Position":
            center = QPointF(panel.center().x(), panel.bottom())
            radius = panel.width() * 0.42
            painter.drawArc(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2), 0, 180 * 16)
            painter.drawArc(QRectF(center.x() - radius / 2, center.y() - radius / 2, radius, radius), 0, 180 * 16)
            painter.drawLine(QPointF(panel.center().x(), panel.top()), QPointF(panel.center().x(), panel.bottom()))
            painter.setPen(QColor("#887a90"))
            painter.drawText(QRectF(panel.left() + 7, panel.bottom() - 22, 18, 18), "L")
            painter.drawText(QRectF(panel.right() - 18, panel.bottom() - 22, 18, 18), "R")
        else:
            painter.drawLine(QPointF(panel.center().x(), panel.top()), QPointF(panel.center().x(), panel.bottom()))
            painter.drawLine(QPointF(panel.left(), panel.center().y()), QPointF(panel.right(), panel.center().y()))
            if self.mode == "Modulation":
                for fraction in (0.25, 0.75):
                    painter.drawLine(
                        QPointF(panel.left() + panel.width() * fraction, panel.top()),
                        QPointF(panel.left() + panel.width() * fraction, panel.bottom()),
                    )
                    painter.drawLine(
                        QPointF(panel.left(), panel.top() + panel.height() * fraction),
                        QPointF(panel.right(), panel.top() + panel.height() * fraction),
                    )

        pos = self.positions[self.mode]
        px = panel.left() + ((pos.x() + 1.0) / 2.0) * panel.width()
        py = panel.top() + ((1.0 - pos.y()) / 2.0) * panel.height()
        painter.setPen(QPen(QColor("#ffd7ef"), 1))
        painter.setBrush(QColor("#e85fae"))
        painter.drawRoundedRect(QRectF(px - 7, py - 7, 14, 14), 4, 4)


class IntelliPanControl(QWidget):
    effect_changed = Signal(str, float, float, dict)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.pad = IntelliPan()
        self.pad.effect_changed.connect(self._changed)
        layout.addWidget(self.pad, 0, Qt.AlignCenter)
        self.readout = QLabel(self.pad.summary())
        self.readout.setObjectName("Subtle")
        self.readout.setAlignment(Qt.AlignCenter)
        self.readout.setFixedHeight(34)
        layout.addWidget(self.readout)
        help_label = QLabel("drag • right-click mode • double-click reset")
        help_label.setObjectName("Subtle")
        help_label.setAlignment(Qt.AlignCenter)
        help_label.setStyleSheet("font-size: 9px;")
        layout.addWidget(help_label)

    def _changed(self, mode: str, x: float, y: float, parameters: dict) -> None:
        self.readout.setText(self.pad.summary())
        self.effect_changed.emit(mode, x, y, parameters)


class VerticalMeter(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(24, 170)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.well = QFrame()
        self.well.setObjectName("MeterWell")
        self.well.setFixedSize(24, 170)
        self.fill = QFrame(self.well)
        self.fill.setObjectName("MeterFill")
        self.fill.setGeometry(4, 164, 16, 0)
        outer.addWidget(self.well)

    def set_level(self, level: float) -> None:
        h = int(160 * max(0.0, min(level, 1.0)))
        self.fill.setGeometry(4, 164 - h, 16, h)


class ChannelStrip(QFrame):
    route_requested = Signal(object, str, bool)

    def __init__(
        self,
        node: AudioNode,
        backend: PipeWireBackend,
        with_intellipan: bool,
        meter_target: AudioNode | None,
    ) -> None:
        super().__init__()
        self.node = node
        self.backend = backend
        self.setObjectName("ChannelStrip")
        self.setFixedWidth(235)
        self.routed_targets: dict[str, int] = {}
        self.meter_target = meter_target
        self.has_meter = meter_target is not None and backend.start_meter(meter_target)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 13, 13, 13)
        layout.setSpacing(8)

        name = QLabel(node.display_name)
        name.setAlignment(Qt.AlignCenter)
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(name)
        subtitle = QLabel(node.subtitle)
        subtitle.setObjectName("Subtle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setFixedHeight(34)
        layout.addWidget(subtitle)

        if with_intellipan:
            self.intellipan = IntelliPanControl()
            self.intellipan.effect_changed.connect(self.on_effect_changed)
            layout.addWidget(self.intellipan)
            self.effect_status = QLabel("Color • Modulation • Position: live DSP")
            self.effect_status.setObjectName("Subtle")
            self.effect_status.setAlignment(Qt.AlignCenter)
            self.effect_status.setStyleSheet("font-size: 9px;")
            layout.addWidget(self.effect_status)

        center = QHBoxLayout()
        center.setAlignment(Qt.AlignCenter)
        if self.has_meter:
            self.meter = VerticalMeter()
            self.meter.setToolTip("Live peak level from PipeWire (-60 to 0 dBFS)")
            center.addWidget(self.meter)
        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        current_level = backend.get_volume(node.id)
        fader_percent = round(min(current_level, 1.0) * 100.0)
        gain_tenths = (
            round(min(12.0, 20.0 * math.log10(current_level)) * 10.0)
            if current_level > 1.0
            else 0
        )
        self.slider.setValue(fader_percent)
        self.slider.setFixedHeight(170)
        self.slider.setToolTip("Volume fader: 0-100% attenuation")
        center.addWidget(self.slider)
        layout.addLayout(center)
        self.volume_label = QLabel(f"{fader_percent}%")
        self.volume_label.setAlignment(Qt.AlignCenter)
        self.volume_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.volume_label)

        gain_row = QHBoxLayout()
        gain_title = QLabel("GAIN")
        gain_title.setObjectName("Subtle")
        gain_title.setStyleSheet("font-size: 9px; font-weight: 700;")
        gain_row.addWidget(gain_title)
        self.gain_slider = QSlider(Qt.Horizontal)
        self.gain_slider.setRange(0, 120)
        self.gain_slider.setValue(gain_tenths)
        self.gain_slider.setToolTip("Post-fader boost: 0 to +12 dB")
        gain_row.addWidget(self.gain_slider, 1)
        self.gain_label = QLabel(f"+{gain_tenths / 10.0:.1f} dB")
        self.gain_label.setFixedWidth(53)
        self.gain_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        gain_row.addWidget(self.gain_label)
        layout.addLayout(gain_row)

        self.slider.valueChanged.connect(self.on_volume)
        self.gain_slider.valueChanged.connect(self.on_gain)
        self.mute = QPushButton("MUTE")
        self.mute.setObjectName("MuteButton")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self.on_mute)
        layout.addWidget(self.mute)

        if with_intellipan:
            route_grid = QGridLayout()
            self.route_buttons: dict[str, QPushButton] = {}
            for index, bus in enumerate(("A1", "A2", "A3", "B1", "B2", "B3")):
                button = QPushButton(bus)
                button.setCheckable(True)
                button.setEnabled(False)
                button.setToolTip(f"Assign an output to {bus} first")
                button.toggled.connect(
                    lambda checked, code=bus: self.route_requested.emit(self, code, checked)
                )
                self.route_buttons[bus] = button
                route_grid.addWidget(button, index // 3, index % 3)
            layout.addLayout(route_grid)

        tag = QLabel(node.media_class)
        tag.setObjectName("Subtle")
        tag.setAlignment(Qt.AlignCenter)
        tag.setWordWrap(True)
        layout.addWidget(tag)

    def on_effect_changed(self, mode: str, x: float, y: float, parameters: dict) -> None:
        self.backend.set_intellipan_state(self.node.id, mode, x, y, parameters)
        result = self.backend.set_intellipan_dsp(
            self.node.id,
            mode,
            x,
            y,
            list(self.routed_targets.values()),
        )
        if result.success:
            active_modes = [
                effect_mode
                for effect_mode, state in self.backend.intellipan_state.get(self.node.id, {}).items()
                if abs(float(state.get("x", 0.0))) > 0.001 or
                abs(float(state.get("y", 0.0))) > 0.001
            ]
            self.effect_status.setText(
                "DSP: " + " + ".join(active_modes)
                if active_modes
                else "IntelliPan DSP: bypassed"
            )
        else:
            self.effect_status.setText("IntelliPan DSP: unavailable")
    def set_bus_targets(self, targets: dict[str, AudioNode | None]) -> None:
        if not hasattr(self, "route_buttons"):
            return
        for code, button in self.route_buttons.items():
            target = targets.get(code)
            button.setEnabled(target is not None)
            button.setToolTip(
                f"Route {self.node.display_name} to {target.display_name}"
                if target is not None
                else f"No output assigned to {code}"
            )

    def restore_intellipan_state(self, states: dict[str, dict]) -> None:
        if not hasattr(self, "intellipan"):
            return
        for mode, state in states.items():
            if mode in self.intellipan.pad.positions:
                self.intellipan.pad.positions[mode] = QPointF(
                    float(state.get("x", 0.0)),
                    float(state.get("y", 0.0)),
                )
        self.intellipan.pad.update()
        self.intellipan.readout.setText(self.intellipan.pad.summary())
        active_modes = [
            mode
            for mode, state in states.items()
            if abs(float(state.get("x", 0.0))) > 0.001 or
            abs(float(state.get("y", 0.0))) > 0.001
        ]
        if active_modes:
            self.effect_status.setText("DSP: " + " + ".join(active_modes))

    def clear_route(self, code: str) -> None:
        if not hasattr(self, "route_buttons"):
            return
        button = self.route_buttons[code]
        if button.isChecked():
            button.setChecked(False)

    def restore_route_button(self, code: str, checked: bool) -> None:
        button = self.route_buttons[code]
        button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(False)

    def on_volume(self, value: int) -> None:
        self.volume_label.setText(f"{value}%")
        self.apply_volume()

    def on_gain(self, value: int) -> None:
        self.gain_label.setText(f"+{value / 10.0:.1f} dB")
        self.apply_volume()

    def apply_volume(self) -> None:
        if not self.node.is_demo:
            fader = self.slider.value() / 100.0
            gain = 10.0 ** ((self.gain_slider.value() / 10.0) / 20.0)
            self.backend.set_volume(self.node.id, fader * gain)

    def on_mute(self, muted: bool) -> None:
        if not self.node.is_demo:
            self.backend.set_mute(self.node.id, muted)

    def update_meter(self) -> None:
        if not self.has_meter or self.meter_target is None:
            return
        level = self.backend.read_meter_level(self.meter_target.id)
        if level is None:
            self.has_meter = False
            self.meter.hide()
            return
        self.meter.set_level(0.0 if self.mute.isChecked() else level)


class BusCard(QFrame):
    target_changed = Signal(str, object)

    def __init__(
        self,
        code: str,
        title: str,
        subtitle: str,
        kind: str,
        choices: list[AudioNode],
        target: AudioNode | None,
    ) -> None:
        super().__init__()
        self.setObjectName("BusCard")
        self.code = code
        self.setFixedSize(235, 185)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 14, 15, 14)
        code_label = QLabel(code)
        code_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #efb6e5;")
        layout.addWidget(code_label)
        kind_label = QLabel(kind.upper())
        kind_label.setObjectName("Subtle")
        kind_label.setStyleSheet("font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(kind_label)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        sub = QLabel(subtitle)
        sub.setObjectName("Subtle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addStretch(1)
        self.selector = QComboBox()
        if code.startswith("A"):
            self.selector.addItem("Not assigned", None)
            for node in choices:
                self.selector.addItem(node.display_name, node)
            if target is not None:
                index = self.selector.findData(target)
                if index >= 0:
                    self.selector.setCurrentIndex(index)
            self.selector.currentIndexChanged.connect(self._selection_changed)
        else:
            self.selector.addItem(
                target.display_name if target is not None else "Virtual sink unavailable",
                target,
            )
            self.selector.setEnabled(False)
        layout.addWidget(self.selector)

    def _selection_changed(self, _index: int) -> None:
        self.target_changed.emit(self.code, self.selector.currentData())


def make_scroll_host() -> tuple[QScrollArea, QWidget, QHBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    host = QWidget()
    layout = QHBoxLayout(host)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    scroll.setWidget(host)
    return scroll, host, layout


def make_grid_scroll_host() -> tuple[QScrollArea, QWidget, QGridLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    host = QWidget()
    layout = QGridLayout(host)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setHorizontalSpacing(12)
    layout.setVerticalSpacing(12)
    layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
    scroll.setWidget(host)
    return scroll, host, layout


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.backend = PipeWireBackend()
        self.discovery_error_shown = False
        self.channel_strips: list[ChannelStrip] = []
        self.input_strips: list[ChannelStrip] = []
        self.bus_targets: dict[str, AudioNode | None] = {
            code: None for code in ("A1", "A2", "A3", "B1", "B2", "B3")
        }
        self.saved_bus_names = self.backend.load_bus_assignments()
        self.setWindowTitle("ViiZeyMix")
        self.resize(1450, 870)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(18, 12, 18, 12)
        title_wrap = QVBoxLayout()
        title = QLabel("ViiZeyMix")
        title.setObjectName("Title")
        title_wrap.addWidget(title)
        subtitle = QLabel("PipeWire mixer • inputs, sources, outputs, and buses")
        subtitle.setObjectName("Subtle")
        title_wrap.addWidget(subtitle)
        top_layout.addLayout(title_wrap)
        top_layout.addStretch(1)
        refresh = QPushButton("Refresh devices")
        refresh.clicked.connect(self.load_nodes)
        top_layout.addWidget(refresh)
        root_layout.addWidget(top)

        self.tabs = QTabWidget()
        self.inputs_scroll, self.inputs_host, self.inputs_layout = make_scroll_host()
        self.outputs_scroll, self.outputs_host, self.outputs_layout = make_grid_scroll_host()
        self.tabs.addTab(self.inputs_scroll, "Inputs & Sources")
        self.tabs.addTab(self.outputs_scroll, "Outputs & Buses")
        self.tabs.setCurrentIndex(0)
        root_layout.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_meters)
        self.timer.start(100)
        self.load_nodes()

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "ViiZeyMix", message)

    @staticmethod
    def clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def load_nodes(self) -> None:
        previous_names = {
            code: target.name
            for code, target in self.bus_targets.items()
            if target is not None
        }
        previous_names = {**self.saved_bus_names, **previous_names}
        self.backend.shutdown_meters()
        virtual_bus_errors = self.backend.ensure_virtual_buses()
        self.clear_layout(self.inputs_layout)
        self.clear_layout(self.outputs_layout)
        self.channel_strips.clear()
        self.input_strips.clear()
        nodes = self.backend.enumerate_nodes()
        if self.backend.last_discovery_error and not self.discovery_error_shown:
            self.discovery_error_shown = True
            message = self.backend.last_discovery_error
            QTimer.singleShot(
                0,
                lambda detail=message: self.show_error(
                    "Live PipeWire discovery failed, so demo devices are being shown.\n\n"
                    + detail
                ),
            )
        input_nodes = sorted(
            (
                n
                for n in nodes
                if n.is_input_or_source
                and not n.is_viizeymix_bus
                and not n.is_viizeymix_dsp
                and not n.is_viizeymix_meter
                and not n.is_monitor
            ),
            key=lambda n: n.display_name.lower(),
        )
        self.backend.cleanup_dsp_sessions({node.id for node in input_nodes})
        all_outputs = sorted((n for n in nodes if n.is_output), key=lambda n: n.display_name.lower())
        output_nodes = [node for node in all_outputs if not node.is_viizeymix_bus]
        virtual_outputs = {
            node.virtual_bus_code: node
            for node in all_outputs
            if node.virtual_bus_code is not None
        }
        monitor_nodes = [node for node in nodes if node.is_monitor]
        monitors_by_sink_name = {
            node.name.removesuffix(".monitor"): node
            for node in monitor_nodes
            if node.name.endswith(".monitor")
        }

        by_name = {node.name: node for node in output_nodes}
        for code in ("A1", "A2", "A3"):
            preserved = by_name.get(previous_names.get(code, ""))
            self.bus_targets[code] = preserved
        for code in ("B1", "B2", "B3"):
            self.bus_targets[code] = virtual_outputs.get(code)

        if virtual_bus_errors:
            QTimer.singleShot(0, lambda: self.show_error(virtual_bus_errors[0]))

        for node in input_nodes[:12]:
            strip = ChannelStrip(
                node,
                self.backend,
                with_intellipan=True,
                meter_target=node,
            )
            strip.restore_intellipan_state(self.backend.intellipan_state.get(node.id, {}))
            strip.route_requested.connect(self.on_route_requested)
            self.inputs_layout.addWidget(strip)
            self.channel_strips.append(strip)
            self.input_strips.append(strip)
        self.inputs_layout.addStretch(1)

        bus_specs = (
            ("A1", "Hardware Output 1", "Primary monitor bus", "hardware bus"),
            ("A2", "Hardware Output 2", "Secondary monitor bus", "hardware bus"),
            ("A3", "Hardware Output 3", "Optional monitor bus", "hardware bus"),
            ("B1", "Stream Mix", "Virtual output for OBS", "virtual bus"),
            ("B2", "Chat Mix", "Virtual output for chat apps", "virtual bus"),
            ("B3", "Record Mix", "Virtual recording bus", "virtual bus"),
        )
        for index, (code, title, subtitle, kind) in enumerate(bus_specs):
            card = BusCard(
                code,
                title,
                subtitle,
                kind,
                output_nodes,
                self.bus_targets[code],
            )
            card.target_changed.connect(self.on_bus_target_changed)
            self.outputs_layout.addWidget(card, index // 3, index % 3, Qt.AlignTop)

        outputs_title = QLabel("OUTPUT DEVICES")
        outputs_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #c9b8d3;")
        self.outputs_layout.addWidget(outputs_title, 2, 0, 1, 3)
        for index, node in enumerate(output_nodes[:12]):
            strip = ChannelStrip(
                node,
                self.backend,
                with_intellipan=False,
                meter_target=monitors_by_sink_name.get(node.name),
            )
            self.outputs_layout.addWidget(strip, 3 + index // 3, index % 3, Qt.AlignTop)
            self.channel_strips.append(strip)

        for strip in self.input_strips:
            strip.set_bus_targets(self.bus_targets)
        self.restore_route_states()

    def restore_route_states(self) -> None:
        if not self.backend.is_live:
            return
        try:
            state = self.backend.graph_state()
        except RuntimeError:
            return
        for strip in self.input_strips:
            for code, target in self.bus_targets.items():
                if target is None:
                    continue
                if self.backend.route_is_active_for_source(state, strip.node.id, target.id):
                    strip.routed_targets[code] = target.id
                    strip.restore_route_button(code, True)

    def on_bus_target_changed(self, code: str, target: AudioNode | None) -> None:
        old_target = self.bus_targets.get(code)
        if old_target == target:
            return
        for strip in self.input_strips:
            strip.clear_route(code)
        self.bus_targets[code] = target
        if code.startswith("A"):
            self.saved_bus_names = {
                bus_code: bus_target.name
                for bus_code, bus_target in self.bus_targets.items()
                if bus_code.startswith("A") and bus_target is not None
            }
            try:
                self.backend.save_bus_assignments(self.saved_bus_names)
            except OSError as error:
                self.show_error(f"Could not save bus assignment: {error}")
        for strip in self.input_strips:
            strip.set_bus_targets(self.bus_targets)
    def on_route_requested(self, strip: ChannelStrip, code: str, enabled: bool) -> None:
        target = self.bus_targets.get(code)
        target_id = target.id if target is not None else None
        if not enabled:
            target_id = strip.routed_targets.get(code, target_id)
        if target_id is None:
            strip.restore_route_button(code, not enabled)
            self.show_error(f"Assign an output to {code} first")
            return

        result = self.backend.set_route(strip.node.id, target_id, enabled)
        if not result.success:
            strip.restore_route_button(code, not enabled)
            self.show_error(result.message)
            return

        if enabled:
            strip.routed_targets[code] = target_id
        else:
            strip.routed_targets.pop(code, None)
    def update_meters(self) -> None:
        for strip in self.channel_strips:
            strip.update_meter()

    def closeEvent(self, event) -> None:
        for strip in self.input_strips:
            self.backend.deactivate_intellipan_dsp(
                strip.node.id,
                list(strip.routed_targets.values()),
            )
        self.backend.shutdown_meters()
        self.backend.shutdown_dsp()
        super().closeEvent(event)


def main() -> int:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"ViiZeyMix {__version__}")
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("ViiZeyMix")
    app.setApplicationDisplayName("ViiZeyMix")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("PetLucy")
    app.setDesktopFileName("io.github.petlucy.viizeymix")
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
