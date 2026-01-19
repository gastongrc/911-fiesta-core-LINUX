"""
VisionArtistTab - Tab independiente para Artist Tracker PRO
Preview + LayeredZoneEditor PRO 8 zonas + controles completos + LEDs de cues

Phase 6.10: USB removed - camera combo removed
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QFrame, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter, QPen, QBrush, QFont

from .layered_zone_editor import LayeredZoneEditor


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


class VisionArtistTab(QWidget):
    """
    Tab independiente para Artist Tracker PRO.

    Incluye:
    - Preview de cámara Artist con 8 zonas horizontales
    - LEDs de cues (CUE_TRACK_1..8)
    - Controles de configuración (Cooldown, Smoothing)
    - Modo calendario (ARTISTA/TEATRO/BOLICHE/OFF)
    - Selector de cámara independiente
    - FPS display
    """

    def __init__(self, vision_manager, parent=None):
        super().__init__(parent)
        self.vision_manager = vision_manager
        self._build_ui()

        # Timer para actualizar UI
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(250)  # 4 FPS
        self.update_timer.timeout.connect(self._update_state)
        self.update_timer.start()

        # Conectar callback de frames (cuando esté implementado)
        try:
            self.vision_manager.set_ui_callback_artist(self.update_frame)
        except AttributeError:
            print("[VisionArtistTab] Warning: set_ui_callback_artist() no disponible aún")

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
        """Panel de preview de cámara Artist con LayeredZoneEditor PRO."""
        group = QGroupBox("Vista Previa - Cámara Artist + LayeredZoneEditor PRO")
        layout = QVBoxLayout(group)

        # LayeredZoneEditor PRO (8 zonas horizontales para Artist)
        # Crear 8 zonas horizontales iniciales
        artist_zones = self._create_artist_zones()
        self.zone_viewer = LayeredZoneEditor(zone_list=artist_zones, max_zones=8, camera_type="ARTIST")
        self.zone_viewer.zones_changed.connect(self._on_zones_changed)
        layout.addWidget(self.zone_viewer)

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

    def _create_artist_zones(self):
        """Crea 8 zonas horizontales para Artist Tracker."""
        zones = []
        canvas_width = 640  # Ancho por defecto
        canvas_height = 480  # Alto por defecto
        zone_width = canvas_width // 8

        for i in range(8):
            zones.append({
                "id": i + 1,
                "name": f"Artist {i + 1}",
                "x": i * zone_width,
                "y": 0,
                "w": zone_width,
                "h": canvas_height,
                "width": zone_width,
                "height": canvas_height,
                "visible": True,
                "locked": True  # Artist zones son fijas, no se pueden mover
            })
        return zones

    def _on_zones_changed(self, zones):
        """Callback cuando cambian las zonas."""
        # Artist zones no cambian mucho pero guardamos por consistencia
        pass

    def _build_controls_panel(self) -> QGroupBox:
        """Panel de controles Artist Tracker."""
        group = QGroupBox("Artist Tracker PRO")
        layout = QVBoxLayout(group)

        # Toggle enable
        self.tracking_enabled_check = QCheckBox("Habilitado")
        self.tracking_enabled_check.setChecked(False)
        self.tracking_enabled_check.stateChanged.connect(
            lambda: self.vision_manager.enable_module("tracking", self.tracking_enabled_check.isChecked())
        )
        layout.addWidget(self.tracking_enabled_check)

        # LEDs de CUES (CUE_TRACK_1..8 = cues 70-77)
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QGridLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues Activos:"), 0, 0, 1, 2)

        # 8 LEDs para CUE_TRACK_1..8
        self.led_track_cues = []
        for i in range(8):
            led = LEDIndicator(QColor(0, 255, 0), 12)
            self.led_track_cues.append(led)

            row = 1 + (i // 2)
            col = (i % 2) * 2

            cues_layout.addWidget(led, row, col)
            cues_layout.addWidget(QLabel(f"T{i+1}"), row, col + 1)

        layout.addWidget(cues_frame)

        # Estado actual
        grid = QGridLayout()

        grid.addWidget(QLabel("Detector State:"), 0, 0)
        self.detector_state_label = QLabel("idle")
        self.detector_state_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.detector_state_label, 0, 1)

        grid.addWidget(QLabel("Zona Activa:"), 1, 0)
        self.active_zone_label = QLabel("None")
        self.active_zone_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        grid.addWidget(self.active_zone_label, 1, 1)

        grid.addWidget(QLabel("Cue State:"), 2, 0)
        self.cue_state_label = QLabel("idle")
        grid.addWidget(self.cue_state_label, 2, 1)

        layout.addLayout(grid)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        # Modo Calendario
        layout.addWidget(QLabel("Modo Calendario:"))

        calendar_layout = QHBoxLayout()
        self.calendar_combo = QComboBox()
        self.calendar_combo.addItems(["OFF", "ARTISTA", "TEATRO", "BOLICHE"])
        self.calendar_combo.setCurrentText("OFF")
        self.calendar_combo.currentTextChanged.connect(self._on_calendar_mode_changed)
        calendar_layout.addWidget(self.calendar_combo)
        layout.addLayout(calendar_layout)

        self.calendar_status_label = QLabel("Artist Tracker: DESHABILITADO por calendario")
        self.calendar_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")
        layout.addWidget(self.calendar_status_label)

        # Separador
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.HLine)
        layout.addWidget(separator2)

        # Configuración
        layout.addWidget(QLabel("Configuración:"))

        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(QLabel("Cooldown (s):"))
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.1, 5.0)
        self.cooldown_spin.setValue(0.5)
        self.cooldown_spin.setSingleStep(0.1)
        cooldown_layout.addWidget(self.cooldown_spin)
        layout.addLayout(cooldown_layout)

        # Smoothing
        smoothing_layout = QHBoxLayout()
        smoothing_layout.addWidget(QLabel("Smoothing:"))
        self.smoothing_spin = QSpinBox()
        self.smoothing_spin.setRange(1, 10)
        self.smoothing_spin.setValue(3)
        smoothing_layout.addWidget(self.smoothing_spin)
        layout.addLayout(smoothing_layout)

        # Zones Horizontal
        zones_layout = QHBoxLayout()
        zones_layout.addWidget(QLabel("Zonas Horizontales:"))
        self.zones_spin = QSpinBox()
        self.zones_spin.setRange(4, 16)
        self.zones_spin.setValue(8)
        self.zones_spin.setEnabled(False)  # Fixed to 8
        zones_layout.addWidget(self.zones_spin)
        layout.addLayout(zones_layout)

        # Botón aplicar
        self.apply_btn = QPushButton("Aplicar Cambios")
        self.apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_btn)

        layout.addStretch()

        return group

    def update_frame(self, frame):
        """Callback para recibir frames de la cámara Artist."""
        if frame is None:
            return

        try:
            # Actualizar el zone viewer con el frame
            self.zone_viewer.set_frame(frame)
        except Exception as e:
            print(f"[VisionArtistTab] Error actualizando frame: {e}")

    def _update_state(self):
        """Actualiza el estado de los controles."""
        try:
            state = self.vision_manager.get_state()
            tracking_state = state.get("tracking", {})

            # FPS
            fps = state.get("system", {}).get("fps", 0.0)
            self.fps_label.setText(f"FPS: {fps:.1f}")

            # Estado detector
            detector_state = tracking_state.get("detector_state", "idle")
            active_zone = tracking_state.get("zone", None)
            cue_state = tracking_state.get("cue_state", "idle")

            self.detector_state_label.setText(detector_state)
            self.active_zone_label.setText(str(active_zone) if active_zone else "None")
            self.cue_state_label.setText(cue_state)

            # Nota: LayeredZoneEditor maneja la selección de zona internamente
            # No necesita set_active_zone() - la selección es interactiva

            # LEDs de cues (verificar Avolites)
            self._update_cue_leds()

            # Actualizar estado de calendario
            self._update_calendar_status()

        except Exception as e:
            print(f"[VisionArtistTab] Error actualizando estado: {e}")

    def _update_cue_leds(self):
        """Actualiza LEDs de cues según estado de Avolites."""
        try:
            if hasattr(self.vision_manager, 'cue_engine') and self.vision_manager.cue_engine:
                av = self.vision_manager.cue_engine.av
                # CUE_TRACK_1..8 = cues 70-77
                for i in range(8):
                    cue_id = 70 + i
                    self.led_track_cues[i].set_on(av.is_active(cue_id))
            else:
                for led in self.led_track_cues:
                    led.set_on(False)
        except Exception as e:
            pass

    def _update_calendar_status(self):
        """Actualiza el estado del calendario."""
        try:
            calendar_mode = self.vision_manager.get_calendar_mode()
            self.calendar_combo.setCurrentText(calendar_mode)

            if calendar_mode == "ARTISTA":
                self.calendar_status_label.setText("Artist Tracker: HABILITADO por calendario")
                self.calendar_status_label.setStyleSheet("color: #2ecc71; font-size: 10px;")
            else:
                self.calendar_status_label.setText(f"Artist Tracker: DESHABILITADO (modo: {calendar_mode})")
                self.calendar_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")
        except Exception as e:
            pass

    # NOTE: _on_camera_changed removed (USB removed in Phase 6.10)

    def _on_calendar_mode_changed(self, mode):
        """Callback cuando cambia el modo de calendario."""
        try:
            self.vision_manager.set_calendar_mode(mode)
            print(f"[VisionArtistTab] Modo calendario cambiado a {mode}")
        except Exception as e:
            print(f"[VisionArtistTab] Error cambiando modo calendario: {e}")

    def _on_apply(self):
        """Aplica cambios de configuración."""
        try:
            artist_tracker = self.vision_manager.get_artist_tracker()

            # Actualizar cooldown y smoothing
            artist_tracker.cooldown = self.cooldown_spin.value()
            artist_tracker.smoothing_frames = self.smoothing_spin.value()

            # Guardar en config JSON
            config = self.vision_manager.get_config()
            tracking_config = config.get_tracking_config()
            tracking_config["cooldown"] = self.cooldown_spin.value()
            tracking_config["smoothing"] = self.smoothing_spin.value()
            tracking_config["zones_horizontal"] = self.zones_spin.value()

            config.set("tracking", tracking_config)
            config.save()

            print(f"[VisionArtistTab] Configuración aplicada")

        except Exception as e:
            print(f"[VisionArtistTab] Error aplicando config: {e}")
