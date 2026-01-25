# ui/calendar_schedule_editor.py
"""
CalendarScheduleEditor v7.0 - Editor visual de horarios semanales.

V7.0 CAMBIOS:
- ELIMINADO dropdown de modo separado del TimeBlockWidget
- UNIFICADO en panel "Configurar" con:
  - Sección MODO (ComboBox single-select)
  - Sección EXTRAS (checkboxes para módulos adicionales)
- Guardado: mode + actions[] en calendar.json
- Layout mejorado sin superposiciones

Widget para editar el calendario de bloques horarios:
- Vista semanal con 7 columnas
- Bloques editables con from/to + panel unificado de modo+extras
- Colores por modo canónico
- Glow verde pulsante en bloque activo

MODOS CANÓNICOS:
clima_1, clima_2, clima_3, clima_4, teatro, artista,
boliche_inicio, boliche_desarrollo, boliche_fin, apagado

ACCIONES EXTRA (opcionales):
vision_haze, vision_dj, vision_artista, tracking_cam,
dj_detection, cues_clima

SOLO UI - No ejecuta acciones del sistema.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QComboBox, QTimeEdit, QScrollArea,
    QGridLayout, QMessageBox, QCheckBox, QSizePolicy,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QTime, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QFont, QColor


# ==================== MODOS CANÓNICOS ====================

CANONICAL_MODES = [
    "clima_1",
    "clima_2",
    "clima_3",
    "clima_4",
    "teatro",
    "artista",
    "boliche_inicio",
    "boliche_desarrollo",
    "boliche_fin",
    "apagado",
]

# Colores por modo
MODE_COLORS = {
    "clima_1": "#1abc9c",
    "clima_2": "#16a085",
    "clima_3": "#2ecc71",
    "clima_4": "#27ae60",
    "teatro": "#3498db",
    "artista": "#9b59b6",
    "boliche_inicio": "#f39c12",
    "boliche_desarrollo": "#e67e22",
    "boliche_fin": "#e74c3c",
    "apagado": "#7f8c8d",
}

# ==================== ACCIONES EXTRA ====================

# Acciones que el usuario puede agregar manualmente
EXTRA_ACTIONS = [
    "vision_haze",
    "vision_dj",
    "vision_artista",
    "tracking_cam",
    "dj_detection",
    "cues_clima",
]

# Configuración visual de acciones extra
EXTRA_ACTION_CONFIG = {
    "vision_haze": {"icon": "💨", "name": "Haze"},
    "vision_dj": {"icon": "🎧", "name": "DJ Cues"},
    "vision_artista": {"icon": "🎤", "name": "Artista"},
    "tracking_cam": {"icon": "📹", "name": "Tracking"},
    "dj_detection": {"icon": "👁", "name": "DJ Detect"},
    "cues_clima": {"icon": "🌡", "name": "Clima"},
}

# ==================== LEGACY MODE MAP ====================
# Acciones implícitas por modo (el usuario NO las ve ni edita)

LEGACY_MODE_MAP = {
    "clima_1": ["cues_clima"],
    "clima_2": ["cues_clima"],
    "clima_3": ["cues_clima"],
    "clima_4": ["cues_clima"],
    "teatro": ["vision_artista", "tracking_cam", "dj_detection"],
    "artista": ["vision_artista", "tracking_cam"],
    "boliche_inicio": [],
    "boliche_desarrollo": ["audio_911", "vision_haze", "vision_dj"],
    "boliche_fin": ["audio_911", "vision_haze", "vision_dj", "dj_detection"],
    "apagado": ["system_idle"],
}

# Nombres de días
DAY_NAMES = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo"
}

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ==================== DEBUG ====================
DEBUG_ENABLED = True


def _log(msg: str):
    if DEBUG_ENABLED:
        print(f"[CalendarUI] {msg}")


# ==================== MODE AND ACTIONS PANEL (UNIFIED) ====================

class ModeAndActionsPanel(QFrame):
    """
    Panel unificado para seleccionar MODO + ACCIONES EXTRAS.

    V7.0: Reemplaza el dropdown de modo separado + panel de extras.
    - Sección MODO: ComboBox single-select con modos canónicos
    - Sección EXTRAS: Checkboxes para acciones adicionales
    """

    changed = Signal()
    mode_changed = Signal(str)  # Emite cuando cambia el modo

    def __init__(self, mode: str = "clima_1", actions: List[str] = None, parent=None):
        super().__init__(parent)
        self._current_mode = mode if mode in CANONICAL_MODES else "clima_1"
        self._selected_actions: Set[str] = set(actions or [])
        self._checkboxes: Dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.setStyleSheet("""
            QFrame {
                background-color: #1a252f;
                border: 1px solid #3498db;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # ==================== SECCIÓN MODO ====================
        mode_section = QVBoxLayout()
        mode_section.setSpacing(4)

        mode_title = QLabel("🎯 MODO (principal)")
        mode_title.setFont(QFont("", 10, QFont.Bold))
        mode_title.setStyleSheet("color: #f39c12; border: none;")
        mode_section.addWidget(mode_title)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(CANONICAL_MODES)
        self.mode_combo.setCurrentText(self._current_mode)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.mode_combo.setStyleSheet("""
            QComboBox {
                background: #2c3e50;
                color: white;
                border: 2px solid #f39c12;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
                min-width: 150px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #f39c12;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: #2c3e50;
                color: white;
                selection-background-color: #f39c12;
                border: 1px solid #f39c12;
            }
        """)
        mode_section.addWidget(self.mode_combo)

        layout.addLayout(mode_section)

        # Separador visual
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background-color: #34495e; border: none; max-height: 1px;")
        layout.addWidget(separator)

        # ==================== SECCIÓN EXTRAS ====================
        extras_section = QVBoxLayout()
        extras_section.setSpacing(4)

        extras_title = QLabel("⚡ EXTRAS / MÓDULOS")
        extras_title.setFont(QFont("", 10, QFont.Bold))
        extras_title.setStyleSheet("color: #3498db; border: none;")
        extras_section.addWidget(extras_title)

        # Grid de checkboxes 2x3
        grid = QGridLayout()
        grid.setSpacing(6)
        grid.setContentsMargins(0, 4, 0, 0)

        for i, action in enumerate(EXTRA_ACTIONS):
            cfg = EXTRA_ACTION_CONFIG.get(action, {})
            row = i // 2
            col = i % 2

            cb = QCheckBox(f"{cfg.get('icon', '?')} {cfg.get('name', action)}")
            cb.setChecked(action in self._selected_actions)
            cb.setStyleSheet("""
                QCheckBox {
                    color: #ecf0f1;
                    font-size: 11px;
                    border: none;
                    padding: 2px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QCheckBox::indicator:checked {
                    background: #3498db;
                    border: 2px solid #2980b9;
                    border-radius: 4px;
                }
                QCheckBox::indicator:unchecked {
                    background: #34495e;
                    border: 2px solid #7f8c8d;
                    border-radius: 4px;
                }
                QCheckBox:hover {
                    background: rgba(52, 152, 219, 0.1);
                    border-radius: 3px;
                }
            """)
            cb.stateChanged.connect(lambda state, a=action: self._on_action_toggled(a, state))
            self._checkboxes[action] = cb
            grid.addWidget(cb, row, col)

        extras_section.addLayout(grid)
        layout.addLayout(extras_section)

        # Contador de total
        self.counter_label = QLabel("")
        self.counter_label.setStyleSheet("color: #7f8c8d; font-size: 9px; border: none;")
        layout.addWidget(self.counter_label)

        self._update_counter()

    def _on_mode_changed(self, mode: str):
        self._current_mode = mode
        self.mode_changed.emit(mode)
        self.changed.emit()

    def _on_action_toggled(self, action: str, state: int):
        if state == Qt.Checked:
            self._selected_actions.add(action)
        else:
            self._selected_actions.discard(action)
        self._update_counter()
        self.changed.emit()

    def _update_counter(self):
        count = len(self._selected_actions)
        total = 1 + count  # 1 (modo) + extras
        if total > 5:
            self.counter_label.setText(f"⚠ Máximo 5 total ({total}/5)")
            self.counter_label.setStyleSheet("color: #e74c3c; font-size: 9px; border: none;")
        else:
            self.counter_label.setText(f"Total: {total}/5 (modo + {count} extras)")
            self.counter_label.setStyleSheet("color: #7f8c8d; font-size: 9px; border: none;")

    def get_mode(self) -> str:
        return self.mode_combo.currentText()

    def set_mode(self, mode: str):
        if mode.lower() in [m.lower() for m in CANONICAL_MODES]:
            # Find the matching mode (case-insensitive)
            for m in CANONICAL_MODES:
                if m.lower() == mode.lower():
                    self.mode_combo.blockSignals(True)
                    self.mode_combo.setCurrentText(m)
                    self._current_mode = m
                    self.mode_combo.blockSignals(False)
                    break

    def get_actions(self) -> List[str]:
        """Retorna las acciones extras seleccionadas (sin el modo)."""
        return [a for a in EXTRA_ACTIONS if a in self._selected_actions]

    def set_actions(self, actions: List[str]):
        """Setea las acciones extras (sin el modo)."""
        self._selected_actions = set(a for a in actions if a in EXTRA_ACTIONS)
        for action, cb in self._checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(action in self._selected_actions)
            cb.blockSignals(False)
        self._update_counter()

    def is_valid(self) -> bool:
        """Máximo 4 extras (modo + 4 = 5 total)"""
        return len(self._selected_actions) <= 4


# ==================== LEGACY: ExtraActionsPanel (wrapper for compatibility) ====================

class ExtraActionsPanel(ModeAndActionsPanel):
    """
    DEPRECATED: Use ModeAndActionsPanel directly.
    This is a compatibility wrapper.
    """
    def __init__(self, selected: List[str] = None, parent=None):
        super().__init__(mode="clima_1", actions=selected, parent=parent)

    def get_extra_actions(self) -> List[str]:
        return self.get_actions()

    def set_extra_actions(self, actions: List[str]):
        self.set_actions(actions)


# ==================== EXTRA BADGES WIDGET ====================

class ExtraBadgesWidget(QWidget):
    """Badges de acciones extra activas."""

    def __init__(self, actions: List[str] = None, parent=None):
        super().__init__(parent)
        self._actions = actions or []
        self._setup_ui()

    def _setup_ui(self):
        # SizePolicy: expandir horizontal, altura mínima
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)
        self._update_badges()

    def _update_badges(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for action in self._actions[:4]:  # Max 4 extras
            cfg = EXTRA_ACTION_CONFIG.get(action, {})
            badge = QLabel(cfg.get("icon", "?"))
            badge.setToolTip(cfg.get("name", action))
            badge.setStyleSheet("""
                background: rgba(52, 152, 219, 0.3);
                color: #3498db;
                padding: 2px 4px;
                border-radius: 3px;
                font-size: 11px;
            """)
            self._layout.addWidget(badge)

        self._layout.addStretch()

    def set_actions(self, actions: List[str]):
        self._actions = [a for a in actions if a in EXTRA_ACTIONS]
        self._update_badges()


# ==================== TIME BLOCK WIDGET ====================

class TimeBlockWidget(QFrame):
    """Widget para un bloque de tiempo con modo + acciones extra."""

    delete_requested = Signal(object)
    changed = Signal()

    def __init__(self, block_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.block_data = block_data
        self._panel_visible = False  # V7.0: Panel unificado visible
        self._is_active = False  # V6.5: Flag para destacar bloque activo
        self._glow_alpha = 0.3  # V9.3: Glow intensity for animation
        self._setup_glow_effect()
        self._setup_ui()

    def _setup_glow_effect(self):
        """V9.3: Setup green glow effect and pulsing animation."""
        # Create drop shadow effect for glow
        self._glow_effect = QGraphicsDropShadowEffect(self)
        self._glow_effect.setBlurRadius(0)
        self._glow_effect.setColor(QColor(39, 174, 96, 0))  # Green, transparent
        self._glow_effect.setOffset(0, 0)
        self.setGraphicsEffect(self._glow_effect)

        # Create pulsing animation (alternates: 0.3 → 1.0 → 0.3 → ...)
        self._glow_animation = QPropertyAnimation(self, b"glowAlpha", self)
        self._glow_animation.setDuration(800)  # 0.8 second per direction
        self._glow_animation.setStartValue(0.3)
        self._glow_animation.setEndValue(1.0)
        self._glow_animation.setEasingCurve(QEasingCurve.InOutSine)
        self._glow_animation.setLoopCount(1)  # Single run, then reverse
        self._glow_animation.finished.connect(self._on_pulse_finished)

    def _get_glow_alpha(self) -> float:
        return self._glow_alpha

    def _set_glow_alpha(self, value: float):
        self._glow_alpha = value
        if self._is_active:
            # Update glow effect with new alpha
            alpha = int(value * 200)  # 0-200 range for visibility
            self._glow_effect.setColor(QColor(39, 174, 96, alpha))
            blur = 15 + int(value * 10)  # 15-25 blur radius
            self._glow_effect.setBlurRadius(blur)

    # Qt Property for animation
    glowAlpha = Property(float, _get_glow_alpha, _set_glow_alpha)

    def _on_pulse_finished(self):
        """V9.3: Reverse animation direction for continuous pulse."""
        if not self._is_active:
            return  # Don't restart if no longer active

        # Swap start/end values to reverse direction
        current_start = self._glow_animation.startValue()
        current_end = self._glow_animation.endValue()
        self._glow_animation.setStartValue(current_end)
        self._glow_animation.setEndValue(current_start)
        self._glow_animation.start()

    def _setup_ui(self):
        self.setFrameShape(QFrame.StyledPanel)

        # SizePolicy: expandir horizontal, ajustar vertical al contenido
        # Esto permite que el bloque crezca cuando se muestra el panel de extras
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Fila 1: Tiempos
        time_row = QHBoxLayout()
        time_row.setSpacing(4)

        self.from_edit = QTimeEdit()
        self.from_edit.setDisplayFormat("HH:mm")
        self.from_edit.setTime(QTime.fromString(self.block_data.get("from", "00:00"), "HH:mm"))
        self.from_edit.timeChanged.connect(self._on_changed)
        self.from_edit.setStyleSheet("background: #1e272e; color: white; border: 1px solid #34495e; border-radius: 3px;")
        self.from_edit.setFixedWidth(60)
        time_row.addWidget(self.from_edit)

        time_row.addWidget(QLabel("→"))

        self.to_edit = QTimeEdit()
        self.to_edit.setDisplayFormat("HH:mm")
        self.to_edit.setTime(QTime.fromString(self.block_data.get("to", "00:00"), "HH:mm"))
        self.to_edit.timeChanged.connect(self._on_changed)
        self.to_edit.setStyleSheet("background: #1e272e; color: white; border: 1px solid #34495e; border-radius: 3px;")
        self.to_edit.setFixedWidth(60)
        time_row.addWidget(self.to_edit)

        time_row.addStretch()

        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #e74c3c;
            }
        """)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        time_row.addWidget(delete_btn)

        layout.addLayout(time_row)

        # Fila 2: Botón configurar + indicador de modo
        config_row = QHBoxLayout()
        config_row.setSpacing(6)

        # Botón configurar (abre panel unificado)
        self.config_btn = QPushButton("⚙ Configurar")
        self.config_btn.setCheckable(True)
        self.config_btn.setStyleSheet("""
            QPushButton {
                background: #2980b9;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:checked {
                background: #3498db;
            }
            QPushButton:hover {
                background: #3498db;
            }
        """)
        self.config_btn.toggled.connect(self._on_config_toggled)
        config_row.addWidget(self.config_btn)

        # Label que muestra el modo actual
        self.mode_label = QLabel()
        self.mode_label.setStyleSheet("""
            QLabel {
                color: #f39c12;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 8px;
                background: rgba(243, 156, 18, 0.15);
                border-radius: 4px;
            }
        """)
        config_row.addWidget(self.mode_label)

        # Badges de extras
        self.extra_badges = ExtraBadgesWidget()
        config_row.addWidget(self.extra_badges)

        config_row.addStretch()

        layout.addLayout(config_row)

        # Panel unificado de MODO + ACCIONES (oculto por defecto)
        initial_mode = self._get_initial_mode()
        initial_extras = self._get_initial_extras()
        self.config_panel = ModeAndActionsPanel(mode=initial_mode, actions=initial_extras)
        self.config_panel.changed.connect(self._on_config_changed)
        self.config_panel.mode_changed.connect(self._on_mode_changed)
        self.config_panel.hide()
        layout.addWidget(self.config_panel)

        # Actualizar label de modo y badges
        self._update_mode_label()
        self.extra_badges.set_actions(initial_extras)

        # Si ya tiene extras, mostrar el panel abierto
        if initial_extras:
            self.config_btn.setChecked(True)
            self._panel_visible = True
            self.config_panel.show()

        # Color inicial
        self._update_color()

    def _get_initial_mode(self) -> str:
        """Obtiene el modo inicial del bloque."""
        # Prioridad 1: campo mode
        if "mode" in self.block_data:
            mode = self.block_data["mode"].lower()
            if mode in CANONICAL_MODES:
                return mode

        # Prioridad 2: derivar de actions[] (legacy)
        if "actions" in self.block_data:
            actions = self.block_data["actions"]
            return self._derive_mode_from_actions(actions)

        return "clima_1"

    def _get_initial_extras(self) -> List[str]:
        """
        V7.0: Obtiene las acciones extras iniciales.

        Lee de:
        1. Campo "actions" (nuevo formato V7.0)
        2. Campo "extra_actions" (formato anterior)
        """
        # Prioridad 1: campo "actions" (V7.0 nuevo formato)
        if "actions" in self.block_data:
            return [a for a in self.block_data["actions"] if a in EXTRA_ACTIONS]

        # Prioridad 2: campo "extra_actions" (formato anterior)
        if "extra_actions" in self.block_data:
            return [a for a in self.block_data["extra_actions"] if a in EXTRA_ACTIONS]

        return []

    def _derive_mode_from_actions(self, actions: List[str]) -> str:
        """Deriva modo desde lista de acciones (para legacy)."""
        actions_lower = [a.lower() for a in actions]
        if "audio_911" in actions_lower:
            return "boliche_desarrollo"
        if "vision_artista" in actions_lower:
            return "artista"
        if "cues_clima" in actions_lower:
            return "clima_1"
        if "system_idle" in actions_lower:
            return "apagado"
        return "boliche_inicio"

    def _on_changed(self):
        self.changed.emit()

    def _on_mode_changed(self, mode: str):
        self._update_mode_label()
        self._update_color()
        self.changed.emit()

    def _on_config_toggled(self, checked: bool):
        self._panel_visible = checked
        self.config_panel.setVisible(checked)

    def _on_config_changed(self):
        extras = self.config_panel.get_actions()
        self.extra_badges.set_actions(extras)
        self._update_mode_label()
        self.changed.emit()

    def _update_mode_label(self):
        """Actualiza el label que muestra el modo actual."""
        mode = self.config_panel.get_mode()
        self.mode_label.setText(f"🎯 {mode}")

    def _update_color(self):
        """
        Actualiza el color del bloque según el modo.

        V7.0: Lee el modo desde config_panel (panel unificado).
        V6.5: Si el bloque está marcado como activo, aplica estilo destacado
        con borde más grueso y fondo más visible.
        """
        mode = self.config_panel.get_mode()
        color = MODE_COLORS.get(mode, "#7f8c8d")

        if self._is_active:
            # V6.5: Estilo ACTIVO - borde grueso, fondo más visible, glow effect
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {color}40;
                    border-radius: 6px;
                    border: 3px solid #27ae60;
                    padding: 4px;
                }}
            """)
        else:
            # Estilo normal
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {color}20;
                    border-radius: 6px;
                    border: 2px solid {color};
                    padding: 4px;
                }}
            """)

    def set_active(self, active: bool):
        """
        V9.3: Marca el bloque como activo/inactivo con glow verde pulsante.

        Args:
            active: True si este bloque es el activo actualmente
        """
        if self._is_active != active:
            self._is_active = active
            self._update_color()

            if active:
                # Start pulsing glow animation
                self._glow_effect.setBlurRadius(15)
                self._glow_effect.setColor(QColor(39, 174, 96, 100))
                self._glow_animation.start()
            else:
                # Stop animation and remove glow
                self._glow_animation.stop()
                self._glow_effect.setBlurRadius(0)
                self._glow_effect.setColor(QColor(39, 174, 96, 0))

    def get_block_id(self) -> str:
        """
        V6.5: Genera ID determinístico para comparar con bloque activo.

        Returns:
            ID en formato "day_from_to_mode" (day puede ser None)
        """
        from_time = self.from_edit.time().toString("HH:mm")
        to_time = self.to_edit.time().toString("HH:mm")
        mode = self.config_panel.get_mode()
        # El día se establece desde DayColumnWidget
        day = getattr(self, '_day_key', 'unknown')
        return f"{day}_{from_time}_{to_time}_{mode}"

    def get_mode(self) -> str:
        """V7.0: Obtiene el modo actual desde el panel unificado."""
        return self.config_panel.get_mode()

    def get_data(self) -> Dict[str, Any]:
        """
        V7.0: Obtiene los datos del bloque para guardar.

        Retorna:
            - from: hora inicio
            - to: hora fin
            - mode: modo canónico
            - actions: lista de extras (si hay)
        """
        mode = self.config_panel.get_mode()
        extras = self.config_panel.get_actions()

        result = {
            "from": self.from_edit.time().toString("HH:mm"),
            "to": self.to_edit.time().toString("HH:mm"),
            "mode": mode,
        }

        # V7.0: Guardar como "actions" (no "extra_actions") para compatibilidad
        if extras:
            result["actions"] = extras

        return result

    def is_valid(self) -> bool:
        # Modo siempre existe, extras max 4
        return self.config_panel.is_valid()

    def get_validation_error(self) -> Optional[str]:
        extras = self.config_panel.get_actions()
        if len(extras) > 4:
            return f"Más de 4 acciones extra ({len(extras)})"
        return None


# ==================== DAY COLUMN WIDGET ====================

class DayColumnWidget(QFrame):
    """Columna para un día de la semana."""

    changed = Signal()

    def __init__(self, day_key: str, day_name: str, blocks: List[Dict], parent=None):
        super().__init__(parent)
        self.day_key = day_key
        self.day_name = day_name
        self.block_widgets: List[TimeBlockWidget] = []
        self._setup_ui(blocks)

    def _setup_ui(self, blocks: List[Dict]):
        self.setFrameShape(QFrame.StyledPanel)

        # SizePolicy: expandir en ambas direcciones para adaptarse al contenido
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.setStyleSheet("""
            QFrame {
                background-color: #1e272e;
                border-radius: 8px;
                border: 1px solid #34495e;
            }
        """)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        header = QLabel(self.day_name)
        header.setFont(QFont("", 11, QFont.Bold))
        header.setStyleSheet("color: #ecf0f1; background: transparent; border: none;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Scroll area para bloques - ADAPTATIVO
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)

        # Contenedor de bloques - sin altura fija
        blocks_container = QWidget()
        blocks_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.blocks_layout = QVBoxLayout(blocks_container)
        self.blocks_layout.setSpacing(6)
        self.blocks_layout.setContentsMargins(0, 0, 0, 0)

        for block in blocks:
            self._add_block(block)

        self.blocks_layout.addStretch()
        scroll.setWidget(blocks_container)
        layout.addWidget(scroll, 1)

        # Botón agregar
        add_btn = QPushButton("+ Agregar bloque")
        add_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2ecc71;
            }
        """)
        add_btn.clicked.connect(self._on_add_block)
        layout.addWidget(add_btn)

    def _add_block(self, block_data: Dict[str, Any]):
        widget = TimeBlockWidget(block_data)
        widget._day_key = self.day_key  # V6.5: Para generar block_id
        widget.delete_requested.connect(self._on_delete_block)
        widget.changed.connect(lambda: self.changed.emit())
        self.block_widgets.append(widget)

        count = self.blocks_layout.count()
        self.blocks_layout.insertWidget(count - 1 if count > 0 else 0, widget)

    def _on_add_block(self):
        new_block = {"from": "20:00", "to": "22:00", "mode": "clima_1"}
        self._add_block(new_block)
        _log(f"Block added to {self.day_key}: mode=clima_1")
        self.changed.emit()

    def _on_delete_block(self, widget: TimeBlockWidget):
        if widget in self.block_widgets:
            self.block_widgets.remove(widget)
            widget.deleteLater()
            _log(f"Block deleted from {self.day_key}")
            self.changed.emit()

    def get_blocks(self) -> List[Dict[str, Any]]:
        return [w.get_data() for w in self.block_widgets]

    def validate(self) -> List[str]:
        errors = []
        for i, widget in enumerate(self.block_widgets):
            error = widget.get_validation_error()
            if error:
                errors.append(f"{self.day_name} bloque {i+1}: {error}")

        # Validar solapamientos
        blocks = self.get_blocks()
        for i, block1 in enumerate(blocks):
            for j, block2 in enumerate(blocks):
                if i >= j:
                    continue
                if self._blocks_overlap(block1, block2):
                    errors.append(f"{self.day_name}: bloques {i+1} y {j+1} se solapan")

        return errors

    def _blocks_overlap(self, block1: Dict, block2: Dict) -> bool:
        from1 = QTime.fromString(block1["from"], "HH:mm")
        to1 = QTime.fromString(block1["to"], "HH:mm")
        from2 = QTime.fromString(block2["from"], "HH:mm")
        to2 = QTime.fromString(block2["to"], "HH:mm")

        if from1 < to1 and from2 < to2:
            return not (to1 <= from2 or to2 <= from1)
        return False

    def highlight_active_block(self, from_time: str, to_time: str, mode: str) -> bool:
        """
        V7.0: Destaca el bloque activo en esta columna.

        Args:
            from_time: Hora inicio del bloque activo (HH:mm)
            to_time: Hora fin del bloque activo (HH:mm)
            mode: Modo del bloque activo

        Returns:
            True si se encontró y destacó el bloque
        """
        found = False
        for widget in self.block_widgets:
            widget_from = widget.from_edit.time().toString("HH:mm")
            widget_to = widget.to_edit.time().toString("HH:mm")
            widget_mode = widget.get_mode()  # V7.0: Usar get_mode() del panel unificado

            # Comparar por tiempos y modo (case-insensitive para modo)
            is_match = (widget_from == from_time and
                       widget_to == to_time and
                       widget_mode.lower() == mode.lower())

            widget.set_active(is_match)
            if is_match:
                found = True

        return found

    def clear_active_highlight(self):
        """V6.5: Quita el highlight de todos los bloques de esta columna."""
        for widget in self.block_widgets:
            widget.set_active(False)


# ==================== CALENDAR SCHEDULE EDITOR ====================

class CalendarScheduleEditor(QWidget):
    """Editor visual del schedule semanal v6.4."""

    schedule_changed = Signal(dict)
    save_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendar = None
        self._day_columns: Dict[str, DayColumnWidget] = {}
        self._has_changes = False
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        # Título
        title_row = QHBoxLayout()
        title = QLabel("EDITOR DE HORARIOS SEMANALES")
        title.setFont(QFont("", 12, QFont.Bold))
        title.setStyleSheet("color: #ecf0f1;")
        title_row.addWidget(title)

        title_row.addStretch()

        # Indicador de cambios
        self.changes_label = QLabel("")
        self.changes_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        title_row.addWidget(self.changes_label)

        main_layout.addLayout(title_row)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        days_container = QWidget()
        days_layout = QHBoxLayout(days_container)
        days_layout.setSpacing(8)
        days_layout.setContentsMargins(0, 0, 0, 0)

        for day_key in DAY_ORDER:
            column = DayColumnWidget(day_key, DAY_NAMES[day_key], [])
            column.changed.connect(self._on_changed)
            self._day_columns[day_key] = column
            days_layout.addWidget(column)

        scroll.setWidget(days_container)
        main_layout.addWidget(scroll)

        # Botones
        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        reload_btn = QPushButton("Recargar")
        reload_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2980b9; }
        """)
        reload_btn.clicked.connect(self._on_reload)
        buttons_row.addWidget(reload_btn)

        self.save_btn = QPushButton("Guardar Cambios")
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2ecc71; }
            QPushButton:disabled { background: #7f8c8d; }
        """)
        self.save_btn.clicked.connect(self._on_save)
        buttons_row.addWidget(self.save_btn)

        main_layout.addLayout(buttons_row)

    def set_calendar_manager(self, calendar_manager) -> None:
        self._calendar = calendar_manager
        self._load_schedule()

    def _load_schedule(self):
        if not self._calendar:
            return

        schedule = self._calendar.get_schedule()
        week = schedule.get("week", {})

        _log(f"Loading schedule: {len(week)} days")

        for day_key, column in list(self._day_columns.items()):
            blocks = week.get(day_key, [])

            parent = column.parent()
            layout = parent.layout() if parent else None

            if layout:
                idx = layout.indexOf(column)
                layout.removeWidget(column)
                column.deleteLater()

                new_column = DayColumnWidget(day_key, DAY_NAMES[day_key], blocks)
                new_column.changed.connect(self._on_changed)
                layout.insertWidget(idx, new_column)
                self._day_columns[day_key] = new_column

        self._has_changes = False
        self._update_changes_indicator()

    def _on_changed(self):
        self._has_changes = True
        self._update_changes_indicator()
        self.schedule_changed.emit(self._get_schedule())

    def _update_changes_indicator(self):
        if self._has_changes:
            self.changes_label.setText("⚠ Cambios sin guardar")
            self.save_btn.setEnabled(True)
        else:
            self.changes_label.setText("")
            self.save_btn.setEnabled(False)

    def update_active_block_highlight(self, snapshot: Optional[Dict[str, Any]] = None):
        """
        V6.5: Actualiza el highlight del bloque activo en toda la semana.

        Args:
            snapshot: Dict del bloque activo (de CalendarManager.get_active_block_snapshot())
                     Si es None, intenta obtenerlo del CalendarManager
        """
        # Limpiar todos los highlights primero
        for column in self._day_columns.values():
            column.clear_active_highlight()

        # Obtener snapshot si no se proporcionó
        if snapshot is None and self._calendar:
            snapshot = self._calendar.get_active_block_snapshot()

        if not snapshot:
            return

        day = snapshot.get("day")
        from_time = snapshot.get("from_time")
        to_time = snapshot.get("to_time")
        mode = snapshot.get("mode")

        if not all([day, from_time, to_time, mode]):
            return

        # Buscar la columna del día
        column = self._day_columns.get(day)
        if column:
            found = column.highlight_active_block(from_time, to_time, mode)
            if found:
                _log(f"Active block highlighted: {day} {from_time}-{to_time} {mode}")

    def _get_schedule(self) -> Dict[str, Any]:
        week = {}
        for day_key, column in self._day_columns.items():
            week[day_key] = column.get_blocks()
        return {"week": week}

    def _validate_schedule(self) -> List[str]:
        errors = []
        for day_key, column in self._day_columns.items():
            errors.extend(column.validate())
        return errors

    def _on_reload(self):
        if self._has_changes:
            reply = QMessageBox.question(
                self, "Descartar cambios",
                "¿Descartar los cambios sin guardar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        _log("Schedule reloaded")
        self._load_schedule()

    def _on_save(self):
        if not self._calendar:
            QMessageBox.warning(self, "Error", "Calendario no conectado")
            return

        errors = self._validate_schedule()
        if errors:
            error_msg = "Errores:\n\n" + "\n".join(f"• {e}" for e in errors)
            QMessageBox.warning(self, "Validación", error_msg)
            return

        schedule = self._get_schedule()

        total_blocks = sum(len(b) for b in schedule["week"].values())
        _log(f"Saving schedule: {total_blocks} blocks")
        for day, blocks in schedule["week"].items():
            for block in blocks:
                extras = block.get("extra_actions", [])
                _log(f"  {day}: {block['from']}-{block['to']} mode={block['mode']} extras={extras}")

        reply = QMessageBox.question(
            self, "Guardar",
            f"¿Guardar {total_blocks} bloques?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        if self._calendar.save_schedule(schedule):
            self._has_changes = False
            self._update_changes_indicator()
            self.save_requested.emit(schedule)
            QMessageBox.information(self, "Guardado", "Horarios guardados")
            _log("Schedule saved")
        else:
            QMessageBox.critical(self, "Error", "Error al guardar")

    def has_unsaved_changes(self) -> bool:
        return self._has_changes
