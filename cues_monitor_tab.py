# cues_monitor_tab.py - Tab de Cues Monitor CON SOPORTE BRAKE ANALYZER REAL
# v4.11 - MANUAL BYPASS (Cue Monitor) + FAMILIAS EXTENDIDAS C60-C82
#
# CAMBIOS v4.11:
# ✅ Nuevas familias: CLIMA, HAZE, DJ, ARTIST, TRACKING (C60-C82)
# ✅ Lectura desde core/cues/cue_map.py (single source of truth)
# ✅ Sección visual para familias extendidas
#
# CAMBIOS v4.10:
# ✅ fire_cue() → fire_cue_manual() en _fire_cue_manual()
# ✅ Todos los handlers de botones usan métodos *_manual() para bypass READY
# ✅ MANUAL BYPASS (Cue Monitor) comentado en los métodos críticos

from __future__ import annotations

from typing import Dict, List, Optional, Set
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QSizePolicy, QFrame, QCheckBox
)
from PySide6.QtGui import QFont

# Importar mapa canónico de cues C60-C82
try:
    from core.cues import (
        FAMILIA_CLIMA, FAMILIA_HAZE, FAMILIA_DJ, FAMILIA_ARTIST, FAMILIA_TRACKING,
        CLIMA_CUE_MAP, HAZE_CUE_MAP, DJ_CUE_MAP, ARTIST_CUE_MAP, TRACKING_CUE_MAP,
        FAMILY_CUE_RANGES_EXTENDED,
        get_state_for_cue,
    )
    EXTENDED_FAMILIES_AVAILABLE = True
except ImportError:
    EXTENDED_FAMILIES_AVAILABLE = False
    FAMILIA_CLIMA = "CLIMA"
    FAMILIA_HAZE = "HAZE"
    FAMILIA_DJ = "DJ"
    FAMILIA_ARTIST = "ARTIST"
    FAMILIA_TRACKING = "TRACKING"
    FAMILY_CUE_RANGES_EXTENDED = {
        "CLIMA": [60, 61, 62, 63],
        "HAZE": [64, 65, 66],
        "DJ": [67, 68, 69, 70, 71],
        "ARTIST": [72, 73, 74, 75, 76, 77, 78, 79],
        "TRACKING": [80, 81, 82],
    }

# Mapa de presentación (CANÓNICO - sin inversiones)
DISPLAY_NAME = {
    "fx_dimmer": "FX Dimmer",
    "fx_color": "FX Color",
    "fx_beam": "FX Beam"
}

# Constantes de familias y mapeo
FAMILY_FX_COLOR = "FX_COLOR"
FAMILY_FX_BEAM = "FX_BEAM"
FAMILY_FX_DIMMER = "FX_DIMMER"
FAMILY_COLORES_FIJOS = "COLORES_FIJOS"
FAMILY_POSICIONES_FIJAS = "POSICIONES_FIJAS"
FAMILY_MOVIMIENTO = "MOVIMIENTO"
FAMILY_STROBE = "STROBE"
FAMILY_BRAKE = "BRAKE"
FAMILY_CONTROL_DIMMER = "CONTROL_DIMMER"
FAMILY_TIMED_SEQUENCE = "TIMED_SEQUENCE"

FAMILY_CUES = {
    FAMILY_FX_COLOR: [7, 8, 9, 57, 58, 59],
    FAMILY_FX_BEAM: [4, 5, 6, 54, 55, 56],
    FAMILY_FX_DIMMER: [1, 2, 3, 51, 52, 53],
    FAMILY_COLORES_FIJOS: [10, 11, 12, 13, 14, 15, 16, 17, 18],
    FAMILY_POSICIONES_FIJAS: [19, 20, 21, 22, 23, 24, 25, 26, 27],
    FAMILY_MOVIMIENTO: [28, 29, 30, 31, 32, 33, 34, 35, 36],
    FAMILY_STROBE: [37, 38, 39, 40],
    FAMILY_CONTROL_DIMMER: [41],
    FAMILY_BRAKE: [42, 43, 44],
    FAMILY_TIMED_SEQUENCE: [45, 46, 47, 48, 49, 50],
}

# CANON 911: ALTA→FX_DIMMER (apaga C41), MEDIA→FX_BEAM, BAJA→FX_COLOR
BG_FAMILY_BY_ENERGY = {
    "BAJA": FAMILY_FX_COLOR,
    "MEDIA": FAMILY_FX_BEAM,
    "ALTA": FAMILY_FX_DIMMER,
}

BTN_W = 50
BTN_H = 32

class CuesMonitorTab(QWidget):
    """Tab integrado de monitor de Cues para CueEngine Modular - CON BRAKE ANALYZER REAL."""
    
    def __init__(self, avolites=None, state_manager=None, energy_detector=None, parent=None, cue_engine=None,
                 modules_bajada=None, modules_golpe=None, modules_ataque=None, modules_brake=None):
        super().__init__(parent)
        
        # Referencias externas
        self.avolites = avolites
        self.state_manager = state_manager
        self.energy_detector = energy_detector
        self.cue_engine = cue_engine
        
        # Referencias a módulos para contar stats
        self.modules_bajada = modules_bajada or []
        self.modules_golpe = modules_golpe or []
        self.modules_ataque = modules_ataque or []
        self.modules_brake = modules_brake or []
        
        # Mapeo de botones por cue ID
        self.btns_by_cue: Dict[int, QPushButton] = {}
        
        # Cache para optimizar UI
        self._last_state = None
        self._last_energy = None
        self._last_active_cues = set()
        
        # Cache de configuración
        self._config_cache = None
        self._labels_cache = None
        
        self._setup_ui()
        
        # Timer para UI
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(40)
        self.ui_timer.timeout.connect(self._update_ui)
        self.ui_timer.start()
        
        # Actualización inicial
        self._update_ui()
        
        print("[CuesMonitorTab] v4.11: Brake Analyzer + MANUAL BYPASS + Familias C60-C82")

    def _load_config(self):
        """Carga la configuración si está disponible."""
        if self._config_cache is None and self.avolites:
            try:
                cfg = self.avolites.config_manager.config
                self._config_cache = cfg
                self._labels_cache = cfg.get('labels', {})
            except Exception as e:
                print(f"[CuesMonitorTab] Error cargando config: {e}")
                self._config_cache = {}
                self._labels_cache = {}
        return self._config_cache or {}

    def _get_cue_label(self, cue_id: int) -> str:
        """Obtiene el label de un cue desde la configuración."""
        if self._labels_cache:
            label = self._labels_cache.get(str(cue_id))
            if label:
                return f"C{cue_id}\n{label[:8]}"
        return f"C{cue_id}"

    def _get_display_name(self, internal_key: str) -> str:
        """Convierte nombre interno a nombre de presentación UI."""
        return DISPLAY_NAME.get(internal_key.lower(), internal_key)

    def _count_analyzer_stats(self) -> tuple:
        """Cuenta analizadores activos, disabled y placeholders"""
        all_modules = self.modules_bajada + self.modules_golpe + self.modules_ataque + self.modules_brake
        
        active = sum(1 for m in all_modules if getattr(m, 'active', True))
        disabled = sum(1 for m in all_modules if getattr(m, 'disabled_by_preset', False))
        placeholders = sum(1 for m in all_modules if getattr(m, 'is_placeholder', False))
        
        return active, disabled, placeholders

    def _get_brake_analyzer_telemetry(self) -> Optional[Dict]:
        """Obtiene telemetría del BrakeAnalyzer REAL si existe"""
        for module in self.modules_brake:
            # Detectar si es el BrakeAnalyzer real (tiene get_telemetry y no es placeholder)
            if (hasattr(module, 'get_telemetry') and 
                not getattr(module, 'is_placeholder', False) and
                hasattr(module, 'attach_audio')):
                try:
                    return module.get_telemetry()
                except Exception as e:
                    print(f"[CuesMonitorTab] Error obteniendo telemetría Brake: {e}")
        return None

    def _setup_ui(self):
        """Construye toda la interfaz de usuario."""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        
        # Header con información de estado + contadores
        self._create_header(root)
        
        # NUEVO: Sección Brake Analyzer
        self._create_brake_analyzer_section(root)
        
        # DEBUG INFO
        self._create_debug_section(root)
        
        # Secciones de cues
        self._create_base_golpe_section(root)
        self._create_bajada_section(root)
        self._create_specials_section(root)
        
        # Sección Auxiliar Time
        self._create_timed_sequence_section(root)

        # Sección Familias Extendidas C60-C82 (CLIMA, HAZE, DJ, ARTIST, TRACKING)
        self._create_extended_families_section(root)

        # Botones de control
        self._create_control_buttons(root)

    def _create_header(self, root):
        """Crea el header con información de estado y contadores."""
        header_frame = QFrame()
        header_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #333; border-radius: 6px; }"
        )
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 8, 10, 8)
        
        # Título
        title = QLabel("CUES MONITOR - 911 FIESTA v4.10 + MANUAL BYPASS + BRAKE ANALYZER REAL")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 12, QFont.Bold))
        title.setStyleSheet("color: #fff; margin-bottom: 5px;")
        header_layout.addWidget(title)
        
        # Info de estado
        self.header_info = QLabel("Estado: — | Energía: — | Engine: Modular")
        self.header_info.setAlignment(Qt.AlignCenter)
        self.header_info.setFont(QFont("Arial", 10))
        self.header_info.setStyleSheet("color: #ccc;")
        header_layout.addWidget(self.header_info)
        
        # Contadores de analizadores
        active, disabled, placeholders = self._count_analyzer_stats()
        self.analyzer_stats = QLabel(f"Analyzers → Active: {active} | Disabled: {disabled} | Placeholders: {placeholders}")
        self.analyzer_stats.setAlignment(Qt.AlignCenter)
        self.analyzer_stats.setFont(QFont("Arial", 9))
        self.analyzer_stats.setStyleSheet("color: #888; background: #0f0f0f; padding: 3px; border-radius: 3px;")
        header_layout.addWidget(self.analyzer_stats)
        
        # Línea de estado Aux Time
        self.aux_time_info = QLabel("AUX TIME: —")
        self.aux_time_info.setAlignment(Qt.AlignCenter)
        self.aux_time_info.setFont(QFont("Arial", 9))
        self.aux_time_info.setStyleSheet("color: #ff9800; background: #2a1b3d; padding: 2px; border-radius: 3px;")
        header_layout.addWidget(self.aux_time_info)
        
        root.addWidget(header_frame)

    def _create_brake_analyzer_section(self, root):
        """NUEVO: Crea sección dedicada para Brake Analyzer REAL"""
        brake_frame = QFrame()
        brake_frame.setStyleSheet(
            "QFrame { background: #2a1b3d; border: 2px solid #9c27b0; border-radius: 6px; }"
        )
        brake_layout = QVBoxLayout(brake_frame)
        brake_layout.setContentsMargins(10, 8, 10, 8)
        brake_layout.setSpacing(4)
        
        # Título
        brake_title = QLabel("🔥 BRAKE ANALYZER REAL")
        brake_title.setAlignment(Qt.AlignCenter)
        brake_title.setFont(QFont("Arial", 11, QFont.Bold))
        brake_title.setStyleSheet("color: #e1bee7; margin-bottom: 3px;")
        brake_layout.addWidget(brake_title)
        
        # Métricas principales
        self.brake_status = QLabel("Estado: Inicializando...")
        self.brake_status.setFont(QFont("Courier", 9))
        self.brake_status.setStyleSheet("color: #ce93d8; background: #1a0033; padding: 4px; border-radius: 3px;")
        self.brake_status.setWordWrap(True)
        brake_layout.addWidget(self.brake_status)
        
        root.addWidget(brake_frame)

    def _create_debug_section(self, root):
        """Crea sección de debug para diagnóstico."""
        debug_frame = QFrame()
        debug_frame.setStyleSheet(
            "QFrame { background: #0d1b2a; border: 1px solid #415a77; border-radius: 6px; }"
        )
        debug_layout = QVBoxLayout(debug_frame)
        debug_layout.setContentsMargins(10, 8, 10, 8)
        
        # Título debug
        debug_title = QLabel("DEBUG INFO")
        debug_title.setAlignment(Qt.AlignCenter)
        debug_title.setFont(QFont("Arial", 10, QFont.Bold))
        debug_title.setStyleSheet("color: #ffd60a;")
        debug_layout.addWidget(debug_title)
        
        # Info de debug
        self.debug_info = QLabel("Inicializando...")
        self.debug_info.setFont(QFont("Courier", 8))
        self.debug_info.setStyleSheet("color: #90e0ef;")
        self.debug_info.setWordWrap(True)
        debug_layout.addWidget(self.debug_info)
        
        root.addWidget(debug_frame)

    def _create_base_golpe_section(self, root):
        """Crea la sección de BASE GOLPE leyendo desde config."""
        bg_box = QGroupBox("BASE GOLPE")
        bg_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #fff; "
            "border: 2px solid #c62828; border-radius: 8px; "
            "margin-top: 6px; padding-top: 10px; }"
        )
        
        grid = QGridLayout(bg_box)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)
        
        # Cargar configuración
        cfg = self._load_config()
        families = cfg.get('families') or cfg.get('FAMILIES') or {}
        
        # Obtener las listas de cues desde config con fallback
        alta_cues = families.get('base_golpe_alta', [1, 2, 3, 51, 52, 53])
        media_cues = families.get('base_golpe_media', [4, 5, 6, 54, 55, 56])
        baja_cues = families.get('base_golpe_baja', [7, 8, 9, 57, 58, 59])
        
        # Actualizar el mapeo global
        FAMILY_CUES[FAMILY_FX_DIMMER] = alta_cues
        FAMILY_CUES[FAMILY_FX_BEAM] = media_cues
        FAMILY_CUES[FAMILY_FX_COLOR] = baja_cues
        
        # Usar nombres de presentación para UI
        fx_color_display = self._get_display_name("fx_dimmer")  # ALTA -> fx_dimmer -> "FX Color"
        fx_beam_display = self._get_display_name("fx_beam")     # MEDIA -> fx_beam -> "FX Beam"
        fx_dimmer_display = self._get_display_name("fx_color")  # BAJA -> fx_color -> "FX Dimmer"
        
        # FX Color (ALTA) - mostrar como "FX Color"
        self._add_cue_row(grid, 0, f"{fx_color_display} (ALTA)", alta_cues, "#f44336")
        
        # FX Beam (MEDIA) - mostrar como "FX Beam"
        self._add_cue_row(grid, 1, f"{fx_beam_display} (MEDIA)", media_cues, "#2196f3")
        
        # FX Dimmer (BAJA) - mostrar como "FX Dimmer"
        self._add_cue_row(grid, 2, f"{fx_dimmer_display} (BAJA)", baja_cues, "#4caf50")
        
        root.addWidget(bg_box)

    def _create_bajada_section(self, root):
        """Crea la sección de BAJADA."""
        bj_box = QGroupBox("BAJADA")
        bj_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #fff; "
            "border: 2px solid #2e7d32; border-radius: 8px; "
            "margin-top: 6px; padding-top: 10px; }"
        )
        
        grid = QGridLayout(bj_box)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)
        
        # Colores Fijos (C10-C18)
        self._add_cue_row(grid, 0, "Colores Fijos", [10, 11, 12, 13, 14, 15, 16, 17, 18], "#ff9800")
        
        # Posiciones Fijas (C19-C27)
        self._add_cue_row(grid, 1, "Posiciones Fijas", [19, 20, 21, 22, 23, 24, 25, 26, 27], "#9c27b0")
        
        # Movimiento (C28-C36)
        self._add_cue_row(grid, 2, "Movimiento", [28, 29, 30, 31, 32, 33, 34, 35, 36], "#00bcd4")
        
        root.addWidget(bj_box)

    def _create_specials_section(self, root):
        """Crea la sección de efectos especiales."""
        sp_box = QGroupBox("EFECTOS ESPECIALES / CONTROL")
        sp_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #fff; "
            "border: 2px solid #6a1b9a; border-radius: 8px; "
            "margin-top: 6px; padding-top: 10px; }"
        )
        
        grid = QGridLayout(sp_box)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)
        
        # Ataque/Strobe (C37-C40)
        self._add_cue_row(grid, 0, "Ataque/Strobe", [37, 38, 39, 40], "#ff5722")
        
        # Control Dimmer (C41)
        self._add_cue_row(grid, 1, "Control Dimmer", [41], "#ffc107")
        
        # Brake (C42-C44)
        self._add_cue_row(grid, 2, "Brake", [42, 43, 44], "#9c27b0")
        
        root.addWidget(sp_box)

    def _create_timed_sequence_section(self, root):
        """Crea la sección de Auxiliar Time."""
        ts_box = QGroupBox("AUXILIAR TIME (TIMED SEQUENCE)")
        ts_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #fff; "
            "border: 2px solid #ff9800; border-radius: 8px; "
            "margin-top: 6px; padding-top: 10px; }"
        )
        
        grid = QGridLayout(ts_box)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)
        
        # Auxiliar Time (C45-C50)
        self._add_cue_row(grid, 0, "Auxiliar Time", [45, 46, 47, 48, 49, 50], "#ff9800")

        root.addWidget(ts_box)

    def _create_extended_families_section(self, root):
        """Crea la sección de familias extendidas C60-C82 (CLIMA, HAZE, DJ, ARTIST, TRACKING)."""
        ext_box = QGroupBox("FAMILIAS EXTENDIDAS (C60-C82)")
        ext_box.setStyleSheet(
            "QGroupBox { font-weight: bold; color: #fff; "
            "border: 2px solid #00bcd4; border-radius: 8px; "
            "margin-top: 6px; padding-top: 10px; }"
        )

        grid = QGridLayout(ext_box)
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(8)

        # CLIMA (C60-C63): clima_1, clima_2, clima_3, clima_4
        clima_cues = FAMILY_CUE_RANGES_EXTENDED.get(FAMILIA_CLIMA, [60, 61, 62, 63])
        self._add_cue_row_with_labels(grid, 0, "CLIMA", clima_cues,
                                       ["clima_1", "clima_2", "clima_3", "clima_4"], "#1abc9c")

        # HAZE (C64-C66): LOW, MID, HIGH
        haze_cues = FAMILY_CUE_RANGES_EXTENDED.get(FAMILIA_HAZE, [64, 65, 66])
        self._add_cue_row_with_labels(grid, 1, "HAZE", haze_cues,
                                       ["LOW", "MID", "HIGH"], "#e91e63")

        # DJ (C67-C71): dj_1..dj_5
        dj_cues = FAMILY_CUE_RANGES_EXTENDED.get(FAMILIA_DJ, [67, 68, 69, 70, 71])
        self._add_cue_row_with_labels(grid, 2, "DJ", dj_cues,
                                       ["dj_1", "dj_2", "dj_3", "dj_4", "dj_5"], "#3f51b5")

        # ARTIST (C72-C79): T1..T8
        artist_cues = FAMILY_CUE_RANGES_EXTENDED.get(FAMILIA_ARTIST, list(range(72, 80)))
        self._add_cue_row_with_labels(grid, 3, "ARTIST", artist_cues,
                                       ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"], "#9c27b0")

        # TRACKING (C80-C82): idle, follow, focus
        tracking_cues = FAMILY_CUE_RANGES_EXTENDED.get(FAMILIA_TRACKING, [80, 81, 82])
        self._add_cue_row_with_labels(grid, 4, "TRACKING", tracking_cues,
                                       ["idle", "follow", "focus"], "#00bcd4")

        root.addWidget(ext_box)

    def _add_cue_row_with_labels(self, grid: QGridLayout, row: int, family: str,
                                  cues: List[int], state_labels: List[str], color: str):
        """Agrega una fila de cues con etiquetas de estado."""
        # Etiqueta de familia
        lbl = QLabel(family)
        lbl.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")
        lbl.setMinimumWidth(80)
        grid.addWidget(lbl, row, 0)

        # Botones de cues con labels de estado
        for i, cue_id in enumerate(cues):
            state_label = state_labels[i] if i < len(state_labels) else ""
            btn = self._create_cue_button_with_state(cue_id, state_label)
            grid.addWidget(btn, row, i + 1)

    def _create_cue_button_with_state(self, cue_id: int, state_label: str) -> QPushButton:
        """Crea un botón para un cue extendido con su label de estado."""
        btn_text = f"C{cue_id}\n{state_label[:6]}" if state_label else f"C{cue_id}"

        btn = QPushButton(btn_text)
        btn.setProperty("cue_id", cue_id)
        btn.setFixedSize(BTN_W + 5, BTN_H + 12)
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn.setToolTip(f"Cue {cue_id}: {state_label}")

        # MANUAL BYPASS: Usar _fire_cue_manual
        btn.clicked.connect(lambda checked, cid=cue_id: self._fire_cue_manual(cid))

        self._style_button(btn, active=False, dimmed=False)
        self.btns_by_cue[cue_id] = btn

        return btn

    def _add_cue_row(self, grid: QGridLayout, row: int, label: str, cues: List[int], color: str):
        """Agrega una fila de cues con etiqueta."""
        # Etiqueta
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")
        lbl.setMinimumWidth(120)
        grid.addWidget(lbl, row, 0)
        
        # Botones de cues
        for i, cue_id in enumerate(cues, start=1):
            btn = self._create_cue_button(cue_id)
            grid.addWidget(btn, row, i)

    def _create_cue_button(self, cue_id: int) -> QPushButton:
        """Crea un botón individual para un cue."""
        btn_text = self._get_cue_label(cue_id)
        
        btn = QPushButton(btn_text)
        btn.setProperty("cue_id", cue_id)
        
        if '\n' in btn_text:
            btn.setFixedSize(BTN_W, BTN_H + 10)
        else:
            btn.setFixedSize(BTN_W, BTN_H)
        
        btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        if self._labels_cache:
            full_label = self._labels_cache.get(str(cue_id))
            if full_label:
                btn.setToolTip(f"Cue {cue_id}: {full_label}")
        
        # MANUAL BYPASS (Cue Monitor): Usar _fire_cue_manual que llama a fire_cue_manual()
        btn.clicked.connect(lambda checked, cid=cue_id: self._fire_cue_manual(cid))
        
        self._style_button(btn, active=False, dimmed=False)
        
        self.btns_by_cue[cue_id] = btn
        
        return btn

    def _style_button(self, btn: QPushButton, active: bool, dimmed: bool):
        """Aplica estilos al botón según su estado."""
        if active:
            style = (
                "QPushButton { "
                "background: #1976d2; color: white; font-weight: bold; "
                "border: 2px solid #0d47a1; border-radius: 4px; "
                "font-size: 10px; "
                "} "
                "QPushButton:hover { background: #1565c0; }"
            )
        elif dimmed:
            style = (
                "QPushButton { "
                "background: #2a2a2a; color: #666; "
                "border: 1px solid #444; border-radius: 4px; opacity: 0.6; "
                "font-size: 10px; "
                "} "
                "QPushButton:hover { background: #333; }"
            )
        else:
            style = (
                "QPushButton { "
                "background: #333; color: #ddd; "
                "border: 1px solid #555; border-radius: 4px; "
                "font-size: 10px; "
                "} "
                "QPushButton:hover { background: #444; border: 1px solid #777; }"
            )
        
        btn.setStyleSheet(style)

    def _create_control_buttons(self, root):
        """Crea botones de control general."""
        control_frame = QFrame()
        control_layout = QHBoxLayout(control_frame)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # Botón Kill All
        self.btn_kill_all = QPushButton("KILL ALL")
        self.btn_kill_all.setStyleSheet(
            "QPushButton { "
            "background: #d32f2f; color: white; font-weight: bold; "
            "border: 1px solid #b71c1c; border-radius: 4px; padding: 8px 16px; "
            "} "
            "QPushButton:hover { background: #c62828; }"
        )
        self.btn_kill_all.clicked.connect(self._kill_all_cues)
        
        # Botón Force Update
        self.btn_force_update = QPushButton("Force Update")
        self.btn_force_update.setStyleSheet(
            "QPushButton { "
            "background: #2e7d32; color: white; font-weight: bold; "
            "border: 1px solid #1b5e20; border-radius: 4px; padding: 8px 16px; "
            "} "
            "QPushButton:hover { background: #388e3c; }"
        )
        self.btn_force_update.clicked.connect(self._force_update)
        
        # Botón de estado de conexión
        self.btn_connection = QPushButton("Avolites: —")
        self.btn_connection.setStyleSheet(
            "QPushButton { "
            "background: #666; color: white; "
            "border: 1px solid #555; border-radius: 4px; padding: 8px 16px; "
            "}"
        )
        
        control_layout.addWidget(self.btn_kill_all)
        control_layout.addWidget(self.btn_force_update)
        control_layout.addStretch()
        control_layout.addWidget(self.btn_connection)
        
        root.addWidget(control_frame)

    def _fire_cue_manual(self, cue_id: int):
        """
        Dispara un cue manualmente usando Avolites directo.
        
        MANUAL BYPASS (Cue Monitor): Usa fire_cue_manual() en lugar de fire_cue()
        para bypasear el chequeo de READY. Esto permite que las acciones manuales
        del usuario lleguen al worker aunque Avolites esté en NOT_READY.
        """
        try:
            if self.avolites and hasattr(self.avolites, 'fire_cue_manual'):
                # MANUAL BYPASS: Usar fire_cue_manual() que bypasea READY
                success = self.avolites.fire_cue_manual(cue_id)
                if success:
                    print(f"[CuesMonitorTab] Disparado manual C{cue_id} (BYPASS READY)")
                else:
                    print(f"[CuesMonitorTab] Error disparando C{cue_id}")
            else:
                print(f"[CuesMonitorTab] MOCK Fire C{cue_id}")
        except Exception as e:
            print(f"[CuesMonitorTab] Error disparando cue C{cue_id}: {e}")

    def _kill_all_cues(self):
        """
        KILL ALL CANÓNICO — Mata cues en Titan Y resetea estado lógico.

        Para testing: el sistema queda SILENTE hasta el próximo evento musical.

        1. Mata TODOS los cues en Titan
        2. Resetea estado lógico del sistema (silent_reset)
        3. NO dispara C41 automáticamente
        """
        try:
            # 1. Kill all cues en Titan
            if self.avolites and hasattr(self.avolites, 'kill_all_cues'):
                self.avolites.kill_all_cues()
                print("[CuesMonitorTab] Kill All → Titan OK")
            else:
                print("[CuesMonitorTab] MOCK Kill All")

            # 2. Silent reset del CueEngine (sin disparar cues)
            if self.cue_engine and hasattr(self.cue_engine, 'silent_reset'):
                self.cue_engine.silent_reset()
                print("[CuesMonitorTab] Kill All → Estado lógico reseteado")

        except Exception as e:
            print(f"[CuesMonitorTab] Error en Kill All: {e}")

    def _force_update(self):
        """Fuerza actualización del CueEngine."""
        try:
            if self.cue_engine and hasattr(self.cue_engine, 'force_update'):
                self.cue_engine.force_update()
                print("[CuesMonitorTab] Force Update ejecutado")
        except Exception as e:
            print(f"[CuesMonitorTab] Error en Force Update: {e}")

    def _get_active_cues_from_specialists(self) -> Set[int]:
        """Obtiene cues activos consultando cada especialista del CueEngine."""
        active_cues = set()
        
        if not self.cue_engine or not hasattr(self.cue_engine, 'specialists'):
            return active_cues
        
        try:
            for specialist_name, specialist in self.cue_engine.specialists.items():
                if hasattr(specialist, 'get_status'):
                    status = specialist.get_status()
                    specialist_actives = status.get('active_cues', [])
                    active_cues.update(specialist_actives)
                    
        except Exception as e:
            print(f"[CuesMonitorTab] Error obteniendo cues de especialistas: {e}")
        
        return active_cues

    def _get_active_cues_from_family_manager(self) -> Set[int]:
        """
        V9.1 FIX: Obtiene cues activos de FamilyManager (familias extendidas C60-C82).
        Permite que CueMonitor muestre los cues de Vision (DJ, HAZE, ARTIST, etc.)
        """
        active_cues = set()

        if not self.cue_engine:
            return active_cues

        try:
            if hasattr(self.cue_engine, 'get_extended_family_active_cues'):
                active_cues = self.cue_engine.get_extended_family_active_cues()
        except Exception as e:
            print(f"[CuesMonitorTab] Error obteniendo cues de FamilyManager: {e}")

        return active_cues

    def _get_active_cues_direct_check(self) -> Set[int]:
        """Verifica directamente con Avolites qué cues están activos."""
        active_cues = set()
        
        if not self.avolites:
            return active_cues
        
        try:
            cfg = self._load_config()
            families = cfg.get('families') or cfg.get('FAMILIES') or {}
            
            bg_cues = []
            bg_cues.extend(families.get('base_golpe_alta', [1, 2, 3, 51, 52, 53]))
            bg_cues.extend(families.get('base_golpe_media', [4, 5, 6, 54, 55, 56]))
            bg_cues.extend(families.get('base_golpe_baja', [7, 8, 9, 57, 58, 59]))

            other_cues = list(range(10, 51))

            # Incluir familias extendidas C60-C82
            extended_cues = list(range(60, 83))

            all_cues = set(bg_cues + other_cues + extended_cues)
            
            for cue_id in all_cues:
                try:
                    if hasattr(self.avolites, 'is_active') and self.avolites.is_active(cue_id):
                        active_cues.add(cue_id)
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"[CuesMonitorTab] Error verificación directa: {e}")
        
        return active_cues

    def _update_ui(self):
        """Actualiza la interfaz de usuario."""
        try:
            # Obtener estado y energía
            state_name = "BASE_GOLPE"
            energy_level = "MEDIA"
            
            if self.state_manager:
                try:
                    status = self.state_manager.get_status()
                    state_name = status.get("current_state", state_name)
                except Exception:
                    pass
            
            if self.energy_detector:
                try:
                    if hasattr(self.energy_detector, 'get_energy_name'):
                        energy_level = self.energy_detector.get_energy_name()
                    elif hasattr(self.energy_detector, 'get_energy'):
                        energy_level = self.energy_detector.get_energy()
                except Exception:
                    pass
            
            # Usar ambos métodos para obtener cues activos
            active_cues_specialists = self._get_active_cues_from_specialists()
            active_cues_direct = self._get_active_cues_direct_check()

            # V9.1 FIX: Obtener cues activos de FamilyManager (Vision modules)
            active_cues_family = self._get_active_cues_from_family_manager()

            active_cues = active_cues_specialists.union(active_cues_direct).union(active_cues_family)
            
            # Actualizar contadores de analizadores
            active, disabled, placeholders = self._count_analyzer_stats()
            self.analyzer_stats.setText(f"Analyzers → Active: {active} | Disabled: {disabled} | Placeholders: {placeholders}")
            
            # NUEVO: Actualizar información de Brake Analyzer REAL
            brake_telemetry = self._get_brake_analyzer_telemetry()
            if brake_telemetry:
                brake_active = brake_telemetry.get("active", False)
                brake_level = brake_telemetry.get("level", "none")
                delta_db = brake_telemetry.get("delta_db", 0.0)
                hiband_drop = brake_telemetry.get("hiband_drop_db", 0.0)
                hold_rem = brake_telemetry.get("hold_remaining", 0.0)
                cooldown_rem = brake_telemetry.get("cooldown_remaining", 0.0)
                fps = brake_telemetry.get("fps", 0)
                
                if brake_active:
                    brake_text = f"🔥 ACTIVO | Level: {brake_level.upper()} | ΔdB: {delta_db:.1f} | HiBand↓: {hiband_drop:.1f}dB | Hold: {hold_rem:.1f}s"
                elif cooldown_rem > 0:
                    brake_text = f"⏳ Cooldown: {cooldown_rem:.1f}s | ΔdB: {delta_db:.1f} | HiBand↓: {hiband_drop:.1f}dB | FPS: {fps}"
                else:
                    brake_text = f"⚪ Inactivo | ΔdB: {delta_db:.1f} | HiBand↓: {hiband_drop:.1f}dB | FPS: {fps}"
                
                self.brake_status.setText(brake_text)
            else:
                self.brake_status.setText("⚠️ BrakeAnalyzer REAL no disponible o no tiene telemetría")
            
            # Actualizar información de Aux Time
            aux_time_text = "AUX TIME: —"
            if self.cue_engine and hasattr(self.cue_engine, 'specialists'):
                try:
                    timed_specialist = self.cue_engine.specialists.get("timed")
                    if timed_specialist and hasattr(timed_specialist, 'get_status'):
                        st = timed_specialist.get_status()
                        dwell = st.get("dwell", 0.0)
                        eta = st.get("next_eta", 0.0)
                        last = st.get("last_fired_cue")
                        idx = st.get("global_index", 0)
                        fires = st.get("fires_total", 0)
                        
                        last_str = f"C{last}" if last else "—"
                        aux_time_text = f"AUX TIME: dwell={dwell:.1f}s | next={eta:.1f}s | last={last_str} | idx={idx} | total={fires}"
                except Exception as e:
                    aux_time_text = f"AUX TIME: error({e})"
            
            if aux_time_text != getattr(self, '_last_aux_time_text', None):
                self._last_aux_time_text = aux_time_text
                self.aux_time_info.setText(aux_time_text)
            
            # DEBUG INFO MEJORADO
            debug_text = f"Estado: {state_name} | Energía: {energy_level}\n"
            debug_text += f"Cues activos (Especialistas): {sorted(list(active_cues_specialists))}\n"
            debug_text += f"Cues activos (Directo): {sorted(list(active_cues_direct))}\n"
            debug_text += f"Cues activos (FamilyMgr): {sorted(list(active_cues_family))}\n"
            debug_text += f"Cues activos (Final): {sorted(list(active_cues))}\n"
            debug_text += f"Analyzers: Active={active} Disabled={disabled} Placeholders={placeholders}\n"
            
            # NUEVO: Info Brake Analyzer en debug
            if brake_telemetry:
                debug_text += f"Brake: active={brake_telemetry.get('active')} level={brake_telemetry.get('level')} fps={brake_telemetry.get('fps')}\n"
            
            if self.cue_engine:
                try:
                    engine_status = self.cue_engine.get_status()
                    debug_text += f"CueEngine Updates: {engine_status.get('stats', {}).get('total_updates', 0)}\n"
                    debug_text += f"Specialist Calls: {engine_status.get('stats', {}).get('specialist_calls', 0)}\n"
                    debug_text += f"Auto-update: {engine_status.get('auto_update_running', False)}"
                except Exception as e:
                    debug_text += f"Error CueEngine: {e}"
            
            self.debug_info.setText(debug_text)
            
            # Actualizar header
            header_text = f"Estado: {state_name} | Energía: {energy_level} | Engine: Modular"
            if header_text != getattr(self, '_last_header_text', None):
                self._last_header_text = header_text
                self.header_info.setText(header_text)
            
            # Actualizar estado de conexión
            if self.avolites:
                try:
                    status = self.avolites.get_status()
                    connected = status.get("connected", False)
                    if connected:
                        self.btn_connection.setText("Avolites: ✓")
                        self.btn_connection.setStyleSheet(
                            "QPushButton { background: #4caf50; color: white; "
                            "border: 1px solid #388e3c; border-radius: 4px; padding: 8px 16px; }"
                        )
                    else:
                        self.btn_connection.setText("Avolites: ✗")
                        self.btn_connection.setStyleSheet(
                            "QPushButton { background: #f44336; color: white; "
                            "border: 1px solid #d32f2f; border-radius: 4px; padding: 8px 16px; }"
                        )
                except Exception:
                    pass
            
            # Obtener familia permitida según energía
            bg_family_allowed = BG_FAMILY_BY_ENERGY.get(energy_level, FAMILY_FX_BEAM)
            
            # Solo actualizar si algo cambió
            if (active_cues != self._last_active_cues or 
                state_name != self._last_state or 
                energy_level != self._last_energy):
                
                self._last_active_cues = active_cues.copy()
                self._last_state = state_name
                self._last_energy = energy_level
                
                # Actualizar botones BG (con dimming según energía)
                bg_families = {
                    FAMILY_FX_COLOR: FAMILY_CUES[FAMILY_FX_COLOR],
                    FAMILY_FX_BEAM: FAMILY_CUES[FAMILY_FX_BEAM],
                    FAMILY_FX_DIMMER: FAMILY_CUES[FAMILY_FX_DIMMER],
                }
                
                for family, cues in bg_families.items():
                    dimmed = (state_name == "BASE_GOLPE" and family != bg_family_allowed)
                    for cue_id in cues:
                        btn = self.btns_by_cue.get(cue_id)
                        if btn:
                            active = cue_id in active_cues
                            self._style_button(btn, active=active, dimmed=dimmed)
                
                # Actualizar resto de botones (sin dimming)
                other_families = {
                    FAMILY_COLORES_FIJOS: [10, 11, 12, 13, 14, 15, 16, 17, 18],
                    FAMILY_POSICIONES_FIJAS: [19, 20, 21, 22, 23, 24, 25, 26, 27],
                    FAMILY_MOVIMIENTO: [28, 29, 30, 31, 32, 33, 34, 35, 36],
                    FAMILY_STROBE: [37, 38, 39, 40],
                    FAMILY_CONTROL_DIMMER: [41],
                    FAMILY_BRAKE: [42, 43, 44],
                    FAMILY_TIMED_SEQUENCE: [45, 46, 47, 48, 49, 50],
                }
                
                for family, cues in other_families.items():
                    for cue_id in cues:
                        btn = self.btns_by_cue.get(cue_id)
                        if btn:
                            active = cue_id in active_cues
                            self._style_button(btn, active=active, dimmed=False)
            
        except Exception as e:
            print(f"[CuesMonitorTab] Error en _update_ui: {e}")

    def cleanup(self):
        """Limpia recursos al cerrar."""
        try:
            if hasattr(self, 'ui_timer'):
                self.ui_timer.stop()
        except Exception:
            pass


def create_cues_monitor_tab(*, avolites=None, state_manager=None, energy_detector=None, parent=None, cue_engine=None,
                            modules_bajada=None, modules_golpe=None, modules_ataque=None, modules_brake=None) -> CuesMonitorTab:
    """Factory function para crear el tab de cues monitor."""
    return CuesMonitorTab(
        avolites=avolites,
        state_manager=state_manager, 
        energy_detector=energy_detector,
        parent=parent,
        cue_engine=cue_engine,
        modules_bajada=modules_bajada,
        modules_golpe=modules_golpe,
        modules_ataque=modules_ataque,
        modules_brake=modules_brake
    )