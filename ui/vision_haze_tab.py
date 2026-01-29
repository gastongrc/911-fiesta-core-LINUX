"""
VisionHazeTab - Tab independiente para Haze Detector PRO
Preview + controles completos + LEDs de estado y cues

Phase 6.9: Thread-safe frame updates
Phase 6.10: USB removed - camera combo removed
"""
import cv2
import numpy as np
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QFrame, QGridLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QColor


class LEDIndicator(QWidget):
    """Widget LED indicator para mostrar estados."""

    def __init__(self, color=QColor(128, 128, 128), size=16, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QPainter, QBrush, QPen

        self.color = color
        self.size = size
        self.is_on = False
        self.setFixedSize(QSize(size, size))
        self.QPainter = QPainter
        self.QBrush = QBrush
        self.QPen = QPen

    def set_on(self, on):
        """Enciende/apaga el LED."""
        self.is_on = on
        self.update()

    def paintEvent(self, event):
        """Dibuja el LED."""
        painter = self.QPainter(self)
        painter.setRenderHint(self.QPainter.Antialiasing)

        if self.is_on:
            color = self.color
        else:
            color = QColor(60, 60, 60)

        painter.setBrush(self.QBrush(color))
        painter.setPen(self.QPen(QColor(40, 40, 40), 1))
        painter.drawEllipse(2, 2, self.size - 4, self.size - 4)


class VisionHazeTab(QWidget):
    """
    Tab independiente para Haze Detector PRO.

    Incluye:
    - Preview de cámara Haze
    - LEDs de estado (READY/SHOOTING/COOLDOWN)
    - LEDs de cues (LOW/MED/HIGH)
    - Controles de configuración
    - Selector de cámara independiente
    - FPS display
    """

    def __init__(self, vision_manager, parent=None, system_bridge=None):
        super().__init__(parent)
        self.vision_manager = vision_manager
        self._system_bridge = system_bridge  # V16: para sync checkbox con calendario

        # Thread-safe frame buffer (Phase 6.9)
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._frame_updated = False

        self._build_ui()

        # Timer para actualizar UI (incluye frame preview)
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(33)  # ~30 FPS for smooth preview
        self.update_timer.timeout.connect(self._on_timer_tick)
        self.update_timer.start()

        # Conectar callback de frames (solo almacena en buffer, no toca UI)
        self.vision_manager.set_ui_callback_haze(self._on_frame_received)

        print("[VisionHazeTab] Initialized with thread-safe frame buffer")

    def _build_ui(self):
        """Construye la interfaz del tab."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Panel superior: Preview + Controles
        top_layout = QHBoxLayout()

        # Preview (izquierda)
        top_layout.addWidget(self._build_preview_panel(), 2)

        # Controles (derecha)
        top_layout.addWidget(self._build_controls_panel(), 1)

        layout.addLayout(top_layout)

    def _build_preview_panel(self) -> QGroupBox:
        """Panel de preview de cámara Haze."""
        group = QGroupBox("Vista Previa - Cámara Haze")
        layout = QVBoxLayout(group)

        # Canvas para preview
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("border: 2px solid #333; background-color: #000;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("No hay video")
        layout.addWidget(self.preview_label)

        # Info bar
        info_layout = QHBoxLayout()
        self.fps_label = QLabel("FPS: 0.0")
        self.fps_label.setStyleSheet("color: #27ae60; font-weight: bold;")
        info_layout.addWidget(self.fps_label)

        info_layout.addStretch()

        # NOTE: camera_combo removed (USB removed in Phase 6.10)
        # IP cameras are configured via VisionConfigWidget

        layout.addLayout(info_layout)

        return group

    def _build_controls_panel(self) -> QGroupBox:
        """Panel de controles Haze."""
        group = QGroupBox("Haze Detector PRO")
        layout = QVBoxLayout(group)

        # Toggle enable - V10: persist=False, Calendar es autoridad
        self.haze_enabled_check = QCheckBox("Habilitado")
        self.haze_enabled_check.setChecked(False)
        self.haze_enabled_check.stateChanged.connect(
            lambda: self.vision_manager.enable_module("haze", self.haze_enabled_check.isChecked(), source="ui", persist=False)
        )
        layout.addWidget(self.haze_enabled_check)

        # LEDs de ESTADO
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(5, 5, 5, 5)

        status_layout.addWidget(QLabel("Estado:"))

        self.led_ready = LEDIndicator(QColor(52, 152, 219), 14)
        status_layout.addWidget(self.led_ready)
        status_layout.addWidget(QLabel("READY"))

        self.led_shooting = LEDIndicator(QColor(243, 156, 18), 14)
        status_layout.addWidget(self.led_shooting)
        status_layout.addWidget(QLabel("SHOOTING"))

        self.led_cooldown = LEDIndicator(QColor(231, 76, 60), 14)
        status_layout.addWidget(self.led_cooldown)
        status_layout.addWidget(QLabel("COOLDOWN"))

        status_layout.addStretch()
        layout.addWidget(status_frame)

        # LEDs de CUES
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QHBoxLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues:"))

        self.led_low = LEDIndicator(QColor(0, 255, 0), 14)
        cues_layout.addWidget(self.led_low)
        cues_layout.addWidget(QLabel("LOW"))

        self.led_med = LEDIndicator(QColor(0, 255, 0), 14)
        cues_layout.addWidget(self.led_med)
        cues_layout.addWidget(QLabel("MED"))

        self.led_high = LEDIndicator(QColor(0, 255, 0), 14)
        cues_layout.addWidget(self.led_high)
        cues_layout.addWidget(QLabel("HIGH"))

        cues_layout.addStretch()
        layout.addWidget(cues_frame)

        # Estado actual
        grid = QGridLayout()

        grid.addWidget(QLabel("Detector State:"), 0, 0)
        self.detector_state_label = QLabel("idle")
        self.detector_state_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.detector_state_label, 0, 1)

        grid.addWidget(QLabel("Nivel:"), 1, 0)
        self.level_label = QLabel("0.0")
        self.level_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.level_label, 1, 1)

        grid.addWidget(QLabel("Estado:"), 2, 0)
        self.state_label = QLabel("LOW")
        grid.addWidget(self.state_label, 2, 1)

        grid.addWidget(QLabel("Cooldown:"), 3, 0)
        self.cooldown_label = QLabel("0s")
        self.cooldown_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        grid.addWidget(self.cooldown_label, 3, 1)

        layout.addLayout(grid)

        # ✅ VISION PRO v2: Barra vertical de haze con colores dinámicos
        haze_bar_layout = QHBoxLayout()
        haze_bar_layout.addWidget(QLabel("Nivel Haze:"))

        self.haze_bar = QFrame()
        self.haze_bar.setFixedHeight(20)
        self.haze_bar.setFrameShape(QFrame.StyledPanel)
        self.haze_bar.setStyleSheet("background-color: #00FF64; border: 1px solid #333;")
        haze_bar_layout.addWidget(self.haze_bar)

        self.haze_bar_label = QLabel("0.0")
        self.haze_bar_label.setStyleSheet("font-weight: bold; min-width: 40px;")
        haze_bar_layout.addWidget(self.haze_bar_label)

        layout.addLayout(haze_bar_layout)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        # Configuración
        layout.addWidget(QLabel("Configuración:"))

        # Fire Duration
        fire_layout = QHBoxLayout()
        fire_layout.addWidget(QLabel("Fire Duration (s):"))
        self.fire_spin = QDoubleSpinBox()
        self.fire_spin.setRange(1.0, 10.0)
        self.fire_spin.setValue(3.0)
        self.fire_spin.setSingleStep(0.5)
        fire_layout.addWidget(self.fire_spin)
        layout.addLayout(fire_layout)

        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(QLabel("Cooldown (s):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(1, 300)
        self.cooldown_spin.setValue(60)
        cooldown_layout.addWidget(self.cooldown_spin)
        layout.addLayout(cooldown_layout)

        # Thresholds
        layout.addWidget(QLabel("Thresholds:"))

        thresh_grid = QGridLayout()

        thresh_grid.addWidget(QLabel("LOW:"), 0, 0)
        self.thresh_low = QSpinBox()
        self.thresh_low.setRange(0, 100)
        self.thresh_low.setValue(30)
        thresh_grid.addWidget(self.thresh_low, 0, 1)

        thresh_grid.addWidget(QLabel("MED:"), 1, 0)
        self.thresh_med = QSpinBox()
        self.thresh_med.setRange(0, 100)
        self.thresh_med.setValue(50)
        thresh_grid.addWidget(self.thresh_med, 1, 1)

        thresh_grid.addWidget(QLabel("HIGH:"), 2, 0)
        self.thresh_high = QSpinBox()
        self.thresh_high.setRange(0, 100)
        self.thresh_high.setValue(70)
        thresh_grid.addWidget(self.thresh_high, 2, 1)

        layout.addLayout(thresh_grid)

        # Target Density
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Densidad Objetivo:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(["LOW", "MEDIUM", "HIGH"])
        self.target_combo.setCurrentText("LOW")
        target_layout.addWidget(self.target_combo)
        layout.addLayout(target_layout)

        # Botones
        btn_layout = QHBoxLayout()

        self.calibrate_btn = QPushButton("Calibrar Baseline")
        self.calibrate_btn.clicked.connect(self._on_calibrate)
        btn_layout.addWidget(self.calibrate_btn)

        self.apply_btn = QPushButton("Aplicar Cambios")
        self.apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)

        layout.addStretch()

        return group

    def _on_frame_received(self, frame):
        """
        Callback para recibir frames de la cámara Haze.
        THREAD-SAFE: Solo almacena en buffer, NO toca UI.
        Llamado desde el thread de CameraLoop.
        """
        if frame is None:
            return

        with self._frame_lock:
            # Hacer copia para evitar problemas de memoria compartida
            self._latest_frame = frame.copy()
            self._frame_updated = True

    def _on_timer_tick(self):
        """
        Timer tick - actualiza UI desde main thread.
        Llama a _update_state cada 8 ticks (~250ms) y preview cada tick.
        """
        # Actualizar preview si hay nuevo frame
        self._update_preview()

        # Actualizar estado menos frecuentemente
        if not hasattr(self, '_state_tick_counter'):
            self._state_tick_counter = 0
        self._state_tick_counter += 1
        if self._state_tick_counter >= 8:  # ~250ms
            self._state_tick_counter = 0
            self._update_state()

    def _update_preview(self):
        """Actualiza el preview desde el buffer thread-safe. MAIN THREAD ONLY."""
        frame = None
        with self._frame_lock:
            if self._frame_updated and self._latest_frame is not None:
                frame = self._latest_frame
                self._frame_updated = False

        if frame is None:
            return

        try:
            h, w = frame.shape[:2]
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb_frame.data, w, h, w * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            scaled = pixmap.scaled(
                self.preview_label.width(), self.preview_label.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.preview_label.setPixmap(scaled)
        except Exception as e:
            print(f"[VisionHazeTab] Error actualizando preview: {e}")

    # Legacy method name for compatibility
    def update_frame(self, frame):
        """Legacy callback - redirects to thread-safe method."""
        self._on_frame_received(frame)

    def _update_state(self):
        """Actualiza el estado de los controles."""
        try:
            state = self.vision_manager.get_state()
            haze_state = state.get("haze", {})

            # FPS
            fps = state.get("system", {}).get("fps", 0.0)
            self.fps_label.setText(f"FPS: {fps:.1f}")

            # V16: Sincronizar checkbox con estado REAL + bloquear si calendario gobierna
            haze_enabled = haze_state.get("enabled", False)
            calendar_governs = False

            if self._system_bridge:
                try:
                    actions = self._system_bridge.get_current_actions()
                    # Si hay actions activas, calendario está gobernando
                    calendar_governs = len(actions) > 0
                except Exception:
                    pass

            # Sincronizar checkbox sin disparar señales
            self.haze_enabled_check.blockSignals(True)
            self.haze_enabled_check.setChecked(haze_enabled)
            self.haze_enabled_check.blockSignals(False)

            # Bloquear checkbox si calendario gobierna (operador no puede pelear)
            self.haze_enabled_check.setEnabled(not calendar_governs)

            # Estado detector
            status = haze_state.get("status", "READY")
            level = haze_state.get("level", 0.0)
            haze_level_str = haze_state.get("state", "LOW")
            cooldown_remaining = haze_state.get("cooldown_remaining", 0.0)

            # V15: UI muestra estado REAL del detector (sin estados inventados)
            self.detector_state_label.setText(status.lower())
            self.detector_state_label.setStyleSheet("font-weight: bold;")
            self.level_label.setText(f"{level:.1f}")
            self.state_label.setText(haze_level_str)
            self.cooldown_label.setText(f"{int(cooldown_remaining)}s")

            # V15: Actualizar barra de haze con colores dinámicos (estado real)
            haze_value = level / 100.0  # Normalizar a 0-1

            # Determinar color según nivel
            if haze_value < 0.25:
                bar_color = "#00FF64"  # Verde
            elif haze_value < 0.40:
                bar_color = "#FFD000"  # Amarillo
            else:
                bar_color = "#FF3333"  # Rojo

            self.haze_bar.setStyleSheet(f"background-color: {bar_color}; border: 1px solid #333;")
            self.haze_bar_label.setText(f"{haze_value:.2f}")

            # LEDs de estado
            self.led_ready.set_on(status == "READY")
            self.led_shooting.set_on(status == "SHOOTING")
            self.led_cooldown.set_on(status == "COOLDOWN" or cooldown_remaining > 0)

            # LEDs de cues (verificar Avolites)
            self._update_cue_leds()

        except Exception as e:
            print(f"[VisionHazeTab] Error actualizando estado: {e}")

    def _update_cue_leds(self):
        """Actualiza LEDs de cues según estado de Avolites."""
        try:
            if hasattr(self.vision_manager, 'cue_engine') and self.vision_manager.cue_engine:
                av = self.vision_manager.cue_engine.av
                self.led_low.set_on(av.is_active(60))
                self.led_med.set_on(av.is_active(61))
                self.led_high.set_on(av.is_active(62))
            else:
                self.led_low.set_on(False)
                self.led_med.set_on(False)
                self.led_high.set_on(False)
        except Exception as e:
            pass

    # NOTE: _on_camera_changed removed (USB removed in Phase 6.10)

    def _on_calibrate(self):
        """Calibra el baseline de Haze."""
        self.vision_manager.calibrate_haze_baseline()
        print("[VisionHazeTab] Baseline de Haze recalibrado")

    def _on_apply(self):
        """Aplica cambios de configuración."""
        try:
            haze_detector = self.vision_manager.get_haze_detector()

            # Actualizar thresholds
            haze_detector.threshold_low = self.thresh_low.value()
            haze_detector.threshold_med = self.thresh_med.value()
            haze_detector.threshold_high = self.thresh_high.value()

            # Actualizar fire duration y cooldown
            haze_detector.fire_duration = self.fire_spin.value()
            haze_detector.cooldown_min = self.cooldown_spin.value()
            haze_detector.cooldown_max = self.cooldown_spin.value()

            # Actualizar target_density
            haze_detector.target_density = self.target_combo.currentText()

            # Guardar en config JSON
            config = self.vision_manager.get_config()
            haze_config = config.get_haze_config()
            haze_config["fire_duration"] = self.fire_spin.value()
            haze_config["cooldown_min"] = self.cooldown_spin.value()
            haze_config["cooldown_max"] = self.cooldown_spin.value()
            haze_config["threshold_low"] = self.thresh_low.value()
            haze_config["threshold_med"] = self.thresh_med.value()
            haze_config["threshold_high"] = self.thresh_high.value()
            haze_config["target_density"] = self.target_combo.currentText()

            config.set("haze", haze_config)
            config.save()

            print(f"[VisionHazeTab] Configuración aplicada (target_density={self.target_combo.currentText()})")

        except Exception as e:
            print(f"[VisionHazeTab] Error aplicando config: {e}")
