"""
VisionTab PRO - PySide6 UI for Vision System - ENHANCED VERSION
Interfaz completa con LEDs, edición de zonas, indicadores de cues
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGroupBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QSlider, QFrame, QGridLayout, QScrollArea, QListWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, Signal, QSize
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QBrush, QFont



class LEDIndicator(QWidget):
    """Widget LED indicator para mostrar estados."""

    def __init__(self, color=QColor(128, 128, 128), size=16, parent=None):
        super().__init__(parent)
        self.color = color
        self.size = size
        self.is_on = False
        self.setFixedSize(QSize(size, size))

    def set_color(self, color):
        """Establece el color del LED."""
        self.color = color
        self.update()

    def set_on(self, on):
        """Enciende/apaga el LED."""
        self.is_on = on
        self.update()

    def paintEvent(self, event):
        """Dibuja el LED."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Color según estado
        if self.is_on:
            color = self.color
        else:
            # Gris oscuro cuando está apagado
            color = QColor(60, 60, 60)

        # Dibujar círculo
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(40, 40, 40), 1))
        painter.drawEllipse(2, 2, self.size - 4, self.size - 4)


class ZoneEditor(QLabel):
    """
    Widget para edición visual de zonas con drag & drop y resize.
    Usado para DJ zones y Artist tracking zones.
    """
    zones_changed = Signal(list)

    def __init__(self, max_zones=5, parent=None):
        super().__init__(parent)
        self.max_zones = max_zones
        self.setMinimumSize(640, 480)
        self.setStyleSheet("border: 2px solid #2e2e38; background-color: #141418;")
        self.setAlignment(Qt.AlignCenter)

        # Estado de edición
        self.edit_mode = False
        self.zones = []
        self.current_frame = None
        self.selected_zone = None

        # Drag state
        self.dragging_zone = None
        self.drag_offset = QPoint(0, 0)
        self.resizing_zone = None
        self.resize_handle = None

        self.setMouseTracking(True)

    def set_frame(self, frame):
        """Actualiza el frame de fondo."""
        self.current_frame = frame
        self.update()

    def set_zones(self, zones):
        """Establece zonas desde config."""
        self.zones = zones.copy() if zones else []
        self.update()

    def get_zones(self):
        """Obtiene zonas actuales."""
        return self.zones.copy()

    def set_edit_mode(self, enabled):
        """Activa/desactiva modo edición."""
        self.edit_mode = enabled
        self.update()

    def add_zone(self):
        """Añade una nueva zona."""
        if len(self.zones) >= self.max_zones:
            return

        zone_id = len(self.zones) + 1

        # Zona por defecto en el centro
        self.zones.append({
            "id": zone_id,
            "x": 200,
            "y": 150,
            "width": 200,
            "height": 200
        })
        self.update()
        self.zones_changed.emit(self.zones)

    def remove_zone(self, zone_id):
        """Elimina una zona."""
        self.zones = [z for z in self.zones if z["id"] != zone_id]
        # Renumerar IDs
        for i, zone in enumerate(self.zones):
            zone["id"] = i + 1
        self.update()
        self.zones_changed.emit(self.zones)

    def remove_selected_zone(self):
        """Elimina la zona seleccionada."""
        if self.selected_zone:
            self.remove_zone(self.selected_zone["id"])
            self.selected_zone = None

    def paintEvent(self, event):
        """Dibuja el frame y las zonas."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dibujar frame de fondo si existe
        if self.current_frame is not None:
            try:
                h, w = self.current_frame.shape[:2]
                rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb_frame.data, w, h, w * 3, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)

                # Escalar al tamaño del widget
                scaled = pixmap.scaled(
                    self.width(), self.height(),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                x_offset = (self.width() - scaled.width()) // 2
                y_offset = (self.height() - scaled.height()) // 2
                painter.drawPixmap(x_offset, y_offset, scaled)
            except Exception as e:
                pass

        # Dibujar zonas
        for zone in self.zones:
            zone_id = zone["id"]
            x = zone["x"]
            y = zone["y"]
            w = zone["width"]
            h = zone["height"]

            # Color según si está seleccionada
            is_selected = (self.selected_zone and self.selected_zone["id"] == zone_id)

            if self.edit_mode:
                if is_selected:
                    color = QColor(255, 0, 0, 120)  # Rojo para seleccionada
                    pen_color = QColor(255, 0, 0)
                else:
                    color = QColor(255, 165, 0, 100)  # Naranja para edición
                    pen_color = QColor(255, 165, 0)
            else:
                color = QColor(0, 255, 0, 80)  # Verde normal
                pen_color = QColor(0, 255, 0)

            # Dibujar rectángulo
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(pen_color, 2))
            painter.drawRect(x, y, w, h)

            # Dibujar ID de zona
            painter.setPen(QPen(Qt.white))
            font = QFont("Arial", 12, QFont.Bold)
            painter.setFont(font)
            painter.drawText(x + 5, y + 20, f"Zone {zone_id}")

            # Dibujar handles de resize si está en modo edición
            if self.edit_mode:
                handle_size = 8
                # Bottom-right handle
                painter.setBrush(QBrush(Qt.white))
                painter.drawRect(x + w - handle_size, y + h - handle_size, handle_size, handle_size)

        painter.end()

    def mousePressEvent(self, event):
        """Inicia drag o resize."""
        if not self.edit_mode:
            return

        pos = event.pos()

        # Verificar si se clickeó un handle de resize
        for zone in self.zones:
            x = zone["x"]
            y = zone["y"]
            w = zone["width"]
            h = zone["height"]

            # Handle bottom-right
            handle_rect = QRect(x + w - 8, y + h - 8, 8, 8)
            if handle_rect.contains(pos):
                self.resizing_zone = zone
                self.resize_handle = "br"
                self.selected_zone = zone
                self.update()
                return

        # Verificar si se clickeó dentro de una zona
        for zone in self.zones:
            zone_rect = QRect(zone["x"], zone["y"], zone["width"], zone["height"])
            if zone_rect.contains(pos):
                self.dragging_zone = zone
                self.selected_zone = zone
                self.drag_offset = pos - QPoint(zone["x"], zone["y"])
                self.update()
                return

        # Click fuera de zonas = deseleccionar
        self.selected_zone = None
        self.update()

    def mouseMoveEvent(self, event):
        """Actualiza drag o resize."""
        if not self.edit_mode:
            return

        pos = event.pos()

        if self.dragging_zone:
            # Drag
            new_x = pos.x() - self.drag_offset.x()
            new_y = pos.y() - self.drag_offset.y()

            # Clamp dentro del widget
            new_x = max(0, min(new_x, self.width() - self.dragging_zone["width"]))
            new_y = max(0, min(new_y, self.height() - self.dragging_zone["height"]))

            self.dragging_zone["x"] = new_x
            self.dragging_zone["y"] = new_y
            self.update()

        elif self.resizing_zone:
            # Resize
            zone = self.resizing_zone
            if self.resize_handle == "br":
                new_width = pos.x() - zone["x"]
                new_height = pos.y() - zone["y"]

                # Tamaño mínimo
                new_width = max(50, new_width)
                new_height = max(50, new_height)

                # Clamp dentro del widget
                new_width = min(new_width, self.width() - zone["x"])
                new_height = min(new_height, self.height() - zone["y"])

                zone["width"] = new_width
                zone["height"] = new_height
                self.update()

    def mouseReleaseEvent(self, event):
        """Finaliza drag o resize."""
        if self.dragging_zone or self.resizing_zone:
            self.zones_changed.emit(self.zones)

        self.dragging_zone = None
        self.resizing_zone = None
        self.resize_handle = None


class VisionTab(QWidget):
    """
    Tab completo para Vision System PRO - ENHANCED VERSION.
    Incluye LEDs, edición de zonas, indicadores de cues.
    """

    def __init__(self, vision_manager, parent=None):
        super().__init__(parent)
        self.vision_manager = vision_manager

        # Estado interno
        self.current_frame = None
        self.system_running = False

        # Setup UI
        self._setup_ui()

        # Timer para actualización de estado
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(250)  # 250ms = 4 FPS UI
        self.update_timer.timeout.connect(self._update_state)
        self.update_timer.start()

        # Conectar callback de frames
        self.vision_manager.set_ui_callback(self.update_frame)

        # Actualización inicial
        self._update_state()

    def _setup_ui(self):
        """Construye la UI completa."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Panel izquierdo: Controles
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(5)

        left_layout.addWidget(self._build_control_panel())
        left_layout.addWidget(self._build_haze_panel())
        left_layout.addWidget(self._build_dj_panel())
        left_layout.addWidget(self._build_dancers_panel())  # ✅ VISION PRO v2: Panel bailarinas
        left_layout.addWidget(self._build_tracking_panel())
        left_layout.addStretch()

        # Scroll area para controles
        scroll = QScrollArea()
        scroll.setWidget(left_panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        scroll.setMaximumWidth(450)

        # Panel derecho: Preview
        right_panel = self._build_preview_panel()

        main_layout.addWidget(scroll)
        main_layout.addWidget(right_panel, 1)

    def _build_control_panel(self) -> QGroupBox:
        """Panel de control general del sistema."""
        group = QGroupBox("Sistema Vision PRO")
        layout = QVBoxLayout(group)

        # Estado general con LED
        status_layout = QHBoxLayout()
        self.system_led = LEDIndicator(QColor(0, 255, 0), 16)
        status_layout.addWidget(self.system_led)
        status_layout.addWidget(QLabel("Estado:"))
        self.status_label = QLabel("OFF")
        self.status_label.setStyleSheet("color: red; font-weight: bold; font-size: 14px;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # FPS
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("FPS:"))
        self.fps_label = QLabel("0.0")
        self.fps_label.setStyleSheet("color: #00ff00; font-weight: bold;")
        fps_layout.addWidget(self.fps_label)
        fps_layout.addStretch()
        layout.addLayout(fps_layout)

        # Camera state
        cam_layout = QHBoxLayout()
        cam_layout.addWidget(QLabel("Camera State:"))
        self.camera_state_label = QLabel("Disconnected")
        self.camera_state_label.setStyleSheet("color: #8a8a8a;")
        cam_layout.addWidget(self.camera_state_label)
        cam_layout.addStretch()
        layout.addLayout(cam_layout)

        # Toggle ON/OFF
        self.system_toggle = QPushButton("Iniciar Sistema")
        self.system_toggle.setCheckable(True)
        self.system_toggle.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 10px;
            }
            QPushButton:checked {
                background-color: #e74c3c;
            }
        """)
        self.system_toggle.clicked.connect(self._on_system_toggle)
        layout.addWidget(self.system_toggle)

        # NOTE: USB camera combos removed (USB removed in Phase 6.10)
        # IP cameras are configured via VisionConfigWidget
        layout.addWidget(QLabel("Cámaras IP (MJPEG only):"))
        layout.addWidget(QLabel("  → Configurar en pestaña 'IP Config'"))

        # Botones de reinicio
        self.restart_camera_btn = QPushButton("Reiniciar Cámara")
        self.restart_camera_btn.clicked.connect(self._on_restart_camera)
        layout.addWidget(self.restart_camera_btn)

        self.restart_system_btn = QPushButton("Reiniciar Sistema")
        self.restart_system_btn.clicked.connect(self._on_restart_system)
        layout.addWidget(self.restart_system_btn)

        return group

    def _build_preview_panel(self) -> QGroupBox:
        """Panel de preview en vivo."""
        group = QGroupBox("Vista Previa")
        layout = QVBoxLayout(group)

        # Canvas para preview
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(640, 480)
        self.preview_label.setStyleSheet("border: 2px solid #2e2e38; background-color: #000;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setText("No hay video")

        layout.addWidget(self.preview_label)

        return group

    def _build_haze_panel(self) -> QGroupBox:
        """Panel de HazeDetector PRO con LEDs de estado y cues."""
        group = QGroupBox("Haze Detector PRO")
        layout = QVBoxLayout(group)

        # Toggle enable - V10: persist=False, Calendar es autoridad
        self.haze_enabled_check = QCheckBox("Habilitado")
        self.haze_enabled_check.setChecked(False)
        self.haze_enabled_check.stateChanged.connect(
            lambda: self.vision_manager.enable_module("haze", self.haze_enabled_check.isChecked(), source="ui", persist=False)
        )
        layout.addWidget(self.haze_enabled_check)

        # LEDs de ESTADO (READY, SHOOTING, COOLDOWN)
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.StyledPanel)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(5, 5, 5, 5)

        status_layout.addWidget(QLabel("Status:"))

        self.haze_led_ready = LEDIndicator(QColor(52, 152, 219), 14)  # Azul
        status_layout.addWidget(self.haze_led_ready)
        status_layout.addWidget(QLabel("READY"))

        self.haze_led_shooting = LEDIndicator(QColor(243, 156, 18), 14)  # Amarillo
        status_layout.addWidget(self.haze_led_shooting)
        status_layout.addWidget(QLabel("SHOOTING"))

        self.haze_led_cooldown = LEDIndicator(QColor(231, 76, 60), 14)  # Rojo
        status_layout.addWidget(self.haze_led_cooldown)
        status_layout.addWidget(QLabel("COOLDOWN"))

        status_layout.addStretch()
        layout.addWidget(status_frame)

        # LEDs de CUES (LOW, MED, HIGH)
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QHBoxLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues:"))

        self.haze_led_low = LEDIndicator(QColor(0, 255, 0), 14)  # Verde
        cues_layout.addWidget(self.haze_led_low)
        cues_layout.addWidget(QLabel("LOW"))

        self.haze_led_med = LEDIndicator(QColor(0, 255, 0), 14)  # Verde
        cues_layout.addWidget(self.haze_led_med)
        cues_layout.addWidget(QLabel("MED"))

        self.haze_led_high = LEDIndicator(QColor(0, 255, 0), 14)  # Verde
        cues_layout.addWidget(self.haze_led_high)
        cues_layout.addWidget(QLabel("HIGH"))

        cues_layout.addStretch()
        layout.addWidget(cues_frame)

        # Estado actual
        grid = QGridLayout()

        grid.addWidget(QLabel("Detector State:"), 0, 0)
        self.haze_detector_state = QLabel("idle")
        self.haze_detector_state.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.haze_detector_state, 0, 1)

        grid.addWidget(QLabel("Nivel:"), 1, 0)
        self.haze_level_label = QLabel("0.0")
        self.haze_level_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.haze_level_label, 1, 1)

        grid.addWidget(QLabel("Contraste:"), 2, 0)
        self.haze_contrast_label = QLabel("0.0")
        grid.addWidget(self.haze_contrast_label, 2, 1)

        grid.addWidget(QLabel("Estado:"), 3, 0)
        self.haze_state_label = QLabel("LOW")
        grid.addWidget(self.haze_state_label, 3, 1)

        # FIX 2: Cooldown Countdown
        grid.addWidget(QLabel("Cooldown:"), 4, 0)
        self.haze_cooldown_label = QLabel("0s")
        self.haze_cooldown_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        grid.addWidget(self.haze_cooldown_label, 4, 1)

        layout.addLayout(grid)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        layout.addWidget(QLabel("Configuración:"))

        # Fire Duration
        fire_layout = QHBoxLayout()
        fire_layout.addWidget(QLabel("Fire Duration (s):"))
        self.haze_fire_spin = QDoubleSpinBox()
        self.haze_fire_spin.setRange(1.0, 10.0)
        self.haze_fire_spin.setValue(3.0)
        self.haze_fire_spin.setSingleStep(0.5)
        fire_layout.addWidget(self.haze_fire_spin)
        layout.addLayout(fire_layout)

        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(QLabel("Cooldown (s):"))
        self.haze_cooldown_spin = QSpinBox()
        self.haze_cooldown_spin.setRange(1, 300)
        self.haze_cooldown_spin.setValue(60)
        cooldown_layout.addWidget(self.haze_cooldown_spin)
        layout.addLayout(cooldown_layout)

        # Thresholds
        layout.addWidget(QLabel("Thresholds:"))

        thresh_grid = QGridLayout()

        thresh_grid.addWidget(QLabel("LOW:"), 0, 0)
        self.haze_thresh_low = QSpinBox()
        self.haze_thresh_low.setRange(0, 100)
        self.haze_thresh_low.setValue(30)
        thresh_grid.addWidget(self.haze_thresh_low, 0, 1)

        thresh_grid.addWidget(QLabel("MED:"), 1, 0)
        self.haze_thresh_med = QSpinBox()
        self.haze_thresh_med.setRange(0, 100)
        self.haze_thresh_med.setValue(50)
        thresh_grid.addWidget(self.haze_thresh_med, 1, 1)

        thresh_grid.addWidget(QLabel("HIGH:"), 2, 0)
        self.haze_thresh_high = QSpinBox()
        self.haze_thresh_high.setRange(0, 100)
        self.haze_thresh_high.setValue(70)
        thresh_grid.addWidget(self.haze_thresh_high, 2, 1)

        layout.addLayout(thresh_grid)

        # Target Density (FIX 1)
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Densidad Objetivo:"))
        self.haze_target_combo = QComboBox()
        self.haze_target_combo.addItems(["LOW", "MEDIUM", "HIGH"])
        self.haze_target_combo.setCurrentText("LOW")
        target_layout.addWidget(self.haze_target_combo)
        layout.addLayout(target_layout)

        # Botones
        btn_layout = QHBoxLayout()

        self.haze_calibrate_btn = QPushButton("Calibrar Baseline")
        self.haze_calibrate_btn.clicked.connect(self._on_calibrate_haze)
        btn_layout.addWidget(self.haze_calibrate_btn)

        self.haze_apply_btn = QPushButton("Aplicar Cambios")
        self.haze_apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.haze_apply_btn.clicked.connect(self._on_apply_haze_config)
        btn_layout.addWidget(self.haze_apply_btn)

        layout.addLayout(btn_layout)

        return group

    def _build_dj_panel(self) -> QGroupBox:
        """Panel de DJDetector PRO con edición de zonas y LEDs de cues."""
        group = QGroupBox("DJ Detector PRO")
        layout = QVBoxLayout(group)

        # Toggle enable - V10: persist=False, Calendar es autoridad
        self.dj_enabled_check = QCheckBox("Habilitado")
        self.dj_enabled_check.setChecked(False)
        self.dj_enabled_check.stateChanged.connect(
            lambda: self.vision_manager.enable_module("dj", self.dj_enabled_check.isChecked(), source="ui", persist=False)
        )
        layout.addWidget(self.dj_enabled_check)

        # LEDs de CUES (DJ_1 a DJ_5)
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QHBoxLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues:"))

        self.dj_leds = []
        for i in range(1, 6):
            led = LEDIndicator(QColor(0, 255, 0), 12)
            self.dj_leds.append(led)
            cues_layout.addWidget(led)
            cues_layout.addWidget(QLabel(f"DJ{i}"))

        cues_layout.addStretch()
        layout.addWidget(cues_frame)

        # Estado actual
        grid = QGridLayout()

        grid.addWidget(QLabel("Detector State:"), 0, 0)
        self.dj_detector_state = QLabel("disabled")
        self.dj_detector_state.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.dj_detector_state, 0, 1)

        grid.addWidget(QLabel("Zona Activa:"), 1, 0)
        self.dj_zone_label = QLabel("None")
        self.dj_zone_label.setStyleSheet("font-weight: bold; color: #3498db;")
        grid.addWidget(self.dj_zone_label, 1, 1)

        grid.addWidget(QLabel("Cue State:"), 2, 0)
        self.dj_cue_state = QLabel("inactive")
        grid.addWidget(self.dj_cue_state, 2, 1)

        layout.addLayout(grid)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        layout.addWidget(QLabel("Zonas (1-5):"))

        # Lista de zonas
        self.dj_zones_list = QListWidget()
        self.dj_zones_list.setMaximumHeight(100)
        layout.addWidget(self.dj_zones_list)

        # Botones de gestión
        btn_row1 = QHBoxLayout()

        self.dj_add_zone_btn = QPushButton("Añadir Zona")
        self.dj_add_zone_btn.clicked.connect(self._on_add_dj_zone)
        btn_row1.addWidget(self.dj_add_zone_btn)

        self.dj_remove_zone_btn = QPushButton("Eliminar Seleccionada")
        self.dj_remove_zone_btn.clicked.connect(self._on_remove_dj_zone)
        btn_row1.addWidget(self.dj_remove_zone_btn)

        layout.addLayout(btn_row1)

        # Edición visual
        self.dj_edit_btn = QPushButton("Editar Zonas Visualmente")
        self.dj_edit_btn.setCheckable(True)
        self.dj_edit_btn.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold;")
        self.dj_edit_btn.clicked.connect(self._on_toggle_dj_edit)
        layout.addWidget(self.dj_edit_btn)

        self.dj_save_btn = QPushButton("Guardar Zonas")
        self.dj_save_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.dj_save_btn.clicked.connect(self._on_save_dj_zones)
        layout.addWidget(self.dj_save_btn)

        return group

    def _build_dancers_panel(self) -> QGroupBox:
        """
        ✅ VISION PRO v2: Panel de detección de bailarinas.
        Muestra estado de bailarinas left/right + total count.
        """
        group = QGroupBox("Bailarinas Detector")
        layout = QVBoxLayout(group)

        # Grid para mostrar estados
        grid = QGridLayout()

        # Bailarina izquierda
        grid.addWidget(QLabel("Left:"), 0, 0)
        self.lbl_dancers_left = QLabel("—")
        self.lbl_dancers_left.setStyleSheet("font-weight: bold; color: #3498db;")
        grid.addWidget(self.lbl_dancers_left, 0, 1)

        # Bailarina derecha
        grid.addWidget(QLabel("Right:"), 1, 0)
        self.lbl_dancers_right = QLabel("—")
        self.lbl_dancers_right.setStyleSheet("font-weight: bold; color: #9b59b6;")
        grid.addWidget(self.lbl_dancers_right, 1, 1)

        # Total
        grid.addWidget(QLabel("Total:"), 2, 0)
        self.lbl_dancers_count = QLabel("0")
        self.lbl_dancers_count.setStyleSheet("font-weight: bold; font-size: 14px; color: #27ae60;")
        grid.addWidget(self.lbl_dancers_count, 2, 1)

        layout.addLayout(grid)

        return group

    def _build_tracking_panel(self) -> QGroupBox:
        """Panel de ArtistTracker PRO con zonas dinámicas y LEDs de cues."""
        group = QGroupBox("Artist Tracker PRO")
        layout = QVBoxLayout(group)

        # Toggle enable - V10: persist=False, Calendar es autoridad
        self.tracking_enabled_check = QCheckBox("Habilitado")
        self.tracking_enabled_check.setChecked(False)
        self.tracking_enabled_check.stateChanged.connect(
            lambda: self.vision_manager.enable_module("tracking", self.tracking_enabled_check.isChecked(), source="ui", persist=False)
        )
        layout.addWidget(self.tracking_enabled_check)

        # LEDs de CUES (TRACK_1 a TRACK_8)
        cues_frame = QFrame()
        cues_frame.setFrameShape(QFrame.StyledPanel)
        cues_layout = QGridLayout(cues_frame)
        cues_layout.setContentsMargins(5, 5, 5, 5)

        cues_layout.addWidget(QLabel("Cues:"), 0, 0, 1, 2)

        self.tracking_leds = []
        for i in range(1, 9):
            led = LEDIndicator(QColor(0, 255, 0), 12)
            self.tracking_leds.append(led)
            row = 1 + (i - 1) // 4
            col = ((i - 1) % 4) * 2
            cues_layout.addWidget(led, row, col)
            cues_layout.addWidget(QLabel(f"T{i}"), row, col + 1)

        layout.addWidget(cues_frame)

        # Estado actual
        grid = QGridLayout()

        grid.addWidget(QLabel("Detector State:"), 0, 0)
        self.tracking_detector_state = QLabel("disabled")
        self.tracking_detector_state.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.tracking_detector_state, 0, 1)

        grid.addWidget(QLabel("Zona Actual:"), 1, 0)
        self.tracking_zone_label = QLabel("None")
        self.tracking_zone_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        grid.addWidget(self.tracking_zone_label, 1, 1)

        grid.addWidget(QLabel("Cue State:"), 2, 0)
        self.tracking_cue_state = QLabel("inactive")
        grid.addWidget(self.tracking_cue_state, 2, 1)

        layout.addLayout(grid)

        # Separador
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        layout.addWidget(QLabel("Configuración:"))

        # Cooldown
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(QLabel("Cooldown (s):"))
        self.tracking_cooldown_spin = QDoubleSpinBox()
        self.tracking_cooldown_spin.setRange(0.1, 5.0)
        self.tracking_cooldown_spin.setValue(0.5)
        self.tracking_cooldown_spin.setSingleStep(0.1)
        cooldown_layout.addWidget(self.tracking_cooldown_spin)
        layout.addLayout(cooldown_layout)

        # Smoothing
        smoothing_layout = QHBoxLayout()
        smoothing_layout.addWidget(QLabel("Smoothing:"))
        self.tracking_smoothing_spin = QSpinBox()
        self.tracking_smoothing_spin.setRange(1, 10)
        self.tracking_smoothing_spin.setValue(3)
        smoothing_layout.addWidget(self.tracking_smoothing_spin)
        layout.addLayout(smoothing_layout)

        # Botón aplicar
        self.tracking_apply_btn = QPushButton("Aplicar Cambios")
        self.tracking_apply_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.tracking_apply_btn.clicked.connect(self._on_apply_tracking_config)
        layout.addWidget(self.tracking_apply_btn)

        return group

    # ===== CALLBACKS =====

    def update_frame(self, frame):
        """
        Callback para recibir frames desde VisionManager.
        Actualiza el preview con overlays de zonas.
        """
        if frame is None:
            return

        try:
            self.current_frame = frame.copy()

            # Dibujar overlays
            display_frame = frame.copy()

            # Overlay DJ zones
            if self.dj_enabled_check.isChecked():
                dj_zones = self.vision_manager.get_dj_detector().get_state().get("zones", [])
                for zone in dj_zones:
                    x = zone["x"]
                    y = zone["y"]
                    w = zone["width"]
                    h = zone["height"]
                    zone_id = zone["id"]

                    # Color verde si es la zona activa
                    dj_state = self.vision_manager.get_vision_state().get_dj_state()
                    active_zone = dj_state.get("active_zone")

                    if active_zone == zone_id:
                        color = (0, 255, 0)  # Verde (activa)
                    else:
                        color = (255, 165, 0)  # Naranja (inactiva)

                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                    cv2.putText(display_frame, f"DJ {zone_id}", (x + 5, y + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # Overlay tracking zones (8 barras verticales)
            if self.tracking_enabled_check.isChecked():
                h, w = display_frame.shape[:2]
                zone_width = w // 8

                tracking_state = self.vision_manager.get_vision_state().get_tracking_state()
                active_zone = tracking_state.get("zone")

                for i in range(8):
                    x1 = i * zone_width
                    x2 = (i + 1) * zone_width

                    # Color si es la zona activa
                    if active_zone == (i + 1):
                        color = (0, 255, 255)  # Amarillo (activa)
                        thickness = 3
                    else:
                        color = (100, 100, 100)  # Gris (inactiva)
                        thickness = 1

                    cv2.line(display_frame, (x2, 0), (x2, h), color, thickness)

            # Convertir a QPixmap
            h, w = display_frame.shape[:2]
            rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb_frame.data, w, h, w * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img)

            # Escalar manteniendo aspect ratio
            scaled = pixmap.scaled(
                self.preview_label.width(),
                self.preview_label.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.preview_label.setPixmap(scaled)

        except Exception as e:
            print(f"[VisionTab] Error actualizando frame: {e}")

    def _update_state(self):
        """Actualiza el estado de todos los widgets desde VisionManager."""
        try:
            state = self.vision_manager.get_state()

            # Sistema general
            system_state = state.get("system", {})
            running = system_state.get("enabled", False)

            if running:
                self.status_label.setText("Running")
                self.status_label.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 14px;")
                self.system_toggle.setText("Detener Sistema")
                self.system_toggle.setChecked(True)
                self.system_led.set_on(True)
                self.camera_state_label.setText("Connected")
                self.camera_state_label.setStyleSheet("color: #2ecc71;")
            else:
                self.status_label.setText("OFF")
                self.status_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 14px;")
                self.system_toggle.setText("Iniciar Sistema")
                self.system_toggle.setChecked(False)
                self.system_led.set_on(False)
                self.camera_state_label.setText("Disconnected")
                self.camera_state_label.setStyleSheet("color: #8a8a8a;")

            self.system_running = running

            # FPS
            fps = system_state.get("fps", 0.0)
            self.fps_label.setText(f"{fps:.1f}")

            # Haze
            haze_state = state.get("haze", {})
            level = haze_state.get("level", 0.0)
            contrast = haze_state.get("contrast", 0.0)
            haze_status = haze_state.get("status", "READY")
            haze_state_str = haze_state.get("state", "LOW")
            cooldown_remaining = haze_state.get("cooldown_remaining", 0.0)

            self.haze_level_label.setText(f"{level:.1f}")
            self.haze_contrast_label.setText(f"{contrast:.1f}")
            self.haze_state_label.setText(haze_state_str)
            self.haze_detector_state.setText(haze_status.lower())

            # FIX 2: Actualizar cooldown countdown
            self.haze_cooldown_label.setText(f"{int(cooldown_remaining)}s")

            # LEDs de estado Haze
            self.haze_led_ready.set_on(haze_status == "READY")
            self.haze_led_shooting.set_on(haze_status == "SHOOTING")
            self.haze_led_cooldown.set_on(haze_status == "COOLDOWN" or cooldown_remaining > 0)

            # LEDs de cues Haze (verificar si cues están activos desde Avolites)
            self._update_haze_cue_leds()

            # DJ
            dj_state = state.get("dj", {})
            dj_zone = dj_state.get("active_zone")
            dj_state_str = dj_state.get("state", "disabled")

            self.dj_zone_label.setText(str(dj_zone) if dj_zone else "None")
            self.dj_detector_state.setText(dj_state_str)
            self.dj_cue_state.setText("active" if dj_zone else "inactive")

            # LEDs de cues DJ
            self._update_dj_cue_leds()

            # Actualizar lista de zonas DJ
            dj_zones = self.vision_manager.get_dj_detector().get_state().get("zones", [])
            self.dj_zones_list.clear()
            for zone in dj_zones:
                self.dj_zones_list.addItem(f"Zona {zone['id']}: ({zone['x']}, {zone['y']}) {zone['width']}x{zone['height']}")

            # Actualizar estado de bailarinas
            dancers = state.get("dancers", {"left": False, "right": False, "count": 0})
            self.lbl_dancers_left.setText("ON" if dancers["left"] else "—")
            self.lbl_dancers_left.setStyleSheet(
                f"font-weight: bold; color: {'#27ae60' if dancers['left'] else '#8a8a8a'};"
            )
            self.lbl_dancers_right.setText("ON" if dancers["right"] else "—")
            self.lbl_dancers_right.setStyleSheet(
                f"font-weight: bold; color: {'#9b59b6' if dancers['right'] else '#8a8a8a'};"
            )
            self.lbl_dancers_count.setText(f"{dancers['count']}")
            self.lbl_dancers_count.setStyleSheet(
                f"font-weight: bold; font-size: 14px; color: {'#27ae60' if dancers['count'] > 0 else '#8a8a8a'};"
            )

            # Tracking
            tracking_state = state.get("tracking", {})
            tracking_zone = tracking_state.get("zone")
            tracking_state_str = tracking_state.get("state", "disabled")

            # Verificar si el modo actual permite tracking
            tracker_state_obj = self.vision_manager.get_artist_tracker().get_state()
            mode_show_artist = tracker_state_obj.get("mode_show_artist", False)

            if not mode_show_artist:
                self.tracking_detector_state.setText("DESHABILITADO POR MODO ACTUAL")
                self.tracking_detector_state.setStyleSheet("font-weight: bold; color: #e74c3c;")
                self.tracking_zone_label.setText("N/A")
                self.tracking_cue_state.setText("disabled")
            else:
                self.tracking_zone_label.setText(str(tracking_zone) if tracking_zone else "None")
                self.tracking_detector_state.setText(tracking_state_str)
                self.tracking_detector_state.setStyleSheet("font-weight: bold;")
                self.tracking_cue_state.setText("active" if tracking_zone else "inactive")

            # LEDs de cues Tracking
            self._update_tracking_cue_leds()

        except Exception as e:
            print(f"[VisionTab] Error actualizando estado: {e}")

    def _update_haze_cue_leds(self):
        """Actualiza LEDs de cues de Haze según estado de Avolites."""
        try:
            # Obtener acceso al cue_engine si está disponible
            if hasattr(self.vision_manager, 'cue_engine') and self.vision_manager.cue_engine:
                av = self.vision_manager.cue_engine.av
                # Cues: 60 (LOW), 61 (MED), 62 (HIGH)
                self.haze_led_low.set_on(av.is_active(60))
                self.haze_led_med.set_on(av.is_active(61))
                self.haze_led_high.set_on(av.is_active(62))
            else:
                # Sin acceso a Avolites, apagar todos
                self.haze_led_low.set_on(False)
                self.haze_led_med.set_on(False)
                self.haze_led_high.set_on(False)
        except Exception as e:
            print(f"[VisionTab] Error actualizando LEDs Haze: {e}")

    def _update_dj_cue_leds(self):
        """Actualiza LEDs de cues de DJ según estado de Avolites."""
        try:
            if hasattr(self.vision_manager, 'cue_engine') and self.vision_manager.cue_engine:
                av = self.vision_manager.cue_engine.av
                # Cues: 65-69 (DJ_1 a DJ_5)
                for i in range(5):
                    cue_id = 65 + i
                    self.dj_leds[i].set_on(av.is_active(cue_id))
            else:
                for led in self.dj_leds:
                    led.set_on(False)
        except Exception as e:
            print(f"[VisionTab] Error actualizando LEDs DJ: {e}")

    def _update_tracking_cue_leds(self):
        """Actualiza LEDs de cues de Tracking según estado de Avolites."""
        try:
            if hasattr(self.vision_manager, 'cue_engine') and self.vision_manager.cue_engine:
                av = self.vision_manager.cue_engine.av
                # Cues: 70-77 (TRACK_1 a TRACK_8)
                for i in range(8):
                    cue_id = 70 + i
                    self.tracking_leds[i].set_on(av.is_active(cue_id))
            else:
                for led in self.tracking_leds:
                    led.set_on(False)
        except Exception as e:
            print(f"[VisionTab] Error actualizando LEDs Tracking: {e}")

    # ===== ACTIONS =====

    def _on_system_toggle(self):
        """Toggle ON/OFF del sistema."""
        if self.system_toggle.isChecked():
            self.vision_manager.start()
            print("[VisionTab] Sistema iniciado")
        else:
            self.vision_manager.stop()
            print("[VisionTab] Sistema detenido")

    # NOTE: _on_camera_*_change methods removed (USB removed in Phase 6.10)

    def _on_restart_camera(self):
        """Reinicia la cámara."""
        self.vision_manager.restart_camera()
        print("[VisionTab] Cámara reiniciada")

    def _on_restart_system(self):
        """Reinicia el sistema completo."""
        self.vision_manager.restart()
        print("[VisionTab] Sistema reiniciado")

    def _on_calibrate_haze(self):
        """Calibra el baseline de haze."""
        self.vision_manager.calibrate_haze_baseline()
        print("[VisionTab] Baseline de haze recalibrado")

    def _on_apply_haze_config(self):
        """Aplica cambios de configuración de Haze."""
        try:
            haze_detector = self.vision_manager.get_haze_detector()

            # Actualizar thresholds
            haze_detector.threshold_low = self.haze_thresh_low.value()
            haze_detector.threshold_med = self.haze_thresh_med.value()
            haze_detector.threshold_high = self.haze_thresh_high.value()

            # Actualizar fire duration y cooldown
            haze_detector.fire_duration = self.haze_fire_spin.value()
            haze_detector.cooldown_min = self.haze_cooldown_spin.value()
            haze_detector.cooldown_max = self.haze_cooldown_spin.value()

            # FIX 1: Actualizar target_density
            haze_detector.target_density = self.haze_target_combo.currentText()

            # Guardar en config JSON
            config = self.vision_manager.get_config()
            haze_config = config.get_haze_config()
            haze_config["fire_duration"] = self.haze_fire_spin.value()
            haze_config["cooldown_min"] = self.haze_cooldown_spin.value()
            haze_config["cooldown_max"] = self.haze_cooldown_spin.value()
            haze_config["threshold_low"] = self.haze_thresh_low.value()
            haze_config["threshold_med"] = self.haze_thresh_med.value()
            haze_config["threshold_high"] = self.haze_thresh_high.value()
            haze_config["target_density"] = self.haze_target_combo.currentText()

            config.set("haze", haze_config)
            config.save()

            print("[VisionTab] Configuración de Haze aplicada y guardada (target_density={})".format(
                self.haze_target_combo.currentText()))

        except Exception as e:
            print(f"[VisionTab] Error aplicando config Haze: {e}")

    def _on_add_dj_zone(self):
        """Añade una nueva zona DJ."""
        try:
            dj_zones = self.vision_manager.get_dj_detector().get_state().get("zones", [])
            if len(dj_zones) >= 5:
                print("[VisionTab] Máximo 5 zonas DJ")
                return

            zone_id = len(dj_zones) + 1
            new_zone = {
                "id": zone_id,
                "x": 100 + (zone_id * 20),
                "y": 100,
                "width": 200,
                "height": 200
            }

            dj_zones.append(new_zone)
            self.vision_manager.set_dj_zones(dj_zones)
            print(f"[VisionTab] Zona DJ {zone_id} añadida")

        except Exception as e:
            print(f"[VisionTab] Error añadiendo zona DJ: {e}")

    def _on_remove_dj_zone(self):
        """Elimina la zona DJ seleccionada."""
        try:
            selected = self.dj_zones_list.currentRow()
            if selected < 0:
                print("[VisionTab] No hay zona seleccionada")
                return

            dj_zones = self.vision_manager.get_dj_detector().get_state().get("zones", [])
            if selected >= len(dj_zones):
                return

            dj_zones.pop(selected)

            # Renumerar IDs
            for i, zone in enumerate(dj_zones):
                zone["id"] = i + 1

            self.vision_manager.set_dj_zones(dj_zones)
            print(f"[VisionTab] Zona DJ eliminada")

        except Exception as e:
            print(f"[VisionTab] Error eliminando zona DJ: {e}")

    def _on_toggle_dj_edit(self):
        """Toggle modo edición visual de zonas DJ."""
        if self.dj_edit_btn.isChecked():
            self.dj_edit_btn.setText("Finalizar Edición")
            print("[VisionTab] Modo edición DJ activado")
            # TODO: Mostrar editor visual en popup o reemplazar preview
        else:
            self.dj_edit_btn.setText("Editar Zonas Visualmente")
            print("[VisionTab] Modo edición DJ desactivado")

    def _on_save_dj_zones(self):
        """Guarda las zonas DJ actuales."""
        try:
            dj_zones = self.vision_manager.get_dj_detector().get_state().get("zones", [])
            self.vision_manager.set_dj_zones(dj_zones)
            self.vision_manager.save_config()
            print("[VisionTab] Zonas DJ guardadas")

        except Exception as e:
            print(f"[VisionTab] Error guardando zonas DJ: {e}")

    def _on_apply_tracking_config(self):
        """Aplica configuración de Tracking."""
        try:
            config = self.vision_manager.get_config()

            tracking_config = config.get_tracking_config()
            tracking_config["cooldown"] = self.tracking_cooldown_spin.value()
            tracking_config["smoothing"] = self.tracking_smoothing_spin.value()

            config.set("tracking", tracking_config)
            config.save()

            # Actualizar detector
            tracker = self.vision_manager.get_artist_tracker()
            tracker.cooldown = self.tracking_cooldown_spin.value()
            tracker.smoothing_frames = self.tracking_smoothing_spin.value()

            print("[VisionTab] Configuración de Tracking aplicada")

        except Exception as e:
            print(f"[VisionTab] Error aplicando config Tracking: {e}")
