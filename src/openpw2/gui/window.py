"""Compact instrument panel. Widget state is always confirmed peer state."""

from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from openpw2 import __version__
from openpw2.client import ConnectionConfig, block_reason

from . import settings
from .bridge import Bridge
from .theme import set_tone, stylesheet


def label(text="", name=None):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


def card():
    widget = QFrame()
    widget.setObjectName("card")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(20, 14, 20, 14)
    layout.setSpacing(9)
    return widget, layout


class Meter(QFrame):
    def __init__(self, title, subtitle):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.addWidget(label(title, "eyebrow"))
        self.value = label("—", "meterValue")
        layout.addWidget(self.value)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        layout.addWidget(label(subtitle, "muted"))

    def update_value(self, text, percent=None, raw=None):
        self.value.setText(text)
        self.bar.setValue(round(max(0, min(100, percent)) * 10) if percent is not None else 0)
        self.bar.setEnabled(percent is not None)
        self.setToolTip(
            f"Display position: {percent:.1f}% · raw: {raw}" if percent is not None else "Unavailable"
        )


class Window(QMainWindow):
    def __init__(self, *, demo=False, bridge=None):
        super().__init__()
        self.setWindowTitle("openpw2 · IC-PW2 remote")
        self.resize(1080, 840)
        self.setMinimumSize(850, 650)
        self.setStyleSheet(stylesheet())
        self.bridge = bridge or Bridge()
        self.state = {}
        self.received = 0.0
        self.busy = False
        self.is_demo = False
        self.mains_v = None
        self.buttons = []
        self._shutdown = False
        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(24, 20, 24, 15)
        outer.setSpacing(14)
        header = QHBoxLayout()
        name = QVBoxLayout()
        name.addWidget(label("openpw2", "brand"))
        name.addWidget(label("IC-PW2  /  INDEPENDENT LAN REMOTE", "eyebrow"))
        header.addLayout(name)
        header.addStretch()
        self.connection_badge = label("DISCONNECTED", "status")
        header.addWidget(self.connection_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.demo_button = QPushButton("Try demo")
        self.demo_button.clicked.connect(self.start_demo)
        header.addWidget(self.demo_button)
        self.demo_tx = QPushButton("Simulate TX")
        self.demo_tx.setCheckable(True)
        self.demo_tx.toggled.connect(self.bridge.demo_tx)
        header.addWidget(self.demo_tx)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("primary")
        self.connect_button.clicked.connect(self.connection_action)
        header.addWidget(self.connect_button)
        outer.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._dashboard(), "Monitor && control")
        self.tabs.addTab(self._connection(), "Connection")
        self.tabs.addTab(self._reference(), "Reference")
        outer.addWidget(self.tabs, 1)
        self.notice = label("Connect to your PW2, or explore the interface in demo mode.", "notice")
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        footer = QHBoxLayout()
        footer.addWidget(label(f"openpw2 {__version__}  ·  MIT  ·  Independent project", "footer"))
        footer.addStretch()
        self.age_label = label("No telemetry", "footer")
        footer.addWidget(self.age_label)
        outer.addLayout(footer)
        self.setCentralWidget(body)
        self.bridge.state_changed.connect(self.update_state)
        self.bridge.message.connect(self.show_message)
        self.bridge.busy_changed.connect(self.set_busy)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(150)
        self.refresh()
        if demo:
            QTimer.singleShot(0, self.start_demo)

    def _dashboard(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        hero = QHBoxLayout()
        power, power_layout = card()
        row = QHBoxLayout()
        row.addWidget(label("FORWARD POWER", "eyebrow"))
        row.addStretch()
        self.level_label = label("LIMIT —", "muted")
        row.addWidget(self.level_label)
        power_layout.addLayout(row)
        self.power_value = label("—", "power")
        self.power_value.setObjectName("power")
        power_layout.addWidget(self.power_value)
        self.po_bar = QProgressBar()
        self.po_bar.setRange(0, 1000)
        self.po_bar.setTextVisible(False)
        power_layout.addWidget(self.po_bar)
        self.power_hint = label("≈ Display-derived watts · 0 … 1,500 W scale", "muted")
        power_layout.addWidget(self.power_hint)
        hero.addWidget(power, 3)
        frequency, frequency_layout = card()
        self.frequency_card = frequency
        row = QHBoxLayout()
        self.mode_label = label("—", "mode")
        row.addWidget(self.mode_label)
        row.addStretch()
        self.tx_label = label("—", "status")
        row.addWidget(self.tx_label)
        frequency_layout.addLayout(row)
        self.frequency_label = label("—", "frequency")
        frequency_layout.addWidget(self.frequency_label)
        self.routing_label = label("Input —   ·   Antenna —   ·   Band —", "muted")
        frequency_layout.addWidget(self.routing_label)
        self.other_input = label("", "muted")
        frequency_layout.addWidget(self.other_input)
        hero.addWidget(frequency, 3)
        layout.addLayout(hero)
        grid = QGridLayout()
        grid.setSpacing(12)
        self.meters = {}
        for col, (key, title, subtitle) in enumerate(
            [
                ("swr", "SWR", "Reference interval 1.1–3.0"),
                ("id", "DRAIN CURRENT", "Id · approximate amperes"),
                ("vd", "DRAIN VOLTAGE", "Vd · approximate volts"),
                ("alc", "ALC", "Relative display position"),
            ]
        ):
            meter = Meter(title, subtitle)
            self.meters[key] = meter
            grid.addWidget(meter, 0, col)
        layout.addLayout(grid)
        thermal = QHBoxLayout()
        self.meters["temp"] = Meter("PA TEMPERATURE", "COOL                                              HOT")
        thermal.addWidget(self.meters["temp"], 2)
        intake, intake_layout = card()
        intake_layout.addWidget(label("INTAKE AIR", "eyebrow"))
        self.intake_label = label("— °C   /   — %", "meterValue")
        intake_layout.addWidget(self.intake_label)
        self.clock_label = label("PW2 clock —", "muted")
        intake_layout.addWidget(self.clock_label)
        thermal.addWidget(intake, 2)
        layout.addLayout(thermal)
        controls, controls_layout = card()
        controls_layout.addWidget(label("AMPLIFIER CONTROL", "eyebrow"))
        row = QHBoxLayout()
        for text, cmd, args in [
            ("Power on", "power", {"value": "on"}),
            ("Power off", "power", {"value": "off"}),
            ("Standby", "operate", {"value": False}),
            ("Operate", "operate", {"value": True}),
            ("Tuner off", "tuner", {"value": "off"}),
            ("Tuner on", "tuner", {"value": "on"}),
            ("Start tune", "tune", {}),
        ]:
            row.addWidget(self._command_button(text, cmd, args))
        controls_layout.addLayout(row)
        route = QHBoxLayout()
        route.addWidget(label("INPUT", "eyebrow"))
        for n in (1, 2):
            route.addWidget(self._command_button(str(n), "input", {"n": n}))
        route.addSpacing(14)
        route.addWidget(label("ANTENNA", "eyebrow"))
        for n in range(1, 7):
            route.addWidget(self._command_button(str(n), "antenna", {"n": n}))
        route.addStretch()
        for level, text in (("500", "500 W"), ("1k", "1 kW")):
            route.addWidget(self._command_button(text, "level", {"id": level}))
        controls_layout.addLayout(route)
        self.guard_label = label("", "guard")
        controls_layout.addWidget(self.guard_label)
        layout.addWidget(controls)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _command_button(self, text, name, args):
        button = QPushButton(text)
        button.setCheckable(name != "tune")
        button.setProperty("control", True)
        if name == "operate":
            button.setProperty("selectionTone", "ok" if args["value"] else "warn")
        button.setObjectName(f"command_{name}_{next(iter(args.values()), 'start')}")
        button.clicked.connect(lambda checked=False: self.send_command(name, args))
        self.buttons.append((button, name, args))
        return button

    def _connection(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        box, inner = card()
        inner.addWidget(label("Connect to your IC-PW2", "sectionTitle"))
        hint = label(
            "Enable LAN remote access on the PW2. Use the user ID and password configured on the amplifier.",
            "muted",
        )
        hint.setWordWrap(True)
        inner.addWidget(hint)
        form = QFormLayout()
        form.setSpacing(14)
        prefs = settings.load()
        self.host_edit = QLineEdit(str(prefs.get("host", "")))
        self.host_edit.setPlaceholderText("Hostname or IP address")
        self.port_edit = QSpinBox()
        self.port_edit.setRange(1, 65535)
        try:
            self.port_edit.setValue(int(prefs.get("port", 50200)))
        except (ValueError, TypeError):
            self.port_edit.setValue(50200)
        self.user_edit = QLineEdit(str(prefs.get("username", "")))
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Not saved to disk")
        self.mains_edit = QComboBox()
        for title, voltage in (
            ("Unknown · 1 kW switching disabled", None),
            ("230 V AC (180–264 V)", 230),
            ("120 V AC (90–132 V)", 120),
        ):
            self.mains_edit.addItem(title, voltage)
        index = self.mains_edit.findData(prefs.get("mains_v"))
        self.mains_edit.setCurrentIndex(max(0, index))
        for title, widget in (
            ("Address", self.host_edit),
            ("TCP port", self.port_edit),
            ("User ID", self.user_edit),
            ("Password", self.password_edit),
            ("AC supply", self.mains_edit),
        ):
            form.addRow(title, widget)
        inner.addLayout(form)
        self.form_connect = QPushButton("Connect to amplifier")
        self.form_connect.setObjectName("primary")
        self.form_connect.clicked.connect(self.connect_real)
        inner.addWidget(self.form_connect)
        note = label(
            "Use one LAN controller at a time. Disconnect RS-PW2 or the HamRig PW2 driver before connecting here.\n"
            "Only connection preferences are saved. Login does not switch power on or start tuning.",
            "muted",
        )
        note.setWordWrap(True)
        inner.addWidget(note)
        layout.addWidget(box)
        layout.addStretch()
        return page

    def _reference(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setMaximumHeight(230)
        help_text.setHtml("""<h2>Implementation status</h2><p><b>Available:</b> login, power, operate/standby,
        tuner on/off and explicit tune, input 1/2, antennas 1–6, 500 W/1 kW. TX/RX, frequencies,
        protection lamp, six display meters and intake air temperature/humidity.</p>
        <p><b>Approximate:</b> Po, Id, Vd and SWR are derived from display positions. ALC and PA temperature
        remain relative. Use bar view on the PW2 to receive all six meters.</p>
        <p><b>Open:</b> precise calibration, needle conversions, detailed protection reasons/reset,
        band writes, SO2R/dual receive, menus and direct hardware acceptance of all openpw2 commands.
        Tune acknowledgement means started, not a successful match.</p>
        <p>Native RS-PW2 TCP protocol, not CI-V over TCP. This independent MIT project has no Icom affiliation.
        See README.md and docs/ in the repository for the complete protocol and evidence.</p>""")
        layout.addWidget(help_text)
        row = QHBoxLayout()
        row.addWidget(label("LIVE TELEMETRY · no credentials or login packets", "eyebrow"))
        row.addStretch()
        export = QPushButton("Export JSON…")
        export.clicked.connect(self.export_snapshot)
        row.addWidget(export)
        layout.addLayout(row)
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        layout.addWidget(self.raw, 1)
        return page

    def show_message(self, message):
        self.notice.setText(message)

    def set_busy(self, value):
        self.busy = value
        self.refresh()

    def start_demo(self):
        self.is_demo = True
        self.mains_v = 230
        self.demo_tx.setChecked(False)
        self.bridge.connect_to(demo=True)
        self.tabs.setCurrentIndex(0)

    def connection_action(self):
        if self.state.get("connected"):
            self.bridge.disconnect_from()
        else:
            self.tabs.setCurrentIndex(1)

    def connect_real(self):
        try:
            config = ConnectionConfig(
                host=self.host_edit.text().strip(),
                port=self.port_edit.value(),
                username=self.user_edit.text(),
                password=self.password_edit.text(),
                mains_v=self.mains_edit.currentData(),
            )
        except ValueError as exc:
            self.show_message(str(exc))
            return
        try:
            settings.save(config)
        except OSError:
            self.show_message("Could not save preferences; connecting for this session")
        self.is_demo = False
        self.mains_v = config.mains_v
        self.demo_tx.setChecked(False)
        self.bridge.connect_to(config)
        self.tabs.setCurrentIndex(0)

    def send_command(self, name, args):
        # Undo Qt's visual toggle immediately; only telemetry selects a button.
        self.refresh()
        self.bridge.command(name, **args)

    def update_state(self, state):
        self.state = state
        self.received = time.monotonic()
        if state.get("error"):
            self.show_message(state["error"])
        self.raw.setPlainText(json.dumps(state, indent=2, ensure_ascii=False))
        self.refresh()

    def refresh(self):
        state = dict(self.state)
        age = (state.get("age_s") or 0) + (time.monotonic() - self.received if self.received else 0)
        state["age_s"] = age
        connected = bool(state.get("connected"))
        on = connected and state.get("power") == "on" and age < 5
        self.connection_badge.setText(
            "DEMO · NO HARDWARE"
            if connected and self.is_demo
            else "CONNECTED"
            if connected
            else "DISCONNECTED"
        )
        self.connect_button.setText("Disconnect" if connected else "Connect")
        self.connect_button.setEnabled(not self.busy)
        self.demo_button.setEnabled(not self.busy and not connected)
        self.demo_button.setVisible(not (self.is_demo and connected))
        self.form_connect.setEnabled(not self.busy and not connected)
        self.demo_tx.setVisible(self.is_demo)
        self.demo_tx.setEnabled(connected and bool(state.get("operate")) and not self.busy)
        self.age_label.setText(f"Last status {age:.1f}s ago" if connected else "No live telemetry")
        power = state.get("out_w") if on else None
        self.power_value.setText(f"≈ {power:,} W" if power is not None else "—")
        self.level_label.setText("LIMIT " + {"500": "500 W", "1k": "1 kW"}.get(state.get("level"), "—"))
        display = state.get("meter_display") if on else None
        bars = display.get("values", {}) if display and display.get("mode") == "bars" else {}
        self.po_bar.setValue(round(bars.get("po", {}).get("percent", 0) * 10))
        self.po_bar.setEnabled("po" in bars)
        self.power_hint.setText(
            "Select bar view on the PW2 to receive all six meters"
            if on and display and display.get("mode") == "needles"
            else "≈ Display-derived watts · 0 … 1,500 W scale"
        )
        mode = (
            "OPERATE" if state.get("operate") is True else "STANDBY" if state.get("operate") is False else "—"
        )
        self.mode_label.setText(
            mode if on else "POWER OFF" if connected and state.get("power") == "off" else "—"
        )
        self.tx_label.setText(
            "TUNING"
            if on and state.get("tuning")
            else "TX"
            if on and state.get("tx") is True
            else "RX"
            if on and state.get("tx") is False
            else "—"
        )
        hz = state.get("frequency_hz") if on else None
        self.frequency_label.setText(f"{hz / 1e6:.3f} MHz" if hz else "—")
        self.routing_label.setText(
            f"Input {state.get('input') or '—'}   ·   Antenna {state.get('tx_ant') or '—'}"
            f"   ·   {state.get('band') or '—'}"
            if on
            else "Input —   ·   Antenna —"
        )
        freqs = state.get("input_frequencies_hz") or [None, None]
        self.other_input.setText(
            "   /   ".join(
                f"IN{i + 1} {f / 1e6:.3f}" if f and on else f"IN{i + 1} —" for i, f in enumerate(freqs)
            )
        )
        for name, key, unit in (("swr", "swr_ant", ""), ("id", "pa_a", " A"), ("vd", "pa_v", " V")):
            value = state.get(key) if on else None
            data = bars.get(name, {})
            text = (
                f"≈ {value:.1f}{unit}"
                if name == "swr" and value is not None
                else f"≈ {value}{unit}"
                if value is not None
                else "—"
            )
            if value is None and data:
                text = f"{data['percent']:.1f}% · relative"
            self.meters[name].update_value(text, data.get("percent"), data.get("raw"))
        for name in ("alc", "temp"):
            data = bars.get(name, {})
            percent = data.get("percent")
            self.meters[name].update_value(
                f"{percent:.1f} %" if percent is not None else "—", percent, data.get("raw")
            )
        temp = (state.get("temps") or {}).get("intake") if on else None
        humidity = state.get("humidity") if on else None
        self.intake_label.setText(
            f"{temp if temp is not None else '—'} °C   /   {humidity if humidity is not None else '—'} %"
        )
        self.clock_label.setText(f"PW2 clock {state.get('device_clock') or '—'}" if on else "PW2 clock —")
        for button, name, args in self.buttons:
            reason = block_reason(state, name, args, self.mains_v)
            button.setEnabled(not self.busy and not reason)
            button.setToolTip(
                reason
                or ("Start a tuning cycle; acknowledgement is not match success" if name == "tune" else "")
            )
            field_name = {
                "operate": "operate",
                "power": "power",
                "input": "input",
                "antenna": "tx_ant",
                "level": "level",
                "tuner": "atu",
            }.get(name)
            button.setChecked(
                connected
                and field_name is not None
                and state.get(field_name) == next(iter(args.values()), None)
            )
        reason = block_reason(state, "input", {"n": 1}, self.mains_v)
        self.guard_label.setText(
            "PROTECTION ACTIVE — detailed reason not decoded"
            if on and state.get("protection_lamp")
            else "Command pending…"
            if self.busy
            else reason or "RX ready · switching enabled"
        )

        # HamRig amplifier semantics: green Operate, amber Standby / tuning,
        # blue RX and a solid red TX badge. Labels always accompany colour.
        set_tone(
            self.connection_badge,
            "warn"
            if connected and self.is_demo
            else "ok"
            if connected
            else "bad"
            if state.get("error")
            else "neutral",
        )
        set_tone(
            self.mode_label,
            "ok"
            if on and state.get("operate") is True
            else "warn"
            if on and state.get("operate") is False
            else "neutral",
        )
        set_tone(
            self.tx_label,
            "warn"
            if on and state.get("tuning")
            else "tx"
            if on and state.get("tx") is True
            else "info"
            if on and state.get("tx") is False
            else "neutral",
        )
        set_tone(
            self.frequency_card,
            "bad"
            if on and state.get("protection_lamp")
            else "tx"
            if on and state.get("tx") is True
            else "neutral",
        )
        set_tone(
            self.guard_label,
            "bad"
            if on and state.get("protection_lamp")
            else "warn"
            if connected and (reason or self.busy)
            else "ok"
            if connected
            else "neutral",
        )

    def export_snapshot(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export telemetry", "openpw2-status.json", "JSON (*.json)"
        )
        if path:
            try:
                Path(path).write_text(
                    json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                self.show_message("Telemetry exported")
            except OSError as exc:
                self.show_message(f"Export failed: {exc.strerror}")

    def closeEvent(self, event):
        if not self._shutdown:
            self._shutdown = True
            self.timer.stop()
            self.bridge.shutdown()
        event.accept()
