# ui/calendar_schedule_editor.py
"""
CalendarScheduleEditor v8.1 - Editor visual de horarios semanales.

V8.1 CAMBIOS (UI Polish):
- Padding interno aumentado (10-12px)
- Spacing vertical consistente entre secciones
- Time section separada visualmente con línea sutil
- Mode buttons: altura 28-32px, pill radius real, spacing 6px
- Extra buttons: más pequeños (22-24px), colores apagados, separador
- Ningún elemento toca bordes/glow

V8.0 CAMBIOS:
- ELIMINADO botón "Configurar", dropdown de modo, checkboxes
- NUEVO: Botones PILL para modo (single-select, siempre visibles)
- NUEVO: Botones TOGGLE para extras (multi-select, siempre visibles)
- Todo inline, sin paneles desplegables

MODOS: Botones pill (uno solo activo)
clima_1, clima_2, clima_3, clima_4, teatro, artista,
boliche_inicio, boliche_desarrollo, boliche_fin, apagado

EXTRAS: Botones toggle (múltiples activos)
Haze, DJ Cues, Artista, Tracking, DJ Detect, Clima

SOLO UI - No ejecuta acciones del sistema.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QTimeEdit, QScrollArea, QGridLayout,
    QMessageBox, QSizePolicy, QGraphicsDropShadowEffect
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

# Display names cortos para botones pill
MODE_DISPLAY = {
    "clima_1": "Clima 1",
    "clima_2": "Clima 2",
    "clima_3": "Clima 3",
    "clima_4": "Clima 4",
    "teatro": "Teatro",
    "artista": "Artista",
    "boliche_inicio": "Bol.Ini",
    "boliche_desarrollo": "Bol.Des",
    "boliche_fin": "Bol.Fin",
    "apagado": "Apagado",
}

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

EXTRA_ACTIONS = [
    "vision_haze",
    "vision_dj",
    "vision_artista",
    "tracking_cam",
    "dj_detection",
    "cues_clima",
]

# Display para botones toggle
EXTRA_DISPLAY = {
    "vision_haze": "💨 Haze",
    "vision_dj": "🎧 DJ",
    "vision_artista": "🎤 Artist",
    "tracking_cam": "📹 Track",
    "dj_detection": "👁 Detect",
    "cues_clima": "🌡 Clima",
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


# ==================== FLOW LAYOUT HELPER ====================

class FlowLayout(QVBoxLayout):
    """
    Simple flow layout that wraps widgets into multiple rows.
    Uses multiple QHBoxLayouts internally.
    """

    def __init__(self, parent=None, max_per_row: int = 5):
        super().__init__(parent)
        self._max_per_row = max_per_row
        self._rows: List[QHBoxLayout] = []
        self._widgets: List[QWidget] = []
        self.setSpacing(4)
        self.setContentsMargins(0, 0, 0, 0)

    def addFlowWidget(self, widget: QWidget):
        self._widgets.append(widget)
        self._rebuild()

    def clearWidgets(self):
        for w in self._widgets:
            w.setParent(None)
        self._widgets.clear()
        self._rebuild()

    def _rebuild(self):
        # Clear existing rows
        while self.count():
            item = self.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().setParent(None)

        self._rows.clear()

        # Rebuild rows
        for i, widget in enumerate(self._widgets):
            row_idx = i // self._max_per_row
            if row_idx >= len(self._rows):
                row = QHBoxLayout()
                row.setSpacing(3)
                row.setContentsMargins(0, 0, 0, 0)
                self._rows.append(row)
                self.addLayout(row)

            self._rows[row_idx].addWidget(widget)

        # Add stretch to last row
        if self._rows:
            self._rows[-1].addStretch()


# ==================== TIME BLOCK WIDGET ====================

class TimeBlockWidget(QFrame):
    """
    V8.0: Widget para un bloque de tiempo con botones pill/toggle.

    - MODOS: Botones pill (single-select)
    - EXTRAS: Botones toggle (multi-select)
    - Todo visible inline, sin paneles desplegables
    """

    delete_requested = Signal(object)
    changed = Signal()

    def __init__(self, block_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.block_data = block_data
        self._current_mode = "clima_1"
        self._selected_actions: Set[str] = set()
        self._mode_buttons: Dict[str, QPushButton] = {}
        self._extra_buttons: Dict[str, QPushButton] = {}
        self._is_active = False
        self._glow_alpha = 0.3
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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # V8.1: Padding interno real (10-12px) para que nada toque bordes/glow
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # ===== SECCIÓN 1: Tiempos + Delete =====
        time_row = QHBoxLayout()
        time_row.setSpacing(6)

        self.from_edit = QTimeEdit()
        self.from_edit.setDisplayFormat("HH:mm")
        self.from_edit.setTime(QTime.fromString(self.block_data.get("from", "00:00"), "HH:mm"))
        self.from_edit.timeChanged.connect(self._on_changed)
        self.from_edit.setStyleSheet("""
            QTimeEdit {
                background: #1e272e;
                color: white;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
        """)
        self.from_edit.setFixedWidth(64)
        self.from_edit.setFixedHeight(26)
        time_row.addWidget(self.from_edit)

        arrow = QLabel("→")
        arrow.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        time_row.addWidget(arrow)

        self.to_edit = QTimeEdit()
        self.to_edit.setDisplayFormat("HH:mm")
        self.to_edit.setTime(QTime.fromString(self.block_data.get("to", "00:00"), "HH:mm"))
        self.to_edit.timeChanged.connect(self._on_changed)
        self.to_edit.setStyleSheet("""
            QTimeEdit {
                background: #1e272e;
                color: white;
                border: 1px solid #34495e;
                border-radius: 4px;
                padding: 4px 6px;
                font-size: 11px;
            }
        """)
        self.to_edit.setFixedWidth(64)
        self.to_edit.setFixedHeight(26)
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
                font-size: 11px;
            }
            QPushButton:hover { background: #e74c3c; }
        """)
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self))
        time_row.addWidget(delete_btn)

        layout.addLayout(time_row)

        # V8.1: Separador visual sutil entre horarios y modos
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: #34495e; max-height: 1px; margin: 2px 0;")
        separator.setFixedHeight(1)
        layout.addWidget(separator)

        # ===== SECCIÓN 2: MODOS (botones pill protagonistas) =====
        modes_frame = QFrame()
        modes_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        modes_layout = QGridLayout(modes_frame)
        modes_layout.setContentsMargins(0, 4, 0, 4)
        modes_layout.setSpacing(6)  # V8.1: Spacing 6px entre botones

        initial_mode = self._get_initial_mode()
        self._current_mode = initial_mode

        for i, mode in enumerate(CANONICAL_MODES):
            btn = QPushButton(MODE_DISPLAY.get(mode, mode))
            btn.setCheckable(True)
            btn.setChecked(mode == initial_mode)
            btn.setProperty("mode_key", mode)
            color = MODE_COLORS.get(mode, "#7f8c8d")
            # V8.1: Altura 28-32px, padding 10-14px, pill radius real
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #2c3e50;
                    color: #95a5a6;
                    border: 1px solid #3d5266;
                    border-radius: 14px;
                    padding: 4px 12px;
                    font-size: 10px;
                    min-width: 44px;
                    min-height: 28px;
                }}
                QPushButton:checked {{
                    background: {color};
                    color: white;
                    border: none;
                    font-weight: bold;
                }}
                QPushButton:hover:!checked {{
                    background: #34495e;
                    border: 1px solid {color};
                }}
            """)
            btn.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(m))
            self._mode_buttons[mode] = btn
            row, col = i // 5, i % 5
            modes_layout.addWidget(btn, row, col)

        layout.addWidget(modes_frame)

        # ===== SECCIÓN 3: EXTRAS (botones toggle secundarios) =====
        # V8.1: Separador visual + label discreto
        extras_separator = QFrame()
        extras_separator.setFrameShape(QFrame.HLine)
        extras_separator.setStyleSheet("background: #2c3e50; max-height: 1px;")
        extras_separator.setFixedHeight(1)
        layout.addWidget(extras_separator)

        extras_label = QLabel("EXTRAS")
        extras_label.setStyleSheet("color: #5d6d7e; font-size: 8px; font-weight: bold; margin: 0; padding: 0;")
        extras_label.setAlignment(Qt.AlignLeft)
        layout.addWidget(extras_label)

        extras_frame = QFrame()
        extras_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        extras_layout = QHBoxLayout(extras_frame)
        extras_layout.setContentsMargins(0, 2, 0, 0)
        extras_layout.setSpacing(4)  # V8.1: Spacing 4px

        initial_extras = self._get_initial_extras()
        self._selected_actions = set(initial_extras)

        for action in EXTRA_ACTIONS:
            btn = QPushButton(EXTRA_DISPLAY.get(action, action))
            btn.setCheckable(True)
            btn.setChecked(action in initial_extras)
            btn.setProperty("action_key", action)
            # V8.1: Más pequeños (22-24px), colores apagados
            btn.setStyleSheet("""
                QPushButton {
                    background: #283747;
                    color: #6c7a89;
                    border: 1px solid #2c3e50;
                    border-radius: 11px;
                    padding: 2px 8px;
                    font-size: 9px;
                    min-height: 22px;
                }
                QPushButton:checked {
                    background: #2980b9;
                    color: #ecf0f1;
                    border: none;
                }
                QPushButton:hover:!checked {
                    background: #34495e;
                    color: #95a5a6;
                }
            """)
            btn.clicked.connect(lambda checked, a=action: self._on_extra_clicked(a, checked))
            self._extra_buttons[action] = btn
            extras_layout.addWidget(btn)

        extras_layout.addStretch()
        layout.addWidget(extras_frame)

        # Color inicial
        self._update_color()

    def _get_initial_mode(self) -> str:
        if "mode" in self.block_data:
            mode = self.block_data["mode"].lower()
            if mode in CANONICAL_MODES:
                return mode
        return "clima_1"

    def _get_initial_extras(self) -> List[str]:
        # V8.0: Lee de "actions" o "extra_actions" (legacy)
        if "actions" in self.block_data:
            return [a for a in self.block_data["actions"] if a in EXTRA_ACTIONS]
        if "extra_actions" in self.block_data:
            return [a for a in self.block_data["extra_actions"] if a in EXTRA_ACTIONS]
        return []

    def _on_changed(self):
        self.changed.emit()

    def _on_mode_clicked(self, mode: str):
        # Single-select: deselect all others
        for m, btn in self._mode_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(m == mode)
            btn.blockSignals(False)
        self._current_mode = mode
        self._update_color()
        self.changed.emit()

    def _on_extra_clicked(self, action: str, checked: bool):
        if checked:
            self._selected_actions.add(action)
        else:
            self._selected_actions.discard(action)
        self.changed.emit()

    def _update_color(self):
        """V8.1: Actualiza el color del bloque según el modo."""
        color = MODE_COLORS.get(self._current_mode, "#7f8c8d")

        # V8.1: Sin padding en CSS (se usa layout margins)
        # Border-radius 8px para mejor apariencia
        if self._is_active:
            self.setStyleSheet(f"""
                TimeBlockWidget {{
                    background-color: {color}40;
                    border-radius: 8px;
                    border: 3px solid #27ae60;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                TimeBlockWidget {{
                    background-color: {color}18;
                    border-radius: 8px;
                    border: 2px solid {color}80;
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
        """V8.0: ID determinístico para comparar con bloque activo."""
        from_time = self.from_edit.time().toString("HH:mm")
        to_time = self.to_edit.time().toString("HH:mm")
        day = getattr(self, '_day_key', 'unknown')
        return f"{day}_{from_time}_{to_time}_{self._current_mode}"

    def get_mode(self) -> str:
        """V8.0: Obtiene el modo actual."""
        return self._current_mode

    def get_data(self) -> Dict[str, Any]:
        """
        V8.0: Obtiene los datos del bloque para guardar.

        Retorna:
            - from: hora inicio
            - to: hora fin
            - mode: modo canónico
            - actions: lista de extras (si hay)
        """
        result = {
            "from": self.from_edit.time().toString("HH:mm"),
            "to": self.to_edit.time().toString("HH:mm"),
            "mode": self._current_mode,
        }

        # V8.0: Guardar extras como "actions"
        if self._selected_actions:
            result["actions"] = list(self._selected_actions)

        return result

    def is_valid(self) -> bool:
        return len(self._selected_actions) <= 4

    def get_validation_error(self) -> Optional[str]:
        if len(self._selected_actions) > 4:
            return f"Más de 4 acciones extra ({len(self._selected_actions)})"
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
