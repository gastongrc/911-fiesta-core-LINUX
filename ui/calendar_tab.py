# ui/calendar_tab.py
"""
CalendarTab v6.4 - Solapa completa del Calendario Inteligente

Centro de gobierno contextual del sistema 911 Fiesta.
GOBERNADOR VISUAL - Decide permisos y muestra estado en tiempo real.

MODOS CANONICOS:
clima_1, clima_2, clima_3, clima_4, teatro, artista,
boliche_inicio, boliche_desarrollo, boliche_fin, apagado

Funcionalidades:
- Header con reloj, modo actual, fuente
- Timeline con progreso y proximo cambio
- Panel de permisos (cam, audio, tracking, dj, energy)
- 3 TABS: Estado, Horarios, Control
- Controles GO con delay (+5, +10, +15 min)
- Override temporal
- Alertas a 5 minutos con reconfirmacion
- Estados deshabilitados (disable_states)

IMPORTANTE: Esta UI es PASIVA
- NO ejecuta cues
- NO activa modulos directamente
- NO modifica el show
- El SystemBridge aplica los cambios
"""

from datetime import datetime
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QProgressBar, QGridLayout, QSizePolicy, QSpacerItem,
    QPushButton, QComboBox, QSpinBox, QMessageBox,
    QScrollArea, QTabWidget, QGroupBox, QButtonGroup
)
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont, QColor

# Import del editor de horarios
try:
    from .calendar_schedule_editor import CalendarScheduleEditor
    SCHEDULE_EDITOR_AVAILABLE = True
except ImportError:
    SCHEDULE_EDITOR_AVAILABLE = False
    print("[CalendarTab] Schedule editor no disponible")


# ==================== CONSTANTES DE DISEÑO ====================

# Colores por modo canonico
MODE_COLORS = {
    # Climas
    "clima_1": "#1abc9c",
    "clima_2": "#16a085",
    "clima_3": "#2ecc71",
    "clima_4": "#27ae60",
    # Teatro/Artista
    "teatro": "#3498db",
    "artista": "#9b59b6",
    # Boliche
    "boliche_inicio": "#f39c12",
    "boliche_desarrollo": "#e67e22",
    "boliche_fin": "#e74c3c",
    # Apagado
    "apagado": "#7f8c8d",
}

# Modos canonicos
CANONICAL_MODES = [
    "clima_1", "clima_2", "clima_3", "clima_4",
    "teatro", "artista",
    "boliche_inicio", "boliche_desarrollo", "boliche_fin",
    "apagado"
]

DAY_NAMES = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]

# Config de permisos v6.4 (legacy)
PERMISSION_CONFIG = {
    "cam": {"icon": "CAM", "name": "Camaras"},
    "audio": {"icon": "AUD", "name": "Audio"},
    "tracking": {"icon": "TRK", "name": "Tracking"},
    "dj": {"icon": "DJ", "name": "Modo DJ"},
}

# Módulos canónicos v6.4 - Grid de acciones activas
CANONICAL_MODULE_CONFIG = {
    "audio_engine": {"icon": "🔊", "name": "Audio 911", "row": 0, "col": 0},
    "vision_haze": {"icon": "💨", "name": "Haze", "row": 0, "col": 1},
    "vision_dj": {"icon": "🎧", "name": "DJ Cues", "row": 0, "col": 2},
    "vision_artista": {"icon": "🎤", "name": "Artista", "row": 0, "col": 3},
    "tracking_cam": {"icon": "📹", "name": "Tracking", "row": 1, "col": 0},
    "dj_detection": {"icon": "👁", "name": "DJ Detect", "row": 1, "col": 1},
    "cues_clima": {"icon": "🌡", "name": "Clima", "row": 1, "col": 2},
    "system_idle": {"icon": "💤", "name": "Idle", "row": 1, "col": 3},
}


# ==================== WIDGETS AUXILIARES ====================

class PermissionIndicator(QWidget):
    """Indicador compacto de permiso"""

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.config = PERMISSION_CONFIG.get(key, {"icon": "?", "name": key})
        self._enabled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.icon_label = QLabel(self.config["icon"])
        self.icon_label.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(self.icon_label)

        info = QVBoxLayout()
        info.setSpacing(0)

        self.name_label = QLabel(self.config["name"])
        self.name_label.setFont(QFont("", 9, QFont.Bold))
        info.addWidget(self.name_label)

        self.status_label = QLabel("OFF")
        self.status_label.setFont(QFont("", 8))
        info.addWidget(self.status_label)

        layout.addLayout(info)
        layout.addStretch()

        self.setMinimumWidth(90)
        self._update_style()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._update_style()

    def _update_style(self):
        if self._enabled:
            self.status_label.setText("ON")
            self.setStyleSheet("""
                QWidget { background: rgba(46,204,113,0.2); border: 1px solid #2ecc71; border-radius: 4px; }
            """)
            self.icon_label.setStyleSheet("color: #2ecc71;")
            self.name_label.setStyleSheet("color: #2ecc71;")
            self.status_label.setStyleSheet("color: #27ae60;")
        else:
            self.status_label.setText("OFF")
            self.setStyleSheet("""
                QWidget { background: rgba(127,140,141,0.1); border: 1px solid #34495e; border-radius: 4px; }
            """)
            self.icon_label.setStyleSheet("color: #7f8c8d;")
            self.name_label.setStyleSheet("color: #7f8c8d;")
            self.status_label.setStyleSheet("color: #95a5a6;")


class AlertBanner(QFrame):
    """Banner de alerta visual con reconfirmacion"""

    confirmed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        self.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f39c12, stop:1 #e67e22);
                border-radius: 6px;
                border: none;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.icon = QLabel("!")
        self.icon.setFont(QFont("", 16, QFont.Bold))
        self.icon.setStyleSheet("color: white;")
        layout.addWidget(self.icon)

        self.message = QLabel("")
        self.message.setFont(QFont("", 11, QFont.Bold))
        self.message.setStyleSheet("color: white;")
        layout.addWidget(self.message, 1)

        self.countdown = QLabel("")
        self.countdown.setFont(QFont("", 12, QFont.Bold))
        self.countdown.setStyleSheet("color: white;")
        layout.addWidget(self.countdown)

        self.confirm_btn = QPushButton("OK")
        self.confirm_btn.setStyleSheet("""
            QPushButton { background: white; color: #e67e22; border: none; border-radius: 4px; padding: 4px 12px; font-weight: bold; }
            QPushButton:hover { background: #ecf0f1; }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self.confirm_btn)

    def _on_confirm(self):
        self.confirmed.emit()
        self.hide()

    def show_alert(self, mode: str, seconds: int):
        mins = seconds // 60
        secs = seconds % 60
        self.message.setText(f"Cambio a {mode} en")
        self.countdown.setText(f"{mins}:{secs:02d}")
        self.show()

    def update_countdown(self, seconds: int):
        mins = seconds // 60
        secs = seconds % 60
        self.countdown.setText(f"{mins}:{secs:02d}")

    def hide_alert(self):
        self.hide()


class DisabledStatesWidget(QWidget):
    """Widget que muestra estados deshabilitados"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.label = QLabel("Estados bloqueados:")
        self.label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        layout.addWidget(self.label)

        self.states_label = QLabel("Ninguno")
        self.states_label.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
        layout.addWidget(self.states_label)

        layout.addStretch()

    def set_disabled_states(self, states: list):
        self._states = states
        if not states:
            self.states_label.setText("Ninguno")
            self.states_label.setStyleSheet("color: #2ecc71; font-size: 10px;")
        elif "ALL" in states:
            self.states_label.setText("TODOS")
            self.states_label.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold;")
        else:
            self.states_label.setText(", ".join(states))
            self.states_label.setStyleSheet("color: #f39c12; font-size: 10px; font-weight: bold;")


class ModuleIndicator(QWidget):
    """Indicador compacto de módulo canónico v6.4"""

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.config = CANONICAL_MODULE_CONFIG.get(key, {"icon": "?", "name": key})
        self._enabled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel(self.config["icon"])
        self.icon_label.setFont(QFont("", 16))
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        self.name_label = QLabel(self.config["name"])
        self.name_label.setFont(QFont("", 8, QFont.Bold))
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)

        self.status_label = QLabel("OFF")
        self.status_label.setFont(QFont("", 7, QFont.Bold))
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        self.setMinimumSize(70, 60)
        self._update_style()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._update_style()

    def _update_style(self):
        if self._enabled:
            self.status_label.setText("ON")
            self.setStyleSheet("""
                QWidget { background: rgba(46,204,113,0.25); border: 2px solid #2ecc71; border-radius: 6px; }
            """)
            self.name_label.setStyleSheet("color: #2ecc71;")
            self.status_label.setStyleSheet("color: #27ae60;")
        else:
            self.status_label.setText("OFF")
            self.setStyleSheet("""
                QWidget { background: rgba(127,140,141,0.1); border: 1px solid #34495e; border-radius: 6px; }
            """)
            self.name_label.setStyleSheet("color: #7f8c8d;")
            self.status_label.setStyleSheet("color: #95a5a6;")


class ActionsPanel(QFrame):
    """Panel de acciones activas v6.4 - Grid de módulos canónicos"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._modules = {}
        self._current_mode = "apagado"
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Título
        title_row = QHBoxLayout()
        title = QLabel("ACCIONES ACTIVAS")
        title.setFont(QFont("", 10, QFont.Bold))
        title.setStyleSheet("color: #ecf0f1;")
        title_row.addWidget(title)
        title_row.addStretch()

        self.mode_badge = QLabel("apagado")
        self.mode_badge.setFont(QFont("", 9, QFont.Bold))
        self.mode_badge.setStyleSheet("color: #7f8c8d; background: rgba(127,140,141,0.2); padding: 2px 8px; border-radius: 3px;")
        title_row.addWidget(self.mode_badge)

        layout.addLayout(title_row)

        # Grid de módulos 4x2
        grid = QGridLayout()
        grid.setSpacing(8)

        self.module_indicators = {}
        for key, config in CANONICAL_MODULE_CONFIG.items():
            indicator = ModuleIndicator(key)
            self.module_indicators[key] = indicator
            grid.addWidget(indicator, config["row"], config["col"])

        layout.addLayout(grid)

        # Explainer text
        self.explainer = QLabel("")
        self.explainer.setWordWrap(True)
        self.explainer.setStyleSheet("color: #95a5a6; font-size: 10px; margin-top: 6px; padding: 6px; background: rgba(52,73,94,0.3); border-radius: 4px;")
        self.explainer.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.explainer)

    def update_modules(self, modules: Dict[str, bool], mode: str):
        """Actualiza el estado de todos los módulos."""
        self._modules = modules
        self._current_mode = mode

        # Actualizar indicadores
        for key, indicator in self.module_indicators.items():
            indicator.set_enabled(modules.get(key, False))

        # Actualizar badge de modo
        color = MODE_COLORS.get(mode, "#7f8c8d")
        self.mode_badge.setText(mode)
        self.mode_badge.setStyleSheet(f"color: {color}; background: rgba(127,140,141,0.2); padding: 2px 8px; border-radius: 3px;")

        # Generar texto explicativo
        self._update_explainer(modules, mode)

    def _update_explainer(self, modules: Dict[str, bool], mode: str):
        """Genera el texto explicativo contextual."""
        active = [k for k, v in modules.items() if v and k != "system_idle"]
        idle = modules.get("system_idle", False)

        if idle:
            text = f"Sistema en standby. El bloque '{mode}' mantiene todos los módulos desactivados."
        elif not active:
            text = f"El bloque '{mode}' no tiene módulos activos. El sistema está esperando."
        elif "audio_engine" in active:
            others = [k for k in active if k != "audio_engine"]
            if others:
                others_str = ", ".join(CANONICAL_MODULE_CONFIG.get(k, {}).get("name", k) for k in others)
                text = f"Audio 911 habilitado. Estados musicales activos. También: {others_str}."
            else:
                text = f"Audio 911 habilitado. Todos los estados musicales están activos."
        else:
            active_str = ", ".join(CANONICAL_MODULE_CONFIG.get(k, {}).get("name", k) for k in active)
            text = f"Módulos activos: {active_str}. Audio deshabilitado por calendario."

        self.explainer.setText(text)


# ==================== CALENDARIO TAB PRINCIPAL ====================

class CalendarTab(QWidget):
    """
    Solapa completa del Calendario Inteligente v6.4.

    GOBERNADOR VISUAL
    - Decide y muestra estados en tiempo real
    - Aplica permisos vía SystemBridge
    - 3 TABS: Estado, Horarios, Control
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._calendar = None
        self._last_mode = None  # V9.2: Track mode for highlight updates
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # ===== ALERTA BANNER =====
        self.alert_banner = AlertBanner()
        self.alert_banner.confirmed.connect(self._on_alert_confirmed)
        main_layout.addWidget(self.alert_banner)

        # ===== HEADER =====
        self._create_header(main_layout)

        # ===== TABS: Estado / Horarios / Control =====
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #34495e; border-radius: 6px; background: #1a1a2e; }
            QTabBar::tab { background: #2c3e50; color: #bdc3c7; padding: 8px 16px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #1a1a2e; color: #ecf0f1; }
        """)

        # Tab 1: Estado
        state_tab = QWidget()
        state_layout = QVBoxLayout(state_tab)
        state_layout.setContentsMargins(12, 12, 12, 12)
        state_layout.setSpacing(12)

        self._create_timeline(state_layout)
        self._create_actions_panel(state_layout)
        self._create_permissions(state_layout)
        self._create_status(state_layout)
        state_layout.addStretch()

        self.tabs.addTab(state_tab, "Estado")

        # Tab 2: Horarios
        if SCHEDULE_EDITOR_AVAILABLE:
            self.schedule_editor = CalendarScheduleEditor()
            self.tabs.addTab(self.schedule_editor, "Horarios")
        else:
            placeholder = QLabel("Editor de horarios no disponible")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("color: #7f8c8d;")
            self.tabs.addTab(placeholder, "Horarios")
            self.schedule_editor = None

        # Tab 3: Control
        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setContentsMargins(12, 12, 12, 12)
        control_layout.setSpacing(12)

        self._create_controls(control_layout)
        control_layout.addStretch()

        self.tabs.addTab(control_tab, "Control")

        main_layout.addWidget(self.tabs)

    def _create_header(self, parent_layout):
        """Header con reloj, modo y fuente"""
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2c3e50, stop:1 #1a252f);
                border-radius: 10px;
                border: 1px solid #34495e;
            }
        """)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Fila 1: Dia y Hora
        row1 = QHBoxLayout()

        self.day_label = QLabel("---")
        self.day_label.setFont(QFont("", 12, QFont.Bold))
        self.day_label.setStyleSheet("color: #ecf0f1;")
        row1.addWidget(self.day_label)

        self.time_label = QLabel("--:--:--")
        self.time_label.setFont(QFont("", 28, QFont.Bold))
        self.time_label.setStyleSheet("color: #ecf0f1;")
        self.time_label.setAlignment(Qt.AlignRight)
        row1.addWidget(self.time_label)

        layout.addLayout(row1)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: #34495e;")
        sep.setMaximumHeight(1)
        layout.addWidget(sep)

        # Fila 2: Modo y fuente
        row2 = QHBoxLayout()

        lbl = QLabel("CALENDARIO")
        lbl.setFont(QFont("", 10))
        lbl.setStyleSheet("color: #7f8c8d;")
        row2.addWidget(lbl)

        row2.addWidget(QLabel(" "))

        self.mode_label = QLabel("apagado")
        self.mode_label.setFont(QFont("", 16, QFont.Bold))
        self.mode_label.setStyleSheet(f"color: {MODE_COLORS['apagado']};")
        row2.addWidget(self.mode_label)

        row2.addStretch()

        # Override badge
        self.override_badge = QLabel("OVERRIDE")
        self.override_badge.setFont(QFont("", 9, QFont.Bold))
        self.override_badge.setStyleSheet("color: #e74c3c; background: rgba(231,76,60,0.2); padding: 2px 6px; border-radius: 3px;")
        self.override_badge.hide()
        row2.addWidget(self.override_badge)

        # Pending GO badge
        self.pending_go_badge = QLabel("GO PENDIENTE")
        self.pending_go_badge.setFont(QFont("", 9, QFont.Bold))
        self.pending_go_badge.setStyleSheet("color: #3498db; background: rgba(52,152,219,0.2); padding: 2px 6px; border-radius: 3px;")
        self.pending_go_badge.hide()
        row2.addWidget(self.pending_go_badge)

        self.source_label = QLabel("Fuente: ---")
        self.source_label.setFont(QFont("", 9))
        self.source_label.setStyleSheet("color: #95a5a6;")
        row2.addWidget(self.source_label)

        layout.addLayout(row2)

        parent_layout.addWidget(header)

    def _create_timeline(self, parent_layout):
        """Timeline con progreso"""
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Titulo
        row = QHBoxLayout()
        row.addWidget(QLabel("TIMELINE"))
        row.addStretch()
        self.timeline_status = QLabel("ACTIVO")
        self.timeline_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        row.addWidget(self.timeline_status)
        layout.addLayout(row)

        # Barra
        self.timeline_bar = QProgressBar()
        self.timeline_bar.setRange(0, 100)
        self.timeline_bar.setValue(0)
        self.timeline_bar.setTextVisible(False)
        self.timeline_bar.setMinimumHeight(16)
        self.timeline_bar.setStyleSheet("""
            QProgressBar { background: #2c3e50; border-radius: 6px; }
            QProgressBar::chunk { background: #3498db; border-radius: 6px; }
        """)
        layout.addWidget(self.timeline_bar)

        # Info
        info_row = QHBoxLayout()
        self.elapsed_label = QLabel("Transcurrido: ---")
        self.elapsed_label.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        info_row.addWidget(self.elapsed_label)
        info_row.addStretch()
        self.progress_pct = QLabel("0%")
        self.progress_pct.setStyleSheet("color: #3498db; font-weight: bold;")
        info_row.addWidget(self.progress_pct)
        layout.addLayout(info_row)

        # Proximo
        self.next_label = QLabel("Proximo: ---")
        self.next_label.setAlignment(Qt.AlignCenter)
        self.next_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        layout.addWidget(self.next_label)

        parent_layout.addWidget(frame)

    def _create_actions_panel(self, parent_layout):
        """Panel de acciones activas v6.4 - Grid de módulos canónicos"""
        self.actions_panel = ActionsPanel()
        parent_layout.addWidget(self.actions_panel)

    def _create_controls(self, parent_layout):
        """Controles GO y Override — with AUTO/MANUAL selector"""
        # === CONTROL MODE SELECTOR ===
        mode_selector_frame = QFrame()
        mode_selector_frame.setStyleSheet("""
            QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }
        """)
        mode_selector_layout = QVBoxLayout(mode_selector_frame)
        mode_selector_layout.setContentsMargins(12, 10, 12, 10)
        mode_selector_layout.setSpacing(8)

        mode_selector_layout.addWidget(QLabel("MODO OPERATIVO"))

        cm_row = QHBoxLayout()
        cm_row.setSpacing(8)

        self._ctrl_auto_btn = QPushButton("AUTO")
        self._ctrl_auto_btn.setCheckable(True)
        self._ctrl_auto_btn.setChecked(True)
        self._ctrl_auto_btn.setFixedHeight(36)
        self._ctrl_auto_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._ctrl_auto_btn.clicked.connect(lambda: self._on_set_control_mode("AUTO"))
        cm_row.addWidget(self._ctrl_auto_btn)

        self._ctrl_manual_btn = QPushButton("MANUAL")
        self._ctrl_manual_btn.setCheckable(True)
        self._ctrl_manual_btn.setChecked(False)
        self._ctrl_manual_btn.setFixedHeight(36)
        self._ctrl_manual_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._ctrl_manual_btn.clicked.connect(lambda: self._on_set_control_mode("MANUAL"))
        cm_row.addWidget(self._ctrl_manual_btn)

        mode_selector_layout.addLayout(cm_row)
        parent_layout.addWidget(mode_selector_frame)

        self._apply_control_mode_btn_styles("AUTO")

        # === AUTO SECTIONS (hidden in MANUAL) ===
        self._auto_sections = []

        # === MANUAL PANEL (hidden in AUTO) ===
        self._manual_panel = QFrame()
        self._manual_panel.setStyleSheet("""
            QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }
        """)
        mp_layout = QVBoxLayout(self._manual_panel)
        mp_layout.setContentsMargins(12, 10, 12, 10)
        mp_layout.setSpacing(10)

        mp_layout.addWidget(QLabel("CONTROL MANUAL"))

        # --- CLIMA group (exclusive) ---
        clima_label = QLabel("CLIMA")
        clima_label.setStyleSheet("color: #95a5a6; font-size: 10px; font-weight: bold;")
        mp_layout.addWidget(clima_label)

        clima_row = QHBoxLayout()
        clima_row.setSpacing(6)
        self._manual_clima_btns = {}
        for clima in ["clima_1", "clima_2", "clima_3", "clima_4"]:
            btn = QPushButton(clima.replace("clima_", "Clima "))
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            color = MODE_COLORS.get(clima, "#7f8c8d")
            btn.setStyleSheet(f"""
                QPushButton {{ background: #2c3e50; color: #95a5a6; border: 1px solid #3d5266; border-radius: 14px; padding: 2px 8px; font-size: 11px; }}
                QPushButton:checked {{ background: {color}; color: white; border: none; font-weight: bold; }}
                QPushButton:hover:!checked {{ background: #34495e; border: 1px solid {color}; }}
            """)
            btn.clicked.connect(lambda checked, c=clima: self._on_manual_clima(c))
            clima_row.addWidget(btn)
            self._manual_clima_btns[clima] = btn
        mp_layout.addLayout(clima_row)

        # --- MODO group (exclusive) ---
        modo_label = QLabel("MODO")
        modo_label.setStyleSheet("color: #95a5a6; font-size: 10px; font-weight: bold;")
        mp_layout.addWidget(modo_label)

        modo_row = QHBoxLayout()
        modo_row.setSpacing(6)
        self._manual_modo_btns = {}
        modo_items = [
            ("boliche_inicio", "BoLIni"),
            ("boliche_desarrollo", "BoLDes"),
            ("boliche_fin", "BoLFin"),
            ("apagado", "Apagado"),
        ]
        for mode_key, display in modo_items:
            btn = QPushButton(display)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            color = MODE_COLORS.get(mode_key, "#7f8c8d")
            btn.setStyleSheet(f"""
                QPushButton {{ background: #2c3e50; color: #95a5a6; border: 1px solid #3d5266; border-radius: 14px; padding: 2px 8px; font-size: 11px; }}
                QPushButton:checked {{ background: {color}; color: white; border: none; font-weight: bold; }}
                QPushButton:hover:!checked {{ background: #34495e; border: 1px solid {color}; }}
            """)
            btn.clicked.connect(lambda checked, m=mode_key: self._on_manual_modo(m))
            modo_row.addWidget(btn)
            self._manual_modo_btns[mode_key] = btn
        mp_layout.addLayout(modo_row)

        # --- EXTRAS group (multi-select toggles) ---
        extras_label = QLabel("EXTRAS")
        extras_label.setStyleSheet("color: #95a5a6; font-size: 10px; font-weight: bold;")
        mp_layout.addWidget(extras_label)

        extras_row = QHBoxLayout()
        extras_row.setSpacing(6)
        self._manual_extra_btns = {}
        for action, display in [("vision_haze", "Haze"), ("vision_dj", "DJ"), ("vision_artista", "Artista")]:
            btn = QPushButton(display)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet("""
                QPushButton { background: #283747; color: #6c7a89; border: 1px solid #2c3e50; border-radius: 14px; padding: 2px 8px; font-size: 11px; }
                QPushButton:checked { background: #2980b9; color: #ecf0f1; border: none; font-weight: bold; }
                QPushButton:hover:!checked { background: #34495e; color: #95a5a6; }
            """)
            extras_row.addWidget(btn)
            self._manual_extra_btns[action] = btn
        mp_layout.addLayout(extras_row)

        # --- APLICAR button ---
        self._manual_apply_btn = QPushButton("APLICAR")
        self._manual_apply_btn.setFixedHeight(40)
        self._manual_apply_btn.setStyleSheet("""
            QPushButton { background: #27ae60; color: white; border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background: #2ecc71; }
        """)
        self._manual_apply_btn.clicked.connect(self._on_manual_apply)
        mp_layout.addWidget(self._manual_apply_btn)

        parent_layout.addWidget(self._manual_panel)
        self._manual_panel.hide()

        # Selected manual state
        self._manual_selected_clima = None
        self._manual_selected_modo = None

        # === GO SECTION ===
        go_frame = QFrame()
        go_frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        go_layout = QVBoxLayout(go_frame)
        go_layout.setContentsMargins(12, 10, 12, 10)
        go_layout.setSpacing(8)

        go_layout.addWidget(QLabel("GO - Cambiar Modo"))

        # Selector de modo
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo:"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(CANONICAL_MODES)
        self.mode_combo.setStyleSheet("background: #2c3e50; color: white; border: 1px solid #34495e; border-radius: 4px; padding: 4px;")
        mode_row.addWidget(self.mode_combo, 1)
        go_layout.addLayout(mode_row)

        # Botones GO con delay
        go_btns_row = QHBoxLayout()

        self.go_now_btn = QPushButton("GO Ahora")
        self.go_now_btn.setStyleSheet("""
            QPushButton { background: #27ae60; color: white; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background: #2ecc71; }
        """)
        self.go_now_btn.clicked.connect(lambda: self._on_go(0))
        go_btns_row.addWidget(self.go_now_btn)

        self.go_5_btn = QPushButton("+5 min")
        self.go_5_btn.setStyleSheet("""
            QPushButton { background: #3498db; color: white; border: none; border-radius: 4px; padding: 8px 12px; }
            QPushButton:hover { background: #2980b9; }
        """)
        self.go_5_btn.clicked.connect(lambda: self._on_go(5))
        go_btns_row.addWidget(self.go_5_btn)

        self.go_10_btn = QPushButton("+10 min")
        self.go_10_btn.setStyleSheet("""
            QPushButton { background: #3498db; color: white; border: none; border-radius: 4px; padding: 8px 12px; }
            QPushButton:hover { background: #2980b9; }
        """)
        self.go_10_btn.clicked.connect(lambda: self._on_go(10))
        go_btns_row.addWidget(self.go_10_btn)

        self.go_15_btn = QPushButton("+15 min")
        self.go_15_btn.setStyleSheet("""
            QPushButton { background: #3498db; color: white; border: none; border-radius: 4px; padding: 8px 12px; }
            QPushButton:hover { background: #2980b9; }
        """)
        self.go_15_btn.clicked.connect(lambda: self._on_go(15))
        go_btns_row.addWidget(self.go_15_btn)

        go_layout.addLayout(go_btns_row)

        # Cancelar GO pendiente
        self.cancel_go_btn = QPushButton("Cancelar GO Pendiente")
        self.cancel_go_btn.setStyleSheet("""
            QPushButton { background: #c0392b; color: white; border: none; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.cancel_go_btn.clicked.connect(self._on_cancel_go)
        self.cancel_go_btn.hide()
        go_layout.addWidget(self.cancel_go_btn)

        parent_layout.addWidget(go_frame)
        self._auto_sections.append(go_frame)

        # === OVERRIDE SECTION ===
        override_frame = QFrame()
        override_frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        override_layout = QVBoxLayout(override_frame)
        override_layout.setContentsMargins(12, 10, 12, 10)
        override_layout.setSpacing(8)

        override_layout.addWidget(QLabel("OVERRIDE - Forzar Modo Temporal"))

        override_row = QHBoxLayout()
        override_row.addWidget(QLabel("Duracion:"))

        self.override_spin = QSpinBox()
        self.override_spin.setRange(5, 120)
        self.override_spin.setValue(30)
        self.override_spin.setSuffix(" min")
        self.override_spin.setStyleSheet("background: #2c3e50; color: white; border: 1px solid #34495e; border-radius: 4px;")
        override_row.addWidget(self.override_spin)

        self.override_btn = QPushButton("Activar Override")
        self.override_btn.setStyleSheet("""
            QPushButton { background: #e67e22; color: white; border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background: #f39c12; }
        """)
        self.override_btn.clicked.connect(self._on_override)
        override_row.addWidget(self.override_btn)

        self.clear_override_btn = QPushButton("Limpiar")
        self.clear_override_btn.setStyleSheet("""
            QPushButton { background: #c0392b; color: white; border: none; border-radius: 4px; padding: 8px 12px; }
            QPushButton:hover { background: #e74c3c; }
        """)
        self.clear_override_btn.clicked.connect(self._on_clear_override)
        self.clear_override_btn.hide()
        override_row.addWidget(self.clear_override_btn)

        override_layout.addLayout(override_row)

        # Override info
        self.override_info = QLabel("")
        self.override_info.setStyleSheet("color: #f39c12; font-size: 10px;")
        self.override_info.hide()
        override_layout.addWidget(self.override_info)

        parent_layout.addWidget(override_frame)
        self._auto_sections.append(override_frame)

        # === AUTO MODE SECTION ===
        auto_frame = QFrame()
        auto_frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        auto_layout = QHBoxLayout(auto_frame)
        auto_layout.setContentsMargins(12, 10, 12, 10)

        self.auto_label = QLabel("Modo automatico: ACTIVO")
        self.auto_label.setStyleSheet("color: #2ecc71;")
        auto_layout.addWidget(self.auto_label)
        auto_layout.addStretch()

        self.auto_btn = QPushButton("Desactivar Auto")
        self.auto_btn.setStyleSheet("""
            QPushButton { background: #7f8c8d; color: white; border: none; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background: #95a5a6; }
        """)
        self.auto_btn.clicked.connect(self._on_toggle_auto)
        auto_layout.addWidget(self.auto_btn)

        parent_layout.addWidget(auto_frame)
        self._auto_sections.append(auto_frame)

    def _apply_control_mode_btn_styles(self, mode: str):
        """Update AUTO/MANUAL button visual states."""
        is_auto = mode == "AUTO"
        self._ctrl_auto_btn.setChecked(is_auto)
        self._ctrl_manual_btn.setChecked(not is_auto)
        self._ctrl_auto_btn.setStyleSheet(f"""
            QPushButton {{ background: {'#27ae60' if is_auto else '#2c3e50'}; color: {'white' if is_auto else '#95a5a6'}; border: {'none' if is_auto else '1px solid #3d5266'}; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: {'#2ecc71' if is_auto else '#34495e'}; }}
        """)
        self._ctrl_manual_btn.setStyleSheet(f"""
            QPushButton {{ background: {'#e67e22' if not is_auto else '#2c3e50'}; color: {'white' if not is_auto else '#95a5a6'}; border: {'none' if not is_auto else '1px solid #3d5266'}; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: {'#f39c12' if not is_auto else '#34495e'}; }}
        """)

    def _update_control_mode_ui(self, control_mode: str):
        """Show/hide sections based on control_mode."""
        is_manual = control_mode == "MANUAL"
        for section in self._auto_sections:
            section.setVisible(not is_manual)
        self._manual_panel.setVisible(is_manual)

    def _on_set_control_mode(self, mode: str):
        if not self._calendar:
            return
        self._calendar.set_control_mode(mode)
        self._apply_control_mode_btn_styles(mode)
        self._update_control_mode_ui(mode)
        print(f"[CalendarTab] control_mode → {mode}")

    def _on_manual_clima(self, clima: str):
        """Exclusive selection in clima group."""
        self._manual_selected_clima = clima
        # Uncheck modo group (clima and modo are mutually exclusive selection contexts)
        self._manual_selected_modo = None
        for key, btn in self._manual_clima_btns.items():
            btn.setChecked(key == clima)
        for btn in self._manual_modo_btns.values():
            btn.setChecked(False)

    def _on_manual_modo(self, modo: str):
        """Exclusive selection in modo group."""
        self._manual_selected_modo = modo
        self._manual_selected_clima = None
        for key, btn in self._manual_modo_btns.items():
            btn.setChecked(key == modo)
        for btn in self._manual_clima_btns.values():
            btn.setChecked(False)

    def _on_manual_apply(self):
        """Apply manual mode + actions."""
        if not self._calendar:
            return

        # Determine selected mode
        selected = self._manual_selected_clima or self._manual_selected_modo
        if not selected:
            QMessageBox.warning(self, "Error", "Selecciona un modo primero")
            return

        # Gather active extras
        actions = [key for key, btn in self._manual_extra_btns.items() if btn.isChecked()]

        self._calendar.force_manual(selected, actions)
        actions_str = f" + {actions}" if actions else ""
        print(f"[CalendarTab] MANUAL APPLY: {selected}{actions_str}")

    def _create_permissions(self, parent_layout):
        """Panel de permisos"""
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        layout.addWidget(QLabel("PERMISOS"))

        grid = QGridLayout()
        grid.setSpacing(6)

        self.permission_indicators = {}
        perms = ["cam", "audio", "tracking", "dj"]
        for i, p in enumerate(perms):
            ind = PermissionIndicator(p)
            self.permission_indicators[p] = ind
            grid.addWidget(ind, 0, i)

        layout.addLayout(grid)

        # Energia
        energy_row = QHBoxLayout()
        energy_row.addWidget(QLabel("Energia:"))
        self.energy_label = QLabel("---")
        self.energy_label.setStyleSheet("color: #f39c12; font-weight: bold;")
        energy_row.addWidget(self.energy_label)
        energy_row.addStretch()
        layout.addLayout(energy_row)

        # Estados deshabilitados
        self.disabled_states = DisabledStatesWidget()
        layout.addWidget(self.disabled_states)

        parent_layout.addWidget(frame)

    def _create_status(self, parent_layout):
        """Panel de estado"""
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #1e272e; border-radius: 8px; border: 1px solid #34495e; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        layout.addWidget(QLabel("ESTADO DEL SISTEMA"))

        grid = QGridLayout()
        grid.setSpacing(4)

        grid.addWidget(QLabel("Estado:"), 0, 0)
        self.sys_status = QLabel("ESTABLE")
        self.sys_status.setStyleSheet("color: #2ecc71; font-weight: bold;")
        grid.addWidget(self.sys_status, 0, 1)

        grid.addWidget(QLabel("Desde:"), 1, 0)
        self.since_label = QLabel("---")
        grid.addWidget(self.since_label, 1, 1)

        grid.addWidget(QLabel("Duracion:"), 2, 0)
        self.uptime_label = QLabel("---")
        grid.addWidget(self.uptime_label, 2, 1)

        layout.addLayout(grid)

        # Indicador de gobernanza (dinámico)
        self.governance_status = QLabel("---")
        self.governance_status.setAlignment(Qt.AlignCenter)
        self.governance_status.setStyleSheet("font-size: 10px; font-weight: bold; margin-top: 8px;")
        layout.addWidget(self.governance_status)

        parent_layout.addWidget(frame)

    def _setup_timer(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_display)
        self._timer.start(1000)

    # ==================== API ====================

    def set_calendar_manager(self, calendar_manager) -> None:
        self._calendar = calendar_manager
        if SCHEDULE_EDITOR_AVAILABLE and self.schedule_editor:
            self.schedule_editor.set_calendar_manager(calendar_manager)
        self._update_display()
        # V9.2 FIX: Update active block highlight after loading schedule
        self._update_schedule_highlight()
        print("[CalendarTab] CalendarManager conectado")

    # ==================== CONTROLES ====================

    def _on_go(self, delay_minutes: int):
        if not self._calendar:
            return

        mode = self.mode_combo.currentText()

        # Confirmacion para GO inmediato
        if delay_minutes == 0:
            reply = QMessageBox.question(
                self,
                "Confirmar GO",
                f"¿Cambiar a {mode} ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

        self._calendar.go(mode, delay_minutes=delay_minutes)
        if delay_minutes > 0:
            print(f"[CalendarTab] GO programado: {mode} en {delay_minutes}min")
        else:
            print(f"[CalendarTab] GO: {mode}")

    def _on_cancel_go(self):
        if not self._calendar:
            return
        self._calendar.cancel_pending_go()
        print("[CalendarTab] GO pendiente cancelado")

    def _on_override(self):
        if not self._calendar:
            return

        mode = self.mode_combo.currentText()
        minutes = self.override_spin.value()

        try:
            from core.calendar import OverrideType
            self._calendar.set_override(mode, OverrideType.TEMPORARY, minutes, "UI Override")
            print(f"[CalendarTab] Override: {mode} por {minutes}min")
        except ImportError:
            print("[CalendarTab] Error importando OverrideType")

    def _on_clear_override(self):
        if not self._calendar:
            return
        self._calendar.clear_override()
        print("[CalendarTab] Override limpiado")

    def _on_toggle_auto(self):
        if not self._calendar:
            return

        state = self._calendar.get_state()
        is_auto = state.get("auto_mode_enabled", True)
        self._calendar.set_auto_mode(not is_auto)

    def _on_alert_confirmed(self):
        if not self._calendar:
            return
        self._calendar.acknowledge_alert()
        print("[CalendarTab] Alerta confirmada")

    # ==================== DISPLAY ====================

    def _update_display(self):
        self._update_clock()

        if not self._calendar:
            self._set_disconnected()
            return

        try:
            state = self._calendar.get_state()
            self._update_mode(state)
            self._update_timeline(state)
            self._update_actions_panel(state)
            self._update_permissions(state.get("permissions", {}))
            self._update_status(state)
            self._update_override(state)
            self._update_pending_go(state)
            self._update_auto_mode(state)
            self._update_control_mode(state)
            self._update_alert(state)
        except Exception as e:
            print(f"[CalendarTab] Error: {e}")

    def _update_clock(self):
        now = datetime.now()
        self.day_label.setText(DAY_NAMES[now.weekday()])
        self.time_label.setText(now.strftime("%H:%M:%S"))

    def _set_disconnected(self):
        self.mode_label.setText("---")
        self.mode_label.setStyleSheet("color: #7f8c8d;")
        self.source_label.setText("No conectado")
        self.timeline_status.setText("DESCONECTADO")
        self.timeline_status.setStyleSheet("color: #e74c3c;")
        self.sys_status.setText("DESCONECTADO")
        self.sys_status.setStyleSheet("color: #e74c3c;")
        # Governance status
        self.governance_status.setText("🔴 DESCONECTADO")
        self.governance_status.setStyleSheet("color: #e74c3c; font-size: 10px; font-weight: bold; margin-top: 8px;")
        # Actions panel - all off
        empty_modules = {k: False for k in CANONICAL_MODULE_CONFIG.keys()}
        self.actions_panel.update_modules(empty_modules, "---")

    def _update_mode(self, state):
        mode = state.get("current_mode", "apagado")
        source = state.get("source", "MANUAL")

        self.mode_label.setText(mode)
        color = MODE_COLORS.get(mode, "#7f8c8d")
        self.mode_label.setStyleSheet(f"color: {color};")

        src_map = {"MANUAL": "Manual", "AUTO": "Automatico", "OVERRIDE": "Override"}
        self.source_label.setText(f"Fuente: {src_map.get(source, source)}")

        # V9.2 FIX: Update schedule highlight when mode changes
        if mode != self._last_mode:
            self._last_mode = mode
            self._update_schedule_highlight()

    def _update_timeline(self, state):
        since_str = state.get("since")
        if not since_str:
            self.timeline_bar.setValue(0)
            self.elapsed_label.setText("---")
            return

        try:
            since = datetime.fromisoformat(since_str) if isinstance(since_str, str) else since_str
            elapsed = datetime.now() - since
            secs = int(elapsed.total_seconds())
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60

            if h > 0:
                self.elapsed_label.setText(f"Transcurrido: {h}h {m:02d}m")
            else:
                self.elapsed_label.setText(f"Transcurrido: {m}m {s:02d}s")

            self.timeline_status.setText("ACTIVO")
            self.timeline_status.setStyleSheet("color: #2ecc71;")

            # Progreso
            progress = state.get("progress", 0)
            pct = int(progress * 100)
            self.timeline_bar.setValue(pct)
            self.progress_pct.setText(f"{pct}%")

            # Proximo
            next_disp = state.get("next_change_display")
            next_mode = state.get("next_mode")
            remaining = state.get("time_remaining_display", "---")

            if next_disp and next_mode:
                self.next_label.setText(f"Proximo: {next_mode} a las {next_disp} ({remaining})")
            else:
                self.next_label.setText("Proximo: No programado")

        except Exception:
            self.elapsed_label.setText("---")

    def _update_actions_panel(self, state):
        """Actualiza el panel de acciones activas v6.4 - Refleja acciones REALES del bloque."""
        mode = state.get("current_mode", "apagado")

        # v6.4: Priorizar acciones del bloque activo (NO inferir del modo)
        current_actions = state.get("current_actions", [])

        # También revisar el active_block por si las acciones están ahí
        active_block = state.get("active_block", {})
        if not current_actions and active_block:
            current_actions = active_block.get("actions", [])

        # Convertir lista de acciones a diccionario de módulos
        # Mapeo de acciones a nombres de módulos en la UI
        ACTION_TO_MODULE = {
            "audio_911": "audio_engine",
            "vision_haze": "vision_haze",
            "vision_dj": "vision_dj",
            "vision_artista": "vision_artista",
            "tracking_cam": "tracking_cam",
            "dj_detection": "dj_detection",
            "cues_clima": "cues_clima",
            "system_idle": "system_idle",
        }

        if current_actions:
            # Usar acciones REALES del bloque (NO inferidas)
            modules = {k: False for k in CANONICAL_MODULE_CONFIG.keys()}
            for action in current_actions:
                module_key = ACTION_TO_MODULE.get(action, action)
                if module_key in modules:
                    modules[module_key] = True
            print(f"[CalendarUI] Actions panel updated from block: {current_actions}")
        else:
            # Fallback: usar calendar_rules para modos legacy sin actions[]
            try:
                from core.calendar.calendar_rules import get_permissions
                modules = get_permissions(mode)
            except ImportError:
                perms = state.get("permissions", {})
                modules = {
                    "audio_engine": perms.get("audio", False),
                    "vision_haze": perms.get("cam", False),
                    "vision_dj": perms.get("dj", False),
                    "vision_artista": False,
                    "tracking_cam": perms.get("tracking", False),
                    "dj_detection": perms.get("dj", False),
                    "cues_clima": False,
                    "system_idle": mode == "apagado",
                }

        self.actions_panel.update_modules(modules, mode)

    def _update_permissions(self, perms):
        for key, ind in self.permission_indicators.items():
            ind.set_enabled(perms.get(key, False))

        # Energia
        energy = perms.get("energy")
        if energy:
            self.energy_label.setText(energy.upper())
            energy_colors = {"low": "#2ecc71", "medium": "#f39c12", "high": "#e74c3c"}
            self.energy_label.setStyleSheet(f"color: {energy_colors.get(energy, '#7f8c8d')}; font-weight: bold;")
        else:
            self.energy_label.setText("---")
            self.energy_label.setStyleSheet("color: #7f8c8d;")

        # Estados deshabilitados
        disabled = perms.get("disable_states", [])
        self.disabled_states.set_disabled_states(disabled)

    def _update_status(self, state):
        mode = state.get("current_mode", "apagado")
        source = state.get("source", "AUTO")

        if mode == "apagado":
            self.sys_status.setText("APAGADO")
            self.sys_status.setStyleSheet("color: #e74c3c;")
            # Governance: pasivo cuando está apagado
            self.governance_status.setText("🟡 PASIVO (sistema idle)")
            self.governance_status.setStyleSheet("color: #f39c12; font-size: 10px; font-weight: bold; margin-top: 8px;")
        else:
            self.sys_status.setText("ESTABLE")
            self.sys_status.setStyleSheet("color: #2ecc71;")
            # Governance: activo gobernando
            src_text = "BIOS" if source == "AUTO" else source
            self.governance_status.setText(f"🟢 GOBERNANDO ({src_text})")
            self.governance_status.setStyleSheet("color: #2ecc71; font-size: 10px; font-weight: bold; margin-top: 8px;")

        since_str = state.get("since")
        if since_str:
            try:
                since = datetime.fromisoformat(since_str) if isinstance(since_str, str) else since_str
                self.since_label.setText(since.strftime("%H:%M:%S"))
                elapsed = datetime.now() - since
                mins = int(elapsed.total_seconds()) // 60
                if mins >= 60:
                    self.uptime_label.setText(f"{mins // 60}h {mins % 60}m")
                else:
                    self.uptime_label.setText(f"{mins} min")
            except:
                pass

    def _update_override(self, state):
        override = state.get("override", {})
        is_active = override.get("active", False)

        if is_active:
            self.override_badge.show()
            self.clear_override_btn.show()
            remaining = override.get("remaining_seconds", 0)
            if remaining > 0:
                mins = remaining // 60
                self.override_badge.setText(f"OVERRIDE ({mins}m)")
                self.override_info.setText(f"Override activo: {override.get('mode', '?')} por {mins} min restantes")
                self.override_info.show()
        else:
            self.override_badge.hide()
            self.clear_override_btn.hide()
            self.override_info.hide()

    def _update_pending_go(self, state):
        pending = state.get("pending_go")
        if pending:
            secs = pending.get("seconds_until", 0)
            mins = secs // 60
            self.pending_go_badge.setText(f"GO: {pending.get('mode', '?')} en {mins}m")
            self.pending_go_badge.show()
            self.cancel_go_btn.show()
        else:
            self.pending_go_badge.hide()
            self.cancel_go_btn.hide()

    def _update_auto_mode(self, state):
        is_auto = state.get("auto_mode_enabled", True)
        if is_auto:
            self.auto_label.setText("Modo automatico: ACTIVO")
            self.auto_label.setStyleSheet("color: #2ecc71;")
            self.auto_btn.setText("Desactivar Auto")
        else:
            self.auto_label.setText("Modo automatico: INACTIVO")
            self.auto_label.setStyleSheet("color: #e74c3c;")
            self.auto_btn.setText("Activar Auto")

    def _update_control_mode(self, state):
        cm = state.get("control_mode", "AUTO")
        self._apply_control_mode_btn_styles(cm)
        self._update_control_mode_ui(cm)

    def _update_alert(self, state):
        alert = state.get("alert")
        if alert and not alert.get("acknowledged", False):
            self.alert_banner.show_alert(
                alert.get("mode", "?"),
                alert.get("seconds_until", 0)
            )
        else:
            self.alert_banner.hide_alert()

    def _update_schedule_highlight(self):
        """V9.2 FIX: Update schedule editor to highlight active block."""
        if SCHEDULE_EDITOR_AVAILABLE and self.schedule_editor and self._calendar:
            try:
                self.schedule_editor.update_active_block_highlight()
            except Exception as e:
                print(f"[CalendarTab] Error updating schedule highlight: {e}")

    # ==================== LIFECYCLE ====================

    def stop_timer(self):
        if self._timer:
            self._timer.stop()

    def start_timer(self):
        if self._timer:
            self._timer.start(1000)
