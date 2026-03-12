# clock_widget.py
# TabTempo / ClockWidget - UI for AutoClock v11 + TAP Tempo
# LED AZUL (clock) + LED VERDE (kick) + LED LOCK (state) + Interval display + TAP button + Sliders
# V11: LockLED indicator (green=LOCKED, yellow=LOCKING, off=UNLOCKED)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QScrollArea, QGroupBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont


class PulseLED(QFrame):
    """LED gigante que parpadea con el pulso (AZUL - clock interno)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._on = False
        self._update_style()

    def pulse(self):
        """Flash breve para indicar beat."""
        self._on = True
        self._update_style()
        QTimer.singleShot(80, self._off)

    def _off(self):
        """Apaga el LED."""
        self._on = False
        self._update_style()

    def _update_style(self):
        """Actualiza estilo visual - AZUL."""
        if self._on:
            self.setStyleSheet("""
                QFrame {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                        fx:0.5, fy:0.5,
                        stop:0 #00aaff, stop:0.5 #0088cc, stop:1 #004466);
                    border-radius: 40px;
                    border: 3px solid #00aaff;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                        fx:0.5, fy:0.5,
                        stop:0 #2e2e38, stop:0.5 #0e0e14, stop:1 #0a0a0f);
                    border-radius: 40px;
                    border: 3px solid #2e2e38;
                }
            """)


class KickLED(QFrame):
    """LED que parpadea cuando detecta KICK real (VERDE)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 80)
        self._on = False
        self._update_style()

    def pulse(self):
        """Flash breve para indicar kick detectado."""
        self._on = True
        self._update_style()
        QTimer.singleShot(80, self._off)

    def _off(self):
        """Apaga el LED."""
        self._on = False
        self._update_style()

    def _update_style(self):
        """Actualiza estilo visual - VERDE."""
        if self._on:
            self.setStyleSheet("""
                QFrame {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                        fx:0.5, fy:0.5,
                        stop:0 #00ff88, stop:0.5 #00cc66, stop:1 #006633);
                    border-radius: 40px;
                    border: 3px solid #00ff88;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                        fx:0.5, fy:0.5,
                        stop:0 #2e2e38, stop:0.5 #0e0e14, stop:1 #0a0a0f);
                    border-radius: 40px;
                    border: 3px solid #2e2e38;
                }
            """)


class LockLED(QFrame):
    """
    LED indicador de lock state del AutoClock.
    Verde fijo = LOCKED (tempo estable)
    Amarillo parpadeante = LOCKING (recibiendo kicks, evaluando)
    Apagado = UNLOCKED (sin datos)
    """

    _STYLE_OFF = """
        QFrame {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                fx:0.5, fy:0.5,
                stop:0 #2e2e38, stop:0.5 #0e0e14, stop:1 #0a0a0f);
            border-radius: 25px;
            border: 3px solid #2e2e38;
        }
    """
    _STYLE_LOCKED = """
        QFrame {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                fx:0.5, fy:0.5,
                stop:0 #00ff88, stop:0.5 #00cc66, stop:1 #006633);
            border-radius: 25px;
            border: 3px solid #00ff88;
        }
    """
    _STYLE_LOCKING_ON = """
        QFrame {
            background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                fx:0.5, fy:0.5,
                stop:0 #ffcc00, stop:0.5 #cc9900, stop:1 #665500);
            border-radius: 25px;
            border: 3px solid #ffcc00;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self._state = "UNLOCKED"
        self._blink_on = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_toggle)
        self.setStyleSheet(self._STYLE_OFF)

    def set_state(self, lock_state: str):
        """Update LED from lock state string: UNLOCKED / LOCKING / LOCKED."""
        if lock_state == self._state:
            return
        self._state = lock_state
        if lock_state == "LOCKED":
            self._blink_timer.stop()
            self.setStyleSheet(self._STYLE_LOCKED)
        elif lock_state == "LOCKING":
            self._blink_on = True
            self.setStyleSheet(self._STYLE_LOCKING_ON)
            self._blink_timer.start(400)
        else:
            self._blink_timer.stop()
            self.setStyleSheet(self._STYLE_OFF)

    def _blink_toggle(self):
        self._blink_on = not self._blink_on
        if self._blink_on:
            self.setStyleSheet(self._STYLE_LOCKING_ON)
        else:
            self.setStyleSheet(self._STYLE_OFF)


class ClockWidget(QWidget):
    """
    Tempo tab for AutoClock v11 + KickPulseDetector V14.

    Components:
    - PulseLED (AZUL): Clock interno
    - KickLED (VERDE): Kick detectado
    - Interval Label: Shows current interval in ms
    - TAP Button: Manual beat input
    - Configuration Sliders: AutoClock + KickDetector parameters

    Slider Wiring (V13):
    - Peak thresh → KickDetector.threshold_k (remapped 0.05-0.50 → 1.5-4.0)
    - RMS thresh → LEGACY (not connected to V13 MAD detector)
    - Anti-double → KickDetector.debounce_ms + AutoClock.min_hit_ms
    - Smoothing → AutoClock.smooth
    - Interval min/max → AutoClock.interval_min_ms/interval_max_ms
    """

    def __init__(self, auto_clock=None, kick_detector=None, parent=None):
        super().__init__(parent)
        self.auto_clock = auto_clock
        self.kick_detector = kick_detector
        self._setup_ui()

    def set_auto_clock(self, auto_clock):
        """Set or update the AutoClock reference."""
        self.auto_clock = auto_clock

    def set_kick_detector(self, kick_detector):
        """Set or update the KickPulseDetector reference."""
        self.kick_detector = kick_detector

    def _create_slider_row(self, label_text, min_val, max_val, default_val,
                           callback, suffix="", decimals=0, multiplier=1):
        """Helper para crear filas de sliders."""
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel(label_text)
        label.setFont(QFont("Arial", 9))
        label.setStyleSheet("color: #8a8a8a; background: transparent;")
        label.setFixedWidth(110)
        row.addWidget(label)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(int(min_val * multiplier), int(max_val * multiplier))
        slider.setValue(int(default_val * multiplier))
        slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #2e2e38;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00ff88;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #00cc66;
            }
        """)
        row.addWidget(slider)

        value_label = QLabel()
        value_label.setFont(QFont("Consolas", 9))
        value_label.setStyleSheet("color: #00ff88; background: transparent;")
        value_label.setFixedWidth(60)
        value_label.setAlignment(Qt.AlignRight)

        def update_label(val):
            real_val = val / multiplier
            if decimals == 0:
                value_label.setText(f"{int(real_val)}{suffix}")
            else:
                value_label.setText(f"{real_val:.{decimals}f}{suffix}")
            callback(real_val)

        slider.valueChanged.connect(update_label)
        update_label(slider.value())

        row.addWidget(value_label)
        return row, slider

    def _setup_ui(self):
        self.setStyleSheet("background: #0a0a0f;")

        # Scroll area for all content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; background: #141418; }
            QScrollBar::handle:vertical { background: #2e2e38; border-radius: 4px; }
        """)

        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # === TITLE ===
        title = QLabel("TAP TEMPO")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title.setStyleSheet("color: #00ff88; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel("AutoClock v11")
        subtitle.setFont(QFont("Arial", 10))
        subtitle.setStyleSheet("color: #616161; background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(subtitle)

        # === LEDs + INTERVAL Section ===
        center_layout = QHBoxLayout()
        center_layout.setSpacing(20)

        # LED AZUL (Clock interno)
        clock_container = QVBoxLayout()
        clock_container.setAlignment(Qt.AlignCenter)

        self.pulse_led = PulseLED()

        clock_label = QLabel("CLOCK")
        clock_label.setFont(QFont("Arial", 9))
        clock_label.setStyleSheet("color: #00aaff; background: transparent;")
        clock_label.setAlignment(Qt.AlignCenter)

        clock_container.addWidget(self.pulse_led, 0, Qt.AlignCenter)
        clock_container.addWidget(clock_label, 0, Qt.AlignCenter)

        # LED VERDE (Kick detectado)
        kick_container = QVBoxLayout()
        kick_container.setAlignment(Qt.AlignCenter)

        self.kick_led = KickLED()

        kick_label = QLabel("KICK")
        kick_label.setFont(QFont("Arial", 9))
        kick_label.setStyleSheet("color: #00ff88; background: transparent;")
        kick_label.setAlignment(Qt.AlignCenter)

        kick_container.addWidget(self.kick_led, 0, Qt.AlignCenter)
        kick_container.addWidget(kick_label, 0, Qt.AlignCenter)

        # LED LOCK STATE (V11)
        lock_container = QVBoxLayout()
        lock_container.setAlignment(Qt.AlignCenter)

        self.lock_led = LockLED()

        self._lock_label = QLabel("LOCK")
        self._lock_label.setFont(QFont("Arial", 9))
        self._lock_label.setStyleSheet("color: #616161; background: transparent;")
        self._lock_label.setAlignment(Qt.AlignCenter)

        lock_container.addWidget(self.lock_led, 0, Qt.AlignCenter)
        lock_container.addWidget(self._lock_label, 0, Qt.AlignCenter)

        # Interval Display
        interval_container = QVBoxLayout()
        interval_container.setAlignment(Qt.AlignCenter)

        self.interval_label = QLabel("750")
        self.interval_label.setFont(QFont("Consolas", 36, QFont.Bold))
        self.interval_label.setStyleSheet("color: #00ff88; background: transparent;")
        self.interval_label.setAlignment(Qt.AlignCenter)

        interval_unit = QLabel("ms")
        interval_unit.setFont(QFont("Arial", 12))
        interval_unit.setStyleSheet("color: #616161; background: transparent;")
        interval_unit.setAlignment(Qt.AlignCenter)

        # BPM Display
        self.bpm_label = QLabel("80 BPM")
        self.bpm_label.setFont(QFont("Arial", 14))
        self.bpm_label.setStyleSheet("color: #00aaff; background: transparent;")
        self.bpm_label.setAlignment(Qt.AlignCenter)

        interval_container.addWidget(self.interval_label, 0, Qt.AlignCenter)
        interval_container.addWidget(interval_unit, 0, Qt.AlignCenter)
        interval_container.addWidget(self.bpm_label, 0, Qt.AlignCenter)

        center_layout.addStretch()
        center_layout.addLayout(clock_container)
        center_layout.addLayout(kick_container)
        center_layout.addLayout(lock_container)
        center_layout.addLayout(interval_container)
        center_layout.addStretch()

        main_layout.addLayout(center_layout)

        # === TAP Button ===
        tap_layout = QHBoxLayout()
        tap_layout.addStretch()

        self.btn_tap = QPushButton("TAP")
        self.btn_tap.setFixedSize(120, 60)
        self.btn_tap.setFont(QFont("Arial", 18, QFont.Bold))
        self.btn_tap.setStyleSheet("""
            QPushButton {
                background: #1a3d2a;
                color: #00ff88;
                border: 2px solid #00aa55;
                border-radius: 8px;
            }
            QPushButton:hover { background: #2a5d3a; }
            QPushButton:pressed { background: #0a2d1a; }
        """)
        self.btn_tap.clicked.connect(self._on_tap)
        tap_layout.addWidget(self.btn_tap)

        # Reset button
        self.btn_reset = QPushButton("RESET")
        self.btn_reset.setFixedSize(80, 40)
        self.btn_reset.setFont(QFont("Arial", 10))
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background: #3d1a1a;
                color: #ff6666;
                border: 1px solid #aa5555;
                border-radius: 10px;
            }
            QPushButton:hover { background: #5d2a2a; }
            QPushButton:pressed { background: #2d0a0a; }
        """)
        self.btn_reset.clicked.connect(self._on_reset)
        tap_layout.addWidget(self.btn_reset)

        tap_layout.addStretch()
        main_layout.addLayout(tap_layout)

        # === DETECTION GROUP ===
        detection_group = QGroupBox("DETECCION DEL BOOM (KICK)")
        detection_group.setFont(QFont("Arial", 10, QFont.Bold))
        detection_group.setStyleSheet("""
            QGroupBox {
                color: #ff8800;
                background: #141418;
                border: 1px solid #2e2e38;
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        detection_layout = QVBoxLayout(detection_group)
        detection_layout.setSpacing(8)
        detection_layout.setContentsMargins(10, 20, 10, 10)

        # Peak threshold (0.05-0.50)
        row, self.slider_peak = self._create_slider_row(
            "Peak thresh", 0.05, 0.50, 0.20,
            lambda v: self._set_param("peak_thresh", v),
            "", 2, 100
        )
        detection_layout.addLayout(row)

        # RMS threshold (0.01-0.20)
        row, self.slider_rms = self._create_slider_row(
            "RMS thresh", 0.01, 0.20, 0.05,
            lambda v: self._set_param("rms_thresh", v),
            "", 2, 100
        )
        detection_layout.addLayout(row)

        # Anti-double-hit (100-300 ms)
        row, self.slider_min_hit = self._create_slider_row(
            "Anti-double", 100, 300, 180,
            lambda v: self._set_param("min_hit_ms", v),
            " ms", 0, 1
        )
        detection_layout.addLayout(row)

        main_layout.addWidget(detection_group)

        # === STABILITY GROUP ===
        stability_group = QGroupBox("ESTABILIDAD DEL CLOCK")
        stability_group.setFont(QFont("Arial", 10, QFont.Bold))
        stability_group.setStyleSheet("""
            QGroupBox {
                color: #00aaff;
                background: #141418;
                border: 1px solid #2e2e38;
                border-radius: 12px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        stability_layout = QVBoxLayout(stability_group)
        stability_layout.setSpacing(8)
        stability_layout.setContentsMargins(10, 20, 10, 10)

        # Smoothing (5-50%, default 30%)
        row, self.slider_smooth = self._create_slider_row(
            "Smoothing", 5, 50, 30,
            lambda v: self._set_param("smooth", v / 100.0),
            "%", 0, 1
        )
        stability_layout.addLayout(row)

        # Interval min (300-800 ms)
        row, self.slider_int_min = self._create_slider_row(
            "Interval min", 300, 800, 350,
            lambda v: self._set_param("interval_min_ms", v),
            " ms", 0, 1
        )
        stability_layout.addLayout(row)

        # Interval max (900-2000 ms)
        row, self.slider_int_max = self._create_slider_row(
            "Interval max", 900, 2000, 1500,
            lambda v: self._set_param("interval_max_ms", v),
            " ms", 0, 1
        )
        stability_layout.addLayout(row)

        main_layout.addWidget(stability_group)

        # Manual override indicator
        self.manual_indicator = QLabel("")
        self.manual_indicator.setFont(QFont("Arial", 10))
        self.manual_indicator.setStyleSheet("color: #ffaa00; background: transparent;")
        self.manual_indicator.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.manual_indicator)

        main_layout.addStretch()

        scroll.setWidget(content)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

    def _set_param(self, name: str, value: float):
        """
        Set parameter on AutoClock and/or KickDetector.

        V13 Wiring:
        - peak_thresh → KickDetector.threshold_k (remapped)
        - rms_thresh → LEGACY (log only, no effect)
        - min_hit_ms → KickDetector.debounce_ms + AutoClock.min_hit_ms
        - smooth, interval_min_ms, interval_max_ms → AutoClock only
        """
        print(f"[TapUI] slider={name} value={value}")

        # Route to KickDetector for detection params
        if self.kick_detector is not None:
            if name == "peak_thresh":
                # Remap 0.05-0.50 → threshold_k 1.5-4.0 (higher peak = higher sensitivity = lower k)
                # Inverted: low peak_thresh = high sensitivity = low k
                k = 4.0 - (value - 0.05) / (0.50 - 0.05) * 2.5  # 0.05→4.0, 0.50→1.5
                self.kick_detector.set_param("threshold_k", k)
            elif name == "min_hit_ms":
                # Anti-double applies to both KickDetector and AutoClock
                self.kick_detector.set_param("debounce_ms", value)

        # Route to AutoClock for all params (some legacy, some active)
        if self.auto_clock is not None:
            self.auto_clock.set_param(name, value)

    def set_interval_ms(self, ms: float):
        """Update interval display."""
        self.interval_label.setText(f"{int(ms)}")
        if ms > 0:
            bpm = 60000.0 / ms
            self.bpm_label.setText(f"{bpm:.1f} BPM")
        else:
            self.bpm_label.setText("-- BPM")

    def pulse_clock(self):
        """Flash the blue CLOCK LED."""
        self.pulse_led.pulse()

    def pulse_kick(self):
        """Flash the green KICK LED when a real kick is detected."""
        self.kick_led.pulse()

    def update_manual_indicator(self, active: bool, bpm: float = 0.0):
        """Update manual override indicator."""
        if active:
            self.manual_indicator.setText(f"TAP OVERRIDE ACTIVO ({bpm:.1f} BPM)")
            self.manual_indicator.setStyleSheet("color: #ffaa00; background: transparent;")
        else:
            self.manual_indicator.setText("")

    def _on_tap(self):
        """Handle TAP button click."""
        if self.auto_clock is not None:
            self.auto_clock.tap()
        self.pulse_led.pulse()

    def _on_reset(self):
        """Handle RESET button click."""
        if self.auto_clock is not None:
            self.auto_clock.reset()
        self.interval_label.setText("750")
        self.bpm_label.setText("80 BPM")
        self.manual_indicator.setText("")
        self.lock_led.set_state("UNLOCKED")

    def update_display(self):
        """Update all displays from AutoClock state via get_ui_state()."""
        if self.auto_clock is None:
            return

        # V11: single snapshot for all UI updates
        ui = self.auto_clock.get_ui_state()

        # Update interval + BPM
        self.set_interval_ms(ui.interval_ms)

        # Update lock LED
        self.lock_led.set_state(ui.lock_state)

        # Update lock label color to match state
        if ui.lock_state == "LOCKED":
            self._lock_label.setStyleSheet("color: #00ff88; background: transparent;")
        elif ui.lock_state == "LOCKING":
            self._lock_label.setStyleSheet("color: #ffcc00; background: transparent;")
        else:
            self._lock_label.setStyleSheet("color: #616161; background: transparent;")

        # Update manual indicator
        if self.auto_clock.manual_override_active():
            self.update_manual_indicator(True, self.auto_clock.get_manual_bpm())
        else:
            self.update_manual_indicator(False)

        # Check for kick
        if self.auto_clock.was_kick_detected():
            self.pulse_kick()


# Alias for compatibility
TabTempo = ClockWidget


__all__ = ['ClockWidget', 'TabTempo', 'PulseLED', 'KickLED', 'LockLED']
