# ui/calendar_status_widget.py
"""
CalendarStatusWidget - Panel informativo del calendario

Muestra en tiempo real:
- Estado actual (modo + fuente)
- Reloj del sistema (BIOS)
- Timeline visual (si disponible)
- Permisos activos por módulo

SOLO LECTURA - No controla nada, solo visualiza.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QGridLayout
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont


# Colores por modo — aligned with WEB design
MODE_COLORS = {
    "OFF": "#ff5252",       # WEB: --red
    "BOLICHE": "#ff9800",   # WEB: --orange
    "ARTISTA": "#00e676",   # WEB: --green
    "TEATRO": "#42a5f5",    # WEB: --blue
    "ESCENA": "#9945ff",    # Purple
    "CLIMA": "#4dd0e1",     # WEB: --cyan
}

# Iconos de permisos (texto simple)
PERMISSION_ICONS = {
    "audio": "🎧",
    "analysis": "📊",
    "cues": "💡",
    "cameras": "🎥",
    "artist_tracking": "🎯",
    "haze_detection": "💨",
}


class CalendarStatusWidget(QWidget):
    """
    Panel informativo del estado del calendario.

    Uso:
        widget = CalendarStatusWidget()
        widget.set_calendar_manager(calendar_manager)
        # El widget se actualiza automáticamente cada segundo
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendar = None
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        """Configura la interfaz del widget"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # ===== TÍTULO =====
        title = QLabel("📅 CALENDARIO")
        title.setFont(QFont("", 11, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # ===== ESTADO ACTUAL =====
        state_frame = QFrame()
        state_frame.setFrameShape(QFrame.StyledPanel)
        state_frame.setStyleSheet("QFrame { background-color: #141418; border: 1px solid #2e2e38; border-radius: 16px; }")
        state_layout = QVBoxLayout(state_frame)
        state_layout.setContentsMargins(10, 8, 10, 8)
        state_layout.setSpacing(4)

        # Modo actual (grande)
        self.mode_label = QLabel("OFF")
        self.mode_label.setFont(QFont("", 18, QFont.Bold))
        self.mode_label.setAlignment(Qt.AlignCenter)
        self.mode_label.setStyleSheet(f"color: {MODE_COLORS['OFF']};")
        state_layout.addWidget(self.mode_label)

        # Fuente
        self.source_label = QLabel("Fuente: MANUAL")
        self.source_label.setAlignment(Qt.AlignCenter)
        self.source_label.setStyleSheet("color: #a6a6a6; font-size: 10px;")
        state_layout.addWidget(self.source_label)

        layout.addWidget(state_frame)

        # ===== RELOJ BIOS =====
        clock_frame = QFrame()
        clock_frame.setFrameShape(QFrame.StyledPanel)
        clock_layout = QHBoxLayout(clock_frame)
        clock_layout.setContentsMargins(8, 4, 8, 4)

        clock_icon = QLabel("🕐")
        clock_layout.addWidget(clock_icon)

        self.clock_label = QLabel("---")
        self.clock_label.setFont(QFont("", 12, QFont.Bold))
        self.clock_label.setStyleSheet("color: #f0f0f0;")
        clock_layout.addWidget(self.clock_label)

        clock_layout.addStretch()
        layout.addWidget(clock_frame)

        # ===== TIMELINE =====
        timeline_frame = QFrame()
        timeline_frame.setFrameShape(QFrame.StyledPanel)
        timeline_layout = QVBoxLayout(timeline_frame)
        timeline_layout.setContentsMargins(8, 6, 8, 6)
        timeline_layout.setSpacing(4)

        timeline_title = QLabel("Timeline")
        timeline_title.setStyleSheet("color: #8a8a8a; font-size: 10px;")
        timeline_layout.addWidget(timeline_title)

        self.timeline_bar = QProgressBar()
        self.timeline_bar.setRange(0, 100)
        self.timeline_bar.setValue(0)
        self.timeline_bar.setTextVisible(False)
        self.timeline_bar.setMaximumHeight(12)
        self.timeline_bar.setStyleSheet("""
            QProgressBar {
                background-color: #0a0a0f;
                border: 1px solid #2e2e38;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e676, stop:1 #4dd0e1);
                border-radius: 3px;
            }
        """)
        timeline_layout.addWidget(self.timeline_bar)

        self.timeline_info = QLabel("Timeline no disponible")
        self.timeline_info.setStyleSheet("color: #a6a6a6; font-size: 9px;")
        self.timeline_info.setAlignment(Qt.AlignCenter)
        timeline_layout.addWidget(self.timeline_info)

        layout.addWidget(timeline_frame)

        # ===== PERMISOS =====
        perms_frame = QFrame()
        perms_frame.setFrameShape(QFrame.StyledPanel)
        perms_layout = QVBoxLayout(perms_frame)
        perms_layout.setContentsMargins(8, 6, 8, 6)
        perms_layout.setSpacing(4)

        perms_title = QLabel("Permisos Activos")
        perms_title.setStyleSheet("color: #8a8a8a; font-size: 10px;")
        perms_layout.addWidget(perms_title)

        # Grid de permisos
        perms_grid = QGridLayout()
        perms_grid.setSpacing(4)

        self.perm_labels = {}
        permissions_order = ["audio", "cues", "cameras", "analysis", "artist_tracking", "haze_detection"]

        for i, perm in enumerate(permissions_order):
            row = i // 2
            col = i % 2

            icon = PERMISSION_ICONS.get(perm, "•")
            label = QLabel(f"{icon} {perm.replace('_', ' ').title()}")
            label.setStyleSheet("color: #8a8a8a; font-size: 9px;")
            self.perm_labels[perm] = label
            perms_grid.addWidget(label, row, col)

        perms_layout.addLayout(perms_grid)
        layout.addWidget(perms_frame)

        # ===== DESDE =====
        self.since_label = QLabel("Desde: ---")
        self.since_label.setStyleSheet("color: #8a8a8a; font-size: 9px;")
        self.since_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.since_label)

        layout.addStretch()

    def _setup_timer(self):
        """Configura el timer de actualización"""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_display)
        self._timer.start(1000)  # Actualizar cada segundo

    def set_calendar_manager(self, calendar_manager) -> None:
        """
        Conecta el CalendarManager para leer estado.

        Args:
            calendar_manager: Instancia de CalendarManager
        """
        self._calendar = calendar_manager
        self._update_display()

    def _update_display(self):
        """Actualiza todos los elementos del display"""
        # Actualizar reloj BIOS
        now = datetime.now()
        day_names = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        day_name = day_names[now.weekday()]
        self.clock_label.setText(f"{day_name} {now.strftime('%H:%M:%S')}")

        # Sin calendario conectado
        if self._calendar is None:
            self._set_disconnected_state()
            return

        try:
            state = self._calendar.get_state()
            self._update_mode(state)
            self._update_permissions(state.get("permissions", {}))
            self._update_timeline(state)
            self._update_since(state)
        except Exception as e:
            print(f"[CalendarStatusWidget] Error actualizando: {e}")
            self._set_disconnected_state()

    def _set_disconnected_state(self):
        """Muestra estado desconectado"""
        self.mode_label.setText("---")
        self.mode_label.setStyleSheet("color: #8a8a8a;")
        self.source_label.setText("Fuente: No conectado")
        self.timeline_info.setText("Calendario no conectado")
        self.timeline_bar.setValue(0)
        self.since_label.setText("Desde: ---")

        for label in self.perm_labels.values():
            label.setStyleSheet("color: #8a8a8a; font-size: 9px;")

    def _update_mode(self, state: Dict[str, Any]):
        """Actualiza el modo y fuente"""
        mode = state.get("current_climate", "OFF")
        source = state.get("source", "MANUAL")

        self.mode_label.setText(mode)
        color = MODE_COLORS.get(mode, "#7f8c8d")
        self.mode_label.setStyleSheet(f"color: {color};")

        self.source_label.setText(f"Fuente: {source}")

    def _update_permissions(self, permissions: Dict[str, Any]):
        """Actualiza los indicadores de permisos"""
        for perm, label in self.perm_labels.items():
            enabled = permissions.get(perm, False)
            icon = PERMISSION_ICONS.get(perm, "•")
            name = perm.replace('_', ' ').title()

            if enabled:
                label.setText(f"{icon} {name}: ON")
                label.setStyleSheet("color: #2ecc71; font-size: 9px; font-weight: bold;")
            else:
                label.setText(f"{icon} {name}: OFF")
                label.setStyleSheet("color: #e74c3c; font-size: 9px;")

    def _update_timeline(self, state: Dict[str, Any]):
        """Actualiza la barra de timeline"""
        since_str = state.get("since")
        if not since_str:
            self.timeline_info.setText("Timeline no disponible")
            self.timeline_bar.setValue(0)
            return

        try:
            # Parsear since
            if isinstance(since_str, str):
                since = datetime.fromisoformat(since_str)
            else:
                since = since_str

            now = datetime.now()
            elapsed = now - since
            elapsed_minutes = int(elapsed.total_seconds() / 60)
            elapsed_hours = elapsed_minutes // 60
            elapsed_mins = elapsed_minutes % 60

            # Mostrar tiempo transcurrido
            if elapsed_hours > 0:
                elapsed_text = f"{elapsed_hours}h {elapsed_mins}m en este modo"
            else:
                elapsed_text = f"{elapsed_mins}m en este modo"

            self.timeline_info.setText(elapsed_text)

            # Calcular progreso (asumiendo ciclos de 4 horas máx)
            max_minutes = 4 * 60  # 4 horas
            progress = min(100, int((elapsed_minutes / max_minutes) * 100))
            self.timeline_bar.setValue(progress)

            # Color según progreso
            if progress < 50:
                bar_color = "#3498db"  # Azul
            elif progress < 80:
                bar_color = "#f39c12"  # Naranja
            else:
                bar_color = "#e74c3c"  # Rojo

            self.timeline_bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: #34495e;
                    border-radius: 4px;
                }}
                QProgressBar::chunk {{
                    background-color: {bar_color};
                    border-radius: 4px;
                }}
            """)

        except Exception as e:
            self.timeline_info.setText("Timeline no disponible")
            self.timeline_bar.setValue(0)

    def _update_since(self, state: Dict[str, Any]):
        """Actualiza el label de 'desde'"""
        since_str = state.get("since")
        if not since_str:
            self.since_label.setText("Desde: ---")
            return

        try:
            if isinstance(since_str, str):
                since = datetime.fromisoformat(since_str)
            else:
                since = since_str

            self.since_label.setText(f"Desde: {since.strftime('%H:%M:%S')}")
        except Exception:
            self.since_label.setText("Desde: ---")

    def stop_timer(self):
        """Detiene el timer de actualización"""
        if self._timer:
            self._timer.stop()

    def start_timer(self):
        """Inicia el timer de actualización"""
        if self._timer:
            self._timer.start(1000)
