# main.py - 911 Fiesta v4.12 - SETTERS DINÁMICOS (UI) + ENGINE SIEMPRE CORRE
# =============================================================================
# CRITICAL: OpenMP fix MUST run BEFORE any import of numpy/torch/cv2/pyav/etc.
# Fixes Windows "OMP: Error #15: libiomp5md.dll already initialized" crash.
# =============================================================================
import os as _os
import sys as _sys

# --- OpenMP Duplicate Runtime Protection (Windows/Conda) ---
_os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
_os.environ.setdefault("OMP_NUM_THREADS", "1")
_os.environ.setdefault("MKL_NUM_THREADS", "1")
_os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

# --- Conda PATH priority (Windows DLL search fix) ---
_conda_prefix = _os.environ.get("CONDA_PREFIX")
_conda_path_prepended = False
if _sys.platform == "win32" and _conda_prefix:
    _conda_lib_bin = _os.path.join(_conda_prefix, "Library", "bin")
    if _os.path.isdir(_conda_lib_bin):
        _current_path = _os.environ.get("PATH", "")
        if _conda_lib_bin.lower() not in _current_path.lower():
            _os.environ["PATH"] = _conda_lib_bin + _os.pathsep + _current_path
            _conda_path_prepended = True
        # Python 3.8+: explicit DLL directory registration
        if hasattr(_os, "add_dll_directory"):
            try:
                _os.add_dll_directory(_conda_lib_bin)
            except OSError:
                pass

# --- Boot logs (once per session) ---
if _os.environ.get("_911_OMP_BOOT_LOGGED") != "1":
    _os.environ["_911_OMP_BOOT_LOGGED"] = "1"
    print(f"[BOOT] KMP_DUPLICATE_LIB_OK={_os.environ.get('KMP_DUPLICATE_LIB_OK')}")
    print(f"[BOOT] OMP_NUM_THREADS={_os.environ.get('OMP_NUM_THREADS')}")
    print(f"[BOOT] MKL_NUM_THREADS={_os.environ.get('MKL_NUM_THREADS')}")
    print(f"[BOOT] OPENBLAS_NUM_THREADS={_os.environ.get('OPENBLAS_NUM_THREADS')}")
    print(f"[BOOT] CONDA_PREFIX={_conda_prefix or '(not set)'}")
    if _conda_path_prepended:
        print(f"[BOOT] PATH prepended: {_conda_lib_bin}")

# Cleanup temp vars (keep namespace clean)
del _conda_prefix, _conda_path_prepended
if "_conda_lib_bin" in dir():
    del _conda_lib_bin
if "_current_path" in dir():
    del _current_path

# =============================================================================
# FIX v4.12 - SETTERS PARA UI:
# ✅ AvolitesController tiene set_local_interface() y set_console_ip()
# ✅ UI puede cambiar interfaz de red y target Titan en caliente
# ✅ No más AttributeError al usar panel de red
#
# FIX v4.11 - ENGINE SIEMPRE CORRE:
# ✅ Eliminado bloqueo "if total_updates == 0" en _update_cue_engine()
# ✅ CueEngine.update() ahora corre SIEMPRE (línea ~1949)
# ✅ El engine/transporte decide si envía comandos según su estado
# ✅ Stats de engine (Updates/Estados/Llamadas) ahora suben correctamente
# ============================================================================
import os
import sys

# =============================================================================
# BOOTSTRAP GUARD v1.0 - Portabilidad entre máquinas
# =============================================================================
# Soluciona crash de signature_bootstrap.py (shiboken6) cuando:
# - Se copia repo entre máquinas
# - Variables de entorno Qt no están configuradas
# - PySide6 no encuentra sus plugins
# =============================================================================

def _bootstrap_guard():
    """Configura entorno Qt ANTES de importar PySide6."""
    import importlib.util

    # 1) Log básico de arranque (solo una vez)
    _log_startup = os.environ.get("_911_BOOT_LOGGED") != "1"
    if _log_startup:
        os.environ["_911_BOOT_LOGGED"] = "1"
        print(f"[BOOT] sys.executable: {sys.executable}")
        print(f"[BOOT] cwd: {os.getcwd()}")
        print(f"[BOOT] sys.path[0]: {sys.path[0] if sys.path else 'N/A'}")

    # 2) Detectar si PySide6 está instalado
    pyside_spec = importlib.util.find_spec("PySide6")
    if not pyside_spec or not pyside_spec.origin:
        print("[BOOT] ERROR: PySide6 no encontrado. Instalar: pip install pyside6")
        return False

    pyside_dir = os.path.dirname(pyside_spec.origin)

    # 3) Configurar Qt plugin path si no existe
    if not os.environ.get("QT_PLUGIN_PATH"):
        plugins_path = os.path.join(pyside_dir, "plugins")
        if os.path.isdir(plugins_path):
            os.environ["QT_PLUGIN_PATH"] = plugins_path
            if _log_startup:
                print(f"[BOOT] QT_PLUGIN_PATH set: {plugins_path}")

    # 4) Windows: configurar platform plugin
    if sys.platform == "win32":
        if not os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
            platform_plugins = os.path.join(pyside_dir, "plugins", "platforms")
            if os.path.isdir(platform_plugins):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platform_plugins

    # 5) Verificar shiboken6/signature_bootstrap (causa del crash)
    shiboken_spec = importlib.util.find_spec("shiboken6")
    if shiboken_spec and shiboken_spec.origin:
        shiboken_dir = os.path.dirname(shiboken_spec.origin)
        sig_bootstrap = os.path.join(shiboken_dir, "signature_bootstrap.py")
        if os.path.exists(sig_bootstrap) and _log_startup:
            print(f"[BOOT] signature_bootstrap: {sig_bootstrap}")

    return True

# Ejecutar bootstrap ANTES de cualquier import de PySide6
_bootstrap_guard()

import math, json, threading, subprocess, platform, time, collections
import numpy as np
import sounddevice as sd

# PySide6 import con fallback informativo
try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QComboBox, QScrollArea, QGridLayout, QMessageBox,
        QFileDialog, QFrame, QTabWidget, QStackedWidget, QProgressBar, QSizePolicy, QLineEdit,
        QCheckBox, QRadioButton, QButtonGroup, QSpinBox
    )
    from PySide6.QtCore import QTimer, Qt, QElapsedTimer, QDateTime
except ImportError as e:
    print(f"[BOOT] FATAL: No se pudo importar PySide6: {e}")
    print("[BOOT] Ejecutar: python tools/diag_boot.py para diagnóstico")
    print("[BOOT] Solución: pip uninstall pyside6 shiboken6 && pip install pyside6")
    sys.exit(1)

# --- PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for sub in ("", "analyzers", "analizer"):
    p = os.path.join(BASE_DIR, sub)
    if p not in sys.path and os.path.isdir(p):
        sys.path.insert(0, p)

# --- IMPORTS BÁSICOS ---
from engine_audio import AudioEngine
from waveform_smooth import SmoothWaveform
from state_manager import StateManager
from core.audio_monitor import AudioMonitor

# Music Structure Engine (MSE) — replaces MIL-Lite
try:
    from core.music_structure_engine import MusicStructureEngine
    _MSE_AVAILABLE = True
except Exception as e:
    MusicStructureEngine = None
    _MSE_AVAILABLE = False
    print(f"[MSE] import FAILED: {e}")
print(f"[MSE] available={_MSE_AVAILABLE}")

# V12: Neon Pro UI Styling
try:
    from neon_styles import (
        get_full_stylesheet, NEON_CYAN, BG_DARK, BG_PANEL, BG_CARD,
        BUTTON_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_DANGER_STYLE,
        TAB_WIDGET_STYLE, PROGRESS_BAR_STYLE, SLIDER_STYLE,
        VU_METER_STYLE, LABEL_TITLE_STYLE, LABEL_SECTION_STYLE,
        state_indicator_style, energy_indicator_style,
        CARD_PADDING, CARD_RADIUS, GRID_SPACING, SIDEBAR_WIDTH,
        CARD_BACKGROUND, CARD_BORDER,
        S_SM, S_MD, S_BASE, S_LG, S_XL, S_2XL,
        R_SM, R_MD, R_LG, R_XL,
        BG_PANEL_SOLID, BG_CARD_SOLID, BG_INSET_SOLID, BORDER_SOLID,
        TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
        NEON_GREEN, FONT_TITLE, FONT_BODY, FONT_MONO,
    )
    NEON_STYLES_AVAILABLE = True
except ImportError:
    NEON_STYLES_AVAILABLE = False
    print("[MAIN] Neon styles not available, using default styling")

# --- IMPORTS OPCIONALES ---
def safe_import(module_name, class_name, fallback_name=None):
    try:
        for pkg in ("", "analyzers", "analizer"):
            try:
                full = f"{pkg + '.' if pkg else ''}{module_name}"
                mod = __import__(full, fromlist=[class_name])
                cls = getattr(mod, class_name)
                return cls, True
            except ImportError:
                continue
        raise ImportError(f"No se encontró {module_name}.{class_name}")
    except Exception as e:
        class Placeholder:
            name = fallback_name or f"{class_name} (NO DISPONIBLE)"
            is_placeholder = True
            disabled_by_preset = False
            active = False
            
            def __init__(self, *args, **kwargs):
                from module_card import ModuleCard
                self.card = ModuleCard(self.name)
                self.card.set_status("Módulo no disponible")
                self.card.mark_as_placeholder()
                
            def process(self, block, sr): 
                pass
                
        return Placeholder, False

# psutil para métricas del sistema
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# Energy Detector
try:
    from energy_detector import EnergyDetector
    ENERGY_AVAILABLE = True
except:
    ENERGY_AVAILABLE = False
    class EnergyDetector:
        def __init__(self, *a, **k):
            self.current_energy, self.energy_score = 0, 0.5
            self.ENERGY_NAMES = ["BAJA", "MEDIA", "ALTA"]
        def process(self, block, sr): pass
        def get_energy_level(self): return self.current_energy
        def get_energy_name(self): return self.ENERGY_NAMES[self.current_energy]
        def get_energy_score(self): return self.energy_score
        def reset_calibration(self): pass

# Avolites
try:
    from avolites_config import AvolitesController
    AVOLITES_AVAILABLE = True
except:
    AVOLITES_AVAILABLE = False
    class AvolitesController:
        def __init__(self, auto_connect=False):
            self.is_connected = False
            self.config_manager = type('obj', (object,), {'config': {'console_ip': '10.0.0.1', 'console_port': 4430, 'local_ip': '10.0.0.10'}})()
        def connect(self): return False
        def fire_cue(self, *a, **k): return False
        def kill_all_cues(self): return False
        def get_status(self): return {"connected": False, "console_ip": "N/A"}
        def set_local_interface(self, ip): pass
        def set_console_ip(self, ip): pass
        def set_console_port(self, port): pass
        def set_transport(self, transport): pass
        def reconnect(self): pass
        def stop(self): pass
        def get_last_error(self): return None

# FastAPI Server
try:
    from api.main import start_api_server
    from services.app_state import AppState
    API_AVAILABLE = True
except Exception as e:
    API_AVAILABLE = False
    print(f"[MAIN] API no disponible: {e}")

# Vision System (Phase 6 - REFACTOR A2: 3 tabs independientes)
try:
    from core_vision import VisionManager
    from ui.vision_haze_tab import VisionHazeTab
    from ui.vision_dj_tab import VisionDJTab
    from ui.vision_artist_tab import VisionArtistTab
    from ui.vision_config_widget import VisionConfigWidget
    VISION_AVAILABLE = True
except Exception as e:
    VISION_AVAILABLE = False
    print(f"[MAIN] Vision System no disponible: {e}")
    VisionManager = None

# Calendar Tab - Governance Panel
try:
    from ui.calendar_tab import CalendarTab
    CALENDAR_TAB_AVAILABLE = True
except Exception as e:
    CALENDAR_TAB_AVAILABLE = False
    print(f"[MAIN] Calendar Tab no disponible: {e}")
    CalendarTab = None

# Calendar Manager - Passive Schedule Resolution
try:
    from core.calendar import CalendarManager, set_calendar_manager
    CALENDAR_MANAGER_AVAILABLE = True
    print("[MAIN] OK: CalendarManager import")
except Exception as e:
    CALENDAR_MANAGER_AVAILABLE = False
    print(f"[MAIN] FAIL: CalendarManager no disponible: {e}")
    CalendarManager = None
    set_calendar_manager = None

# System Bridge - Calendar → System governance
try:
    from core.system_bridge import get_system_bridge
    SYSTEM_BRIDGE_AVAILABLE = True
except Exception as e:
    SYSTEM_BRIDGE_AVAILABLE = False
    print(f"[MAIN] SystemBridge no disponible: {e}")
    get_system_bridge = None

# Health Tab (consolidated)
try:
    from ui.health_tab import HealthMonitorWidget as _HealthMonitorWidgetNew
    HEALTH_TAB_AVAILABLE = True
except Exception as e:
    HEALTH_TAB_AVAILABLE = False
    _HealthMonitorWidgetNew = None
    print(f"[MAIN] Health Tab no disponible: {e}")

# Cues Monitor Tab

# TAP Tempo / AutoClock v9 + KickPulseDetector V13
try:
    from tempo.auto_clock import AutoClock
    from tempo.tap_bridge import TapBridge
    from tempo.kick_detector import KickPulseDetector
    from tempo.tap_sender import TapTempoSender
    from clock_widget import ClockWidget
    TAP_TEMPO_AVAILABLE = True
except Exception as e:
    TAP_TEMPO_AVAILABLE = False
    print(f"[MAIN] TAP Tempo no disponible: {e}")
    AutoClock = None
    TapBridge = None
    KickPulseDetector = None
    TapTempoSender = None
    ClockWidget = None
try:
    from cues_monitor_tab import create_cues_monitor_tab
    CUES_AVAILABLE = True
except:
    CUES_AVAILABLE = False
    create_cues_monitor_tab = None

# CueEngine
try:
    from cue_engine import create_cue_engine
    from cue_engine_debug_widget import create_cue_engine_debug_widget
    CUE_ENGINE_MODULAR_AVAILABLE = True
except:
    CUE_ENGINE_MODULAR_AVAILABLE = False

# Network Utils
try:
    from network_utils import list_interfaces
    NETWORK_UTILS_AVAILABLE = True
except:
    NETWORK_UTILS_AVAILABLE = False
    def list_interfaces():
        return [("Auto", "0.0.0.0", "00:00:00:00:00:00", True)]

# State Monitor
try:
    from state_manager import StateMonitorWidget
    STATE_WIDGET_AVAILABLE = True
except:
    STATE_WIDGET_AVAILABLE = False
    class StateMonitorWidget(QWidget):
        def __init__(self, state_manager):
            super().__init__()
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("StateMonitor: No disponible"))
        def update_display(self): pass

# Analizadores
NoHits, _ = safe_import("no_hits", "NoHits")
DeepListener, _ = safe_import("deep_listener", "DeepListener")
SoftPeaks, _ = safe_import("soft_peaks", "SoftPeaks")
RampDown, _ = safe_import("ramp_down", "RampDown")
HighSilence, _ = safe_import("high_silence", "HighSilence")
BreakSpotter, _ = safe_import("break_spotter", "BreakSpotter")
LoopDissolver, _ = safe_import("loop_dissolver", "LoopDissolver")
DynamicFlattener, _ = safe_import("dynamic_flattener", "DynamicFlattener")
TextureCleaner, _ = safe_import("texture_cleaner", "TextureCleaner")
AmbientConfirmator, _ = safe_import("ambient_confirmator", "AmbientConfirmator")
YesHits, _ = safe_import("yes_hits", "YesHits")
AccentCatcher, _ = safe_import("accent_catcher", "AccentCatcher")
GrooveKeeper, _ = safe_import("groove_keeper", "GrooveKeeper")
PatternLock, _ = safe_import("pattern_lock", "PatternLock")
CadenceSpotter, _ = safe_import("cadence_spotter", "CadenceSpotter")
FlowMonitor, _ = safe_import("flow_monitor", "FlowMonitor")
DynamicPulse, _ = safe_import("dynamic_pulse", "DynamicPulse")
# PulseFinder V10: Usar wrapper profesional con .value/.score/.detected
try:
    from analyzers.pulse_finder_wrapper import PulseFinderAnalyzer
    PULSE_FINDER_WRAPPER_OK = True
except ImportError:
    PulseFinderAnalyzer = None
    PULSE_FINDER_WRAPPER_OK = False
RhythmHighlighter, _ = safe_import("rhythm_highlighter", "RhythmHighlighter")
SnareRoll, _ = safe_import("snare_roll", "SnareRoll")
HiRoll, _ = safe_import("hi_roll", "HiRoll")
BurstSharpness, _ = safe_import("burst_sharpness", "BurstSharpness")
BurstContinuity, _ = safe_import("burst_continuity", "BurstContinuity")
EnergyCliff, _ = safe_import("energy_cliff", "EnergyCliff")
WidebandBlackout, _ = safe_import("wideband_blackout", "WidebandBlackout")
RhythmVoid, _ = safe_import("rhythm_void", "RhythmVoid")

# Brake real
try:
    from analyzers.brake import BrakeAnalyzer
    BRAKE_ANALYZER_AVAILABLE = True
    print("[MAIN] BrakeAnalyzer REAL importado exitosamente")
except Exception as e:
    BRAKE_ANALYZER_AVAILABLE = False
    print(f"[MAIN] No se pudo importar BrakeAnalyzer real: {e}")

def dbfs(rms):
    if rms <= 1e-12: return -80.0
    return max(-80.0, min(0.0, 20.0 * math.log10(rms)))

def sanitize_audio(x):
    if x is None: return None
    arr = np.asarray(x)
    if arr.size == 0: return None
    if arr.ndim > 1: arr = arr.mean(axis=1)
    arr = arr.astype(np.float32, copy=False)
    if not np.isfinite(arr).all():
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
    np.clip(arr, -1.0, 1.0, out=arr)
    return arr

def make_grid(modules, cols=3):
    gridw = QWidget()
    grid = QGridLayout(gridw)
    grid.setContentsMargins(10,10,10,10)
    grid.setSpacing(12)
    for i in range((len(modules) + cols - 1) // cols):
        grid.setRowMinimumHeight(i, 280)
    for c in range(cols):
        grid.setColumnStretch(c, 1)
    for i, m in enumerate(modules):
        row, col = divmod(i, cols)
        grid.addWidget(m.card, row, col)
        m.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        m.card.setMinimumHeight(260)
    return gridw

def mark_analyzer_flags(analyzer, is_placeholder_flag):
    """Marca flags en analizador recién instanciado"""
    analyzer.is_placeholder = is_placeholder_flag
    analyzer.disabled_by_preset = False
    analyzer.active = not is_placeholder_flag
    return analyzer

class EnergyMonitorWidget(QWidget):
    def __init__(self, energy_detector):
        super().__init__()
        self.energy_detector = energy_detector
        self._last_name = None
        self._last_color = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        title = QLabel("ENERGY DETECTOR")
        title.setStyleSheet("font-weight:700; color:#f0f0f0; font-size:12px;")
        layout.addWidget(title)
        self.energy_main = QLabel("MEDIA")
        self.energy_main.setAlignment(Qt.AlignCenter)
        self.energy_main.setStyleSheet(
            "color:#FF9800; font-weight:700; font-size:18px; "
            "background:#0a0a0f; border:1px solid #2e2e38; border-radius:12px; padding:8px;"
        )
        layout.addWidget(self.energy_main)
        info_layout = QHBoxLayout()
        score_lbl = QLabel("Score:")
        score_lbl.setStyleSheet("QLabel{font-size:11px;}")
        info_layout.addWidget(score_lbl)
        self.score_label = QLabel("0.5")
        self.score_label.setStyleSheet("color:#a6a6a6; font-weight:700; font-size:11px;")
        info_layout.addWidget(self.score_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)
        self.btn_reset = QPushButton("Reset Calibración")
        self.btn_reset.setStyleSheet(
            "QPushButton{background:#2e2e38; border:1px solid #2e2e38; border-radius:10px; "
            "padding:6px; color:#f0f0f0; font-size:11px;} QPushButton:hover{background:#2e2e38;}"
        )
        self.btn_reset.clicked.connect(self.reset_calibration)
        layout.addWidget(self.btn_reset)
        layout.addStretch()
        self.setStyleSheet(
            "QWidget{background:#141418; border:1px solid #2e2e38; border-radius:12px;} "
            "QLabel{color:#f0f0f0;}"
        )

    def update_display(self):
        try:
            energy_name = self.energy_detector.get_energy_name()
            if energy_name != self._last_name:
                self._last_name = energy_name
                self.energy_main.setText(energy_name)
            colors = {"BAJA": "#4CAF50", "MEDIA": "#FF9800", "ALTA": "#F44336"}
            color = colors.get(energy_name, "#888888")
            if color != self._last_color:
                self._last_color = color
                self.energy_main.setStyleSheet(
                    f"color:{color}; font-weight:700; font-size:18px; "
                    "background:#0a0a0f; border:1px solid #2e2e38; border-radius:12px; padding:8px;"
                )
            score = self.energy_detector.get_energy_score()
            self.score_label.setText(f"{score:.3f}")
        except: pass

    def reset_calibration(self):
        try:
            self.energy_detector.reset_calibration()
        except: pass

# HealthMonitorWidget — use consolidated version from ui/health_tab,
# fallback to minimal placeholder if import failed.
if HEALTH_TAB_AVAILABLE and _HealthMonitorWidgetNew is not None:
    HealthMonitorWidget = _HealthMonitorWidgetNew
else:
    class HealthMonitorWidget(QWidget):
        """Minimal fallback when ui.health_tab is not available."""
        def __init__(self, main_window):
            super().__init__()
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Health tab unavailable — check ui/health_tab.py"))
        def update_all(self, **kwargs):
            pass
        def record_error(self, source, message):
            pass

_GENERIC_DEVICE_NAMES = {"default", "hw:", "plughw:", "pulse", "sysdefault", "dmix"}

def wait_for_audio_device(keywords=None, timeout=15.0, poll_interval=1.0):
    """
    Wait for a specific USB audio device to appear in ALSA/PortAudio.

    Polls sd.query_devices() every poll_interval seconds looking for an input
    device whose name contains any of the given keywords.
    Generic names ("default", "hw:", "pulse", etc.) are always excluded.

    Args:
        keywords: list of substrings to match (e.g. ["PS22", "Maono"]).
                  Generic entries are silently stripped.
        timeout: max seconds to wait (default 15)
        poll_interval: seconds between polls (default 1)

    Returns:
        (device_index, device_name) if found, (None, None) if timeout
    """
    if not keywords:
        keywords = ["PS22", "Maono"]
    # Strip generic keywords that would match onboard/system devices
    keywords = [k for k in keywords if k.lower() not in _GENERIC_DEVICE_NAMES]
    if not keywords:
        keywords = ["PS22", "Maono"]
    keywords_lower = [k.lower() for k in keywords]
    print(f"[AUDIO] Waiting for Maono PS22 (keywords={keywords}, timeout={timeout}s)...")

    # Force PortAudio to rebuild its device list from ALSA.
    # Without this, PortAudio caches the device list from process init time
    # and never sees USB devices that appeared after Python started.
    try:
        sd._terminate()
        sd._initialize()
        print("[AUDIO] PortAudio re-initialized (cache cleared)")
    except Exception as e:
        print(f"[AUDIO] PortAudio re-init warning: {e}")

    t0 = time.time()
    attempt = 0
    while time.time() - t0 < timeout:
        attempt += 1
        try:
            # Re-scan ALSA on every poll cycle so newly-appeared USB devices
            # are visible to sd.query_devices().
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d.get('max_input_channels', 0) <= 0:
                    continue
                name = d.get('name', '')
                name_lower = name.lower()
                if any(kw in name_lower for kw in keywords_lower):
                    elapsed = time.time() - t0
                    print(f"[AUDIO] Device detected: #{i} '{name}' (attempt {attempt}, {elapsed:.1f}s)")
                    return i, name
        except Exception as e:
            print(f"[AUDIO] Error querying devices (attempt {attempt}): {e}")
        if time.time() - t0 + poll_interval < timeout:
            time.sleep(poll_interval)
        else:
            break
    print(f"[AUDIO] WARNING: Maono PS22 not found after {timeout}s ({attempt} attempts)")
    return None, None


# ---------------------------------------------------------------------------
# Sidebar Navigation Widget
# ---------------------------------------------------------------------------
class SidebarNav(QWidget):
    """Left sidebar navigation that drives a QStackedWidget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        try:
            self.setFixedWidth(SIDEBAR_WIDTH)
        except NameError:
            self.setFixedWidth(170)
        self._buttons: list[QPushButton] = []
        self._stack: QStackedWidget | None = None
        # Maps button position → stack widget index
        self._btn_to_stack: list[int] = []
        # Maps stack widget index → button position
        self._stack_to_btn: dict[int, int] = {}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)

    # -- public API ----------------------------------------------------------
    def set_stack(self, stack: QStackedWidget):
        self._stack = stack

    def add_section(self, title: str):
        lbl = QLabel(title)
        lbl.setProperty("role", "section")
        self._layout.addWidget(lbl)

    def add_item(self, label: str, widget: QWidget):
        stack_idx = self._stack.indexOf(widget) if self._stack else -1
        btn_idx = len(self._buttons)
        btn = QPushButton(label)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda checked, bi=btn_idx: self._activate(bi))
        self._layout.addWidget(btn)
        self._buttons.append(btn)
        self._btn_to_stack.append(stack_idx)
        if stack_idx >= 0:
            self._stack_to_btn[stack_idx] = btn_idx

    def finish(self):
        self._layout.addStretch()
        if self._buttons:
            self._activate(0)

    # -- internal ------------------------------------------------------------
    def _activate(self, btn_index: int):
        """Switch view by button index (not stack index)."""
        if self._stack is None or btn_index < 0 or btn_index >= len(self._buttons):
            return
        stack_idx = self._btn_to_stack[btn_index]
        if stack_idx >= 0:
            self._stack.setCurrentIndex(stack_idx)
        for b in self._buttons:
            b.setProperty("active", "false")
            b.style().unpolish(b)
            b.style().polish(b)
        self._buttons[btn_index].setProperty("active", "true")
        self._buttons[btn_index].style().unpolish(self._buttons[btn_index])
        self._buttons[btn_index].style().polish(self._buttons[btn_index])

    def select_widget(self, widget: QWidget):
        """Switch view by widget reference."""
        if self._stack is None:
            return
        stack_idx = self._stack.indexOf(widget)
        btn_idx = self._stack_to_btn.get(stack_idx, -1)
        if btn_idx >= 0:
            self._activate(btn_idx)

    def sync_highlight(self, stack_idx: int):
        """Update button highlight when stack changes externally."""
        btn_idx = self._stack_to_btn.get(stack_idx, -1)
        if btn_idx < 0:
            return
        for b in self._buttons:
            b.setProperty("active", "false")
            b.style().unpolish(b)
            b.style().polish(b)
        self._buttons[btn_idx].setProperty("active", "true")
        self._buttons[btn_idx].style().unpolish(self._buttons[btn_idx])
        self._buttons[btn_idx].style().polish(self._buttons[btn_idx])


# ---------------------------------------------------------------------------
# GlassCard — WEB-style .g card wrapper for workspace modules
# ---------------------------------------------------------------------------
class GlassCard(QFrame):
    """Card container matching WEB .g glass card.

    Wraps an existing widget with a titled card frame so the workspace
    feels like the web Control Room without modifying the inner widget.
    """

    def __init__(self, title: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("WorkspaceCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        if title:
            lbl = QLabel(title)
            lbl.setProperty("role", "card-title")
            lay.addWidget(lbl)
        self._content_layout = lay

    def set_content(self, widget: QWidget):
        widget.setContentsMargins(
            NEON_CARD_PADDING, 0, NEON_CARD_PADDING, NEON_CARD_PADDING
        )
        self._content_layout.addWidget(widget)

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)


try:
    NEON_CARD_PADDING = CARD_PADDING
except NameError:
    NEON_CARD_PADDING = 24


class Main(QMainWindow):
    def __init__(self):
        global API_AVAILABLE
        super().__init__()
        self.setWindowTitle("911 Fiesta - Sistema Modular v4.2 + BRAKE ANALYZER REAL + RED PANEL + HEALTH")

        # Kiosk mode: frameless (no title bar, no window controls)
        self.setWindowFlags(Qt.FramelessWindowHint)

        # Preset path - SINGLE PROFILE (source of truth)
        # ABSOLUTE PATH anchored to main.py directory (Windows CWD fix)
        self.preset_path = self._get_preset_abs_path()
        print(f"[INIT] preset_path={self.preset_path} cwd={os.getcwd()}")

        # Health monitoring
        self.health_enabled = True
        self.health_sample_s = 2.0
        self._loop_lat_samples = collections.deque(maxlen=30)
        self._loop_probe = None
        self._loop_probe_interval_s = 0.5
        self._loop_probe_last = None
        self._health_timer = None

        # Boot flags
        self._boot_ready = False
        self._pending_console_baseline = False
        self._pending_initial_apply = False
        self._pending_apply_in_progress = False  # Lock to prevent double-firing
        self._boot_calendar_result = None  # Stored for re-apply on READY
        self._first_audio_buffer_logged = False  # Log only first buffer

        # NIC configuration
        self.local_ip_effective = None  # Currently bound local IP

        self.energy_detector = EnergyDetector()
        self.avolites = AvolitesController(auto_connect=False)
        # ✅ SPRINT 1: Pasar energy_detector al StateManager
        self.state_manager = StateManager(
            energy_detector=self.energy_detector,
            min_hold_seconds=2.0,
            hysteresis_margin=0.6,
            cooldown_seconds=0.5
        )

        # Music Structure Engine (MSE)
        self.music_structure_engine = None
        if _MSE_AVAILABLE and MusicStructureEngine is not None:
            try:
                self.music_structure_engine = MusicStructureEngine()
            except Exception as e:
                print(f"[MSE] init failed: {e}")
                self.music_structure_engine = None

        if CUE_ENGINE_MODULAR_AVAILABLE:
            try:
                self.cue_engine = create_cue_engine(
                    avolites_controller=self.avolites,
                    state_manager=self.state_manager,
                    energy_detector=self.energy_detector
                )
                self.cue_engine.start_auto_update()
            except:
                self.cue_engine = None
        else:
            self.cue_engine = None

        # Vision System (Phase 6) - PRO con integración CueEngine
        if VISION_AVAILABLE:
            try:
                # Pasar cue_engine a VisionManager para integración completa
                self.vision_manager = VisionManager(cue_engine=self.cue_engine if hasattr(self, 'cue_engine') else None)
                print("[MAIN] VisionManager PRO inicializado correctamente")

                # Si no había cue_engine al inicio, conectarlo después
                if hasattr(self, 'cue_engine') and self.cue_engine and hasattr(self.vision_manager, '_connect_cue_engine'):
                    self.vision_manager._connect_cue_engine(self.cue_engine)
                    print("[MAIN] CueEngine conectado a VisionManager")
            except Exception as e:
                self.vision_manager = None
                print(f"[MAIN] Error inicializando VisionManager: {e}")
        else:
            self.vision_manager = None

        # Calendar Manager - Passive Schedule Resolution
        # Obtiene SystemBridge primero para inyectarlo en CalendarManager
        print(f"[MAIN] CalendarManager disponible: {CALENDAR_MANAGER_AVAILABLE}")
        if CALENDAR_MANAGER_AVAILABLE:
            try:
                # Obtener SystemBridge (singleton) para inyectar
                initial_bridge = get_system_bridge() if SYSTEM_BRIDGE_AVAILABLE and get_system_bridge else None
                print(f"[MAIN] Creando CalendarManager con bridge={initial_bridge is not None}")
                self.calendar_manager = CalendarManager(system_bridge=initial_bridge)
                print("[MAIN] OK: CalendarManager instanciado")
                # Registrar instancia global
                if set_calendar_manager:
                    set_calendar_manager(self.calendar_manager)
                    print("[MAIN] OK: CalendarManager registrado como singleton")
                print("[MAIN] CalendarManager inicializado con SystemBridge inyectado")
            except Exception as e:
                self.calendar_manager = None
                print(f"[MAIN] FAIL: Error inicializando CalendarManager: {e}")
                import traceback
                traceback.print_exc()
        else:
            self.calendar_manager = None
            print("[MAIN] SKIP: CalendarManager no disponible - saltando inicializacion")

        # System Bridge - Calendar → System governance
        # Punto ÚNICO de conexión entre calendario y sistema
        self.system_bridge = None
        self._audio_processing_enabled = True  # Flag para bypass de audio analysis

        if SYSTEM_BRIDGE_AVAILABLE and get_system_bridge:
            try:
                self.system_bridge = get_system_bridge()

                # Conectar CueEngine
                if hasattr(self, 'cue_engine') and self.cue_engine:
                    self.system_bridge.connect_cue_engine(self.cue_engine)

                # Conectar VisionManager
                if hasattr(self, 'vision_manager') and self.vision_manager:
                    self.system_bridge.connect_vision_manager(self.vision_manager)

                # Conectar audio processor callback
                self.system_bridge.connect_audio_processor(self._set_audio_processing_enabled)

                # CalendarManager ya tiene SystemBridge inyectado en constructor
                # y llama apply_calendar_state() directamente cuando cambia el modo
                if self.calendar_manager:
                    print("[MAIN] SystemBridge conectado - CalendarManager gobierna vía apply_calendar_state()")
                else:
                    print("[MAIN] SystemBridge inicializado sin CalendarManager")

            except Exception as e:
                self.system_bridge = None
                print(f"[MAIN] Error inicializando SystemBridge: {e}")
        else:
            print("[MAIN] SystemBridge no disponible - sistema sin gobierno de calendario")

        # TAP Tempo / AutoClock v9 + KickPulseDetector V13 + TapBridge v3
        if TAP_TEMPO_AVAILABLE:
            try:
                self.auto_clock = AutoClock(interval_ms=750, correction_period=3.0)
                # V13: Thread-safe kick detector with MAD threshold
                self.kick_detector = KickPulseDetector(
                    debounce_ms=150.0,
                    threshold_k=2.5,
                    lp_cutoff_hz=150.0
                ) if KickPulseDetector else None
                # TapBridge v3: pasa auto_clock para gating por lock state
                self.tap_bridge = TapBridge(self.avolites, self.auto_clock)
                # TapTempoSender v3: transport clock — keeps Titan BPM synced
                self.tap_sender = TapTempoSender() if TapTempoSender else None
                # V11.1: Edge detection state for hit registration
                self._prev_is_golpe = False
                # FIX 6: DEBUG_TEMPO=1 instrumentation
                self._debug_tempo = os.environ.get("DEBUG_TEMPO", "0") == "1"
                self._debug_tempo_last = 0.0
                self._debug_tempo_kicks = 0
                print(f"[MAIN] AutoClock v13 + KickDetector V18 + TapBridge v3 + TapSender v3 (DEBUG_TEMPO={'ON' if self._debug_tempo else 'off'})")
            except Exception as e:
                self.auto_clock = None
                self.kick_detector = None
                self.tap_bridge = None
                self.tap_sender = None
                self._prev_is_golpe = False
                self._debug_tempo = False
                self._debug_tempo_last = 0.0
                self._debug_tempo_kicks = 0
                print(f"[MAIN] Error inicializando AutoClock/KickDetector/TapBridge: {e}")
        else:
            self.auto_clock = None
            self.kick_detector = None
            self.tap_bridge = None
            self._prev_is_golpe = False
            self._debug_tempo = False
            self._debug_tempo_last = 0.0
            self._debug_tempo_kicks = 0

        # =======================================================================
        # V12: Motor Real vs Legacy Analyzer Organization
        # =======================================================================
        # Motor Real: Active analyzers that drive the state machine
        # Legacy: Additional analyzers for monitoring/experimentation
        # =======================================================================

        # BAJADA - Motor Real (5 active analyzers)
        self.modules_bajada = [
            mark_analyzer_flags(NoHits(), getattr(NoHits, 'is_placeholder', False)),
            mark_analyzer_flags(DeepListener(), getattr(DeepListener, 'is_placeholder', False)),
            mark_analyzer_flags(SoftPeaks(), getattr(SoftPeaks, 'is_placeholder', False)),
            mark_analyzer_flags(RampDown(), getattr(RampDown, 'is_placeholder', False)),
            mark_analyzer_flags(BreakSpotter(), getattr(BreakSpotter, 'is_placeholder', False)),
        ]

        # BAJADA - Legacy (5 additional analyzers)
        self.modules_bajada_legacy = [
            mark_analyzer_flags(HighSilence(), getattr(HighSilence, 'is_placeholder', False)),
            mark_analyzer_flags(LoopDissolver(), getattr(LoopDissolver, 'is_placeholder', False)),
            mark_analyzer_flags(DynamicFlattener(), getattr(DynamicFlattener, 'is_placeholder', False)),
            mark_analyzer_flags(TextureCleaner(), getattr(TextureCleaner, 'is_placeholder', False)),
            mark_analyzer_flags(AmbientConfirmator(), getattr(AmbientConfirmator, 'is_placeholder', False))
        ]

        # BASE_GOLPE - Motor Real (10 active analyzers - V11 pipeline)
        self.modules_golpe = [
            mark_analyzer_flags(YesHits(), getattr(YesHits, 'is_placeholder', False)),
            mark_analyzer_flags(AccentCatcher(), getattr(AccentCatcher, 'is_placeholder', False)),
            mark_analyzer_flags(GrooveKeeper(), getattr(GrooveKeeper, 'is_placeholder', False)),
            mark_analyzer_flags(PatternLock(), getattr(PatternLock, 'is_placeholder', False)),
            mark_analyzer_flags(CadenceSpotter(), getattr(CadenceSpotter, 'is_placeholder', False)),
            mark_analyzer_flags(FlowMonitor(), getattr(FlowMonitor, 'is_placeholder', False)),
            mark_analyzer_flags(DynamicPulse(), getattr(DynamicPulse, 'is_placeholder', False)),
            # V10: PulseFinder wrapper con .value/.score/.detected para UI
            mark_analyzer_flags(PulseFinderAnalyzer(), False) if PULSE_FINDER_WRAPPER_OK else None,
            mark_analyzer_flags(RhythmHighlighter(), getattr(RhythmHighlighter, 'is_placeholder', False)),
            # BurstSharpness para detectar explosiones
            mark_analyzer_flags(BurstSharpness(), getattr(BurstSharpness, 'is_placeholder', False)),
        ]
        # V10: Filtrar Nones si PulseFinderAnalyzer no está disponible
        self.modules_golpe = [m for m in self.modules_golpe if m is not None]

        # BASE_GOLPE - Legacy (empty, all 10 are active in V11 pipeline)
        self.modules_golpe_legacy = []

        # ATAQUE - Motor Real (3 active analyzers)
        self.modules_ataque = [
            mark_analyzer_flags(SnareRoll(), getattr(SnareRoll, 'is_placeholder', False)),
            mark_analyzer_flags(HiRoll(), getattr(HiRoll, 'is_placeholder', False)),
            mark_analyzer_flags(BurstSharpness(), getattr(BurstSharpness, 'is_placeholder', False)),
        ]

        # ATAQUE - Legacy (1 additional analyzer)
        self.modules_ataque_legacy = [
            mark_analyzer_flags(BurstContinuity(), getattr(BurstContinuity, 'is_placeholder', False))
        ]

        # BRAKE - Motor Real (4 active analyzers including BrakeAnalyzer REAL)
        self.modules_brake = [
            mark_analyzer_flags(EnergyCliff(), getattr(EnergyCliff, 'is_placeholder', False)),
            mark_analyzer_flags(WidebandBlackout(), getattr(WidebandBlackout, 'is_placeholder', False)),
            mark_analyzer_flags(RhythmVoid(), getattr(RhythmVoid, 'is_placeholder', False))
        ]

        # Instanciar BrakeAnalyzer REAL sin wrappers (ya expone .card y .name)
        self.brake_analyzer = BrakeAnalyzer() if BRAKE_ANALYZER_AVAILABLE else None
        if self.brake_analyzer:
            self.modules_brake.append(self.brake_analyzer)
            print("[MAIN] BrakeAnalyzer REAL instanciado correctamente")

        # BRAKE - Legacy (empty, all are active)
        self.modules_brake_legacy = []

        # V12: Log analyzer organization
        print(f"[MAIN] V12 Motor Real: Bajada={len(self.modules_bajada)}, Golpe={len(self.modules_golpe)}, Ataque={len(self.modules_ataque)}, Brake={len(self.modules_brake)}")
        print(f"[MAIN] V12 Legacy: Bajada={len(self.modules_bajada_legacy)}, Golpe={len(self.modules_golpe_legacy)}, Ataque={len(self.modules_ataque_legacy)}, Brake={len(self.modules_brake_legacy)}")

        self._log_analyzer_stats()

        # V10: Conectar modules_golpe a CueEngine para PulseFinder flags
        if self.cue_engine and hasattr(self.cue_engine, 'connect_modules_golpe'):
            self.cue_engine.connect_modules_golpe(self.modules_golpe)

        self._setup_ui()

        # Start Vision System after UI is ready
        if self.vision_manager:
            try:
                self.vision_manager.start()
                print("[MAIN] VisionManager iniciado correctamente")
            except Exception as e:
                print(f"[MAIN] Error iniciando VisionManager: {e}")

        self.engine = None
        self._active_tab_name = "bajada"

        self.CADENCE = {
            "vu": 50,
            "scope": 300,
            "modules": 33,
            "energy": 150,
            "status": 100,
            "cues": 400
        }
        self._acc = {k: 0.0 for k in self.CADENCE.keys()}
        self._clock = QElapsedTimer()
        self._clock.start()

        self.t_frame = QTimer(self)
        self.t_frame.setInterval(33)
        self.t_frame.timeout.connect(self._frame_tick)

        # Vision System update timer
        if self.vision_manager and self.haze_bar:
            self.t_vision = QTimer(self)
            self.t_vision.setInterval(200)
            self.t_vision.timeout.connect(self._update_vision_ui)
            self.t_vision.start()
        else:
            self.t_vision = None

        self._vu_last_text = None
        self._vu_last_val = None

        # Cargar preset en startup
        self._load_net_panel_from_preset()

        # Inicializar API FastAPI
        if API_AVAILABLE:
            try:
                # Crear dict de modules_by_state para AppState
                modules_by_state = {
                    "BAJADA": self.modules_bajada,
                    "BASE_GOLPE": self.modules_golpe,
                    "ATAQUE": self.modules_ataque,
                    "BRAKE": self.modules_brake
                }

                # Inicializar AppState con referencias a managers
                AppState.initialize(
                    state_manager=self.state_manager,
                    audio_engine=self.engine,
                    cue_engine=self.cue_engine,
                    avolites=self.avolites,
                    vision_manager=self.vision_manager if hasattr(self, 'vision_manager') else None,
                    modules_by_state=modules_by_state,
                    energy_detector=self.energy_detector,
                    audio_monitor=self.audio_monitor if hasattr(self, 'audio_monitor') else None,
                    auto_clock=self.auto_clock if hasattr(self, 'auto_clock') else None
                )
                print("[MAIN] AppState initialized")

                # Iniciar HTTP Snapshot Server (bridge CORE → WEB)
                try:
                    from core.http_snapshot import start_snapshot_server
                    self.snapshot_server = start_snapshot_server(
                        state_manager=self.state_manager,
                        audio_engine=self.engine,
                        avolites=self.avolites,
                        cue_engine=self.cue_engine,
                        vision_manager=self.vision_manager if hasattr(self, 'vision_manager') else None,
                        calendar_manager=self.calendar_manager if hasattr(self, 'calendar_manager') else None,
                        energy_detector=self.energy_detector,
                        audio_monitor=self.audio_monitor if hasattr(self, 'audio_monitor') else None,
                        bpm_detector=self.auto_clock if hasattr(self, 'auto_clock') else None,
                        port=8010
                    )
                    print("[MAIN] HTTP Snapshot Server started at http://127.0.0.1:8010")
                except Exception as e:
                    print(f"[MAIN] Error starting HTTP Snapshot Server: {e}")
            except Exception as e:
                print(f"[MAIN] Error initializing AppState: {e}")
                API_AVAILABLE = False

        # Iniciar API server en thread daemon
        if API_AVAILABLE:
            try:
                import threading
                self.api_thread = threading.Thread(
                    target=start_api_server,
                    args=("0.0.0.0", 8000),
                    daemon=True,
                    name="APIServerThread"
                )
                self.api_thread.start()
                print("[MAIN] API server started at http://localhost:8000")
                print("[MAIN] API docs: http://localhost:8000/docs")
            except Exception as e:
                print(f"[MAIN] Error starting API server: {e}")

        # Iniciar timers de health
        self._start_loop_probe()
        self._start_health_timer()

        # =====================================================================
        # V13 BOOT SEQUENCE - AUTONOMOUS PROFILE + DETERMINISTIC BOOTSTRAP
        # =====================================================================
        # PHASE 1 (100ms): _startup_auto_apply
        #   - Load profile from preset_path
        #   - Apply + auto-connect: Audio, NIC, Avolites
        #
        # PHASE 2 (500ms): _execute_bootstrap
        #   - CueEngine reset
        #   - Console baseline (KILL ALL + C41)
        #   - Calendar bootstrap
        #   - Vision sync
        #   - Initial cues
        #
        # ORDER: load_profile → apply_profile → connections → cues
        # =====================================================================
        QTimer.singleShot(100, self._startup_auto_apply)
        QTimer.singleShot(500, self._execute_bootstrap)

    def _execute_bootstrap(self):
        """
        Bootstrap determinístico al arranque.

        Secuencia:
        1. CueEngine silent_reset()
        2. Console baseline: KILL ALL + C41 (si Titan READY, sino pending)
        3. Calendar bootstrap_now() - resolve + apply forzado
        4. Vision sync_runtime_to_actions() - sync a actions
        5. Initial cues (CLIMA o BAJADA) - SOLO si Titan READY, sino pending
        6. Marcar _boot_ready = True

        Si Titan NOT READY: guarda calendar_result y marca pending_initial_apply.
        Cuando Titan pasa a READY (en health tick): re-aplica baseline + initial cues.
        """
        print("[BOOT] ========== BOOTSTRAP START ==========")

        titan_ready = False

        try:
            # === PASO 1: CueEngine silent_reset ===
            print("[BOOT] PASO 1: CueEngine silent_reset")
            if hasattr(self, 'cue_engine') and self.cue_engine:
                if hasattr(self.cue_engine, 'silent_reset'):
                    self.cue_engine.silent_reset()

            # === PASO 2: Check Titan READY + Console baseline ===
            print("[BOOT] PASO 2: Console baseline (KILL ALL + C41)")
            if hasattr(self, 'avolites') and self.avolites:
                try:
                    titan_ready = self.avolites.is_ready() if hasattr(self.avolites, 'is_ready') else False

                    if titan_ready:
                        print("[BOOT] TITAN ready")
                        self._apply_console_baseline()
                    else:
                        self._pending_console_baseline = True
                        print("[BOOT] TITAN not_ready → baseline PENDING")
                except Exception as e:
                    self._pending_console_baseline = True
                    print(f"[BOOT] Console baseline error: {e} → PENDING")

            # === PASO 3: Calendar bootstrap ===
            print("[BOOT] PASO 3: Calendar bootstrap_now()")
            calendar_result = {"mode": "apagado", "actions": [], "day_key": "unknown"}
            if hasattr(self, 'calendar_manager') and self.calendar_manager:
                if hasattr(self.calendar_manager, 'bootstrap_now'):
                    calendar_result = self.calendar_manager.bootstrap_now(force=True)

            # Guardar para re-apply en READY
            self._boot_calendar_result = calendar_result
            mode = calendar_result.get("mode", "unknown")
            actions = calendar_result.get("actions", [])
            day = calendar_result.get("day_key", "unknown")
            print(f"[BOOT] CALENDAR applied mode={mode} actions={actions}")

            # === PASO 4: Vision sync ===
            print("[BOOT] PASO 4: Vision sync_runtime_to_actions()")
            if hasattr(self, 'vision_manager') and self.vision_manager:
                if hasattr(self.vision_manager, 'sync_runtime_to_actions'):
                    self.vision_manager.sync_runtime_to_actions(actions, force=True)

            # === PASO 5: Initial cues (SOLO si Titan READY) ===
            print("[BOOT] PASO 5: Initial cues (CLIMA/BAJADA)")
            initial_cues_result = {"applied": False, "cues_fired": []}

            if titan_ready:
                # Titan READY → aplicar initial cues ahora
                if hasattr(self, 'cue_engine') and self.cue_engine:
                    if hasattr(self.cue_engine, 'boot_apply_initial_state'):
                        initial_cues_result = self.cue_engine.boot_apply_initial_state(calendar_result)
                        init_cues = initial_cues_result.get("cues_fired", [])
                        print(f"[BOOT] INITIAL_CUES applied cues={init_cues}")
            else:
                # Titan NOT READY → marcar pending para re-apply cuando conecte
                self._pending_initial_apply = True
                print("[BOOT] INITIAL_CUES pending (Titan not ready)")

            # === PASO 6: Marcar boot ready ===
            self._boot_ready = True

            # === Log único de resumen ===
            titan_status = "READY" if titan_ready else "NOT_READY"
            init_cues = initial_cues_result.get("cues_fired", [])
            print(f"[BOOT] READY day={day} mode={mode} actions={actions} titan={titan_status} init_cues={init_cues}")

        except Exception as e:
            print(f"[BOOT] ERROR: {e}")
            import traceback
            traceback.print_exc()

        print("[BOOT] ========== BOOTSTRAP COMPLETE ==========")

    def _apply_pending_on_ready(self):
        """
        Unified method to apply pending operations when Titan becomes READY.

        Sequence (deterministic):
        1. Log READY transition detected
        2. Apply baseline: KILL ALL → delay 300ms → C41
        3. Apply initial cues (CLIMA or BAJADA) after baseline completes
        4. Clear pending flags

        Uses lock to prevent double-firing from health tick.
        """
        # Lock to prevent double-firing
        if self._pending_apply_in_progress:
            return
        self._pending_apply_in_progress = True

        print("[BOOT] READY transition detected")

        # Start with baseline if pending
        if self._pending_console_baseline:
            self._apply_console_baseline()
        elif self._pending_initial_apply:
            # No baseline pending, go straight to initial cues
            self._apply_initial_cues_sequence()

    def _apply_console_baseline(self):
        """
        Aplica baseline de consola: KILL ALL + C41 con delay.

        KILL ALL primero, luego C41 después de 300ms para asegurar
        que la consola procesó el kill antes del baseline.
        """
        print("[BOOT] BASELINE apply start")
        try:
            # KILL ALL
            if hasattr(self.avolites, 'kill_all_cues'):
                self.avolites.kill_all_cues()

            # C41 después de 300ms
            QTimer.singleShot(300, self._fire_c41_baseline)

        except Exception as e:
            print(f"[BOOT] BASELINE KILL ALL error: {e}")
            self._pending_console_baseline = True
            self._pending_apply_in_progress = False

    def _fire_c41_baseline(self):
        """Dispara C41 (parte 2 del baseline), then chain to initial cues."""
        try:
            result = self.avolites.fire_cue(41)
            if result:
                self._pending_console_baseline = False
                print("[BOOT] BASELINE OK")

                # Chain to initial cues after 300ms if pending
                if self._pending_initial_apply:
                    QTimer.singleShot(300, self._apply_initial_cues_sequence)
                else:
                    # No initial cues pending, clear lock
                    self._pending_apply_in_progress = False
                    self._log_pending_cleared()
            else:
                # Retry later
                self._pending_console_baseline = True
                self._pending_apply_in_progress = False
                print("[BOOT] BASELINE C41 failed, will retry")
        except Exception as e:
            self._pending_console_baseline = True
            self._pending_apply_in_progress = False
            print(f"[BOOT] BASELINE C41 error: {e}")

    def _apply_initial_cues_sequence(self):
        """
        Aplica cues iniciales (CLIMA o BAJADA) después del baseline.

        Se ejecuta después de que C41 se dispara exitosamente.
        """
        if not self._pending_initial_apply:
            self._pending_apply_in_progress = False
            return

        calendar_result = self._boot_calendar_result
        if not calendar_result:
            self._pending_initial_apply = False
            self._pending_apply_in_progress = False
            return

        mode = calendar_result.get("mode", "unknown")
        print(f"[BOOT] INITIAL_CUES apply start mode={mode}")

        try:
            # Aplicar initial cues (CLIMA o BAJADA)
            if hasattr(self, 'cue_engine') and self.cue_engine:
                if hasattr(self.cue_engine, 'boot_apply_initial_state'):
                    result = self.cue_engine.boot_apply_initial_state(calendar_result)
                    init_cues = result.get("cues_fired", [])
                    print(f"[BOOT] INITIAL_CUES OK cues={init_cues}")

            self._pending_initial_apply = False
            self._pending_apply_in_progress = False
            self._log_pending_cleared()

        except Exception as e:
            print(f"[BOOT] INITIAL_CUES error: {e}")
            self._pending_apply_in_progress = False
            # Keep pending for retry

    def _log_pending_cleared(self):
        """Log when all pending operations are cleared."""
        baseline_status = "done" if not self._pending_console_baseline else "pending"
        initial_status = "done" if not self._pending_initial_apply else "pending"
        print(f"[BOOT] PENDING cleared baseline={baseline_status} initial={initial_status}")

    def _start_loop_probe(self):
        """Iniciar probe de latencia del event-loop"""
        if self._loop_probe is not None:
            self._loop_probe.stop()
        self._loop_probe_last = time.time()
        self._loop_probe = QTimer(self)
        self._loop_probe.setInterval(int(self._loop_probe_interval_s * 1000))
        self._loop_probe.timeout.connect(self._on_loop_probe)
        self._loop_probe.start()

    def _start_health_timer(self):
        """Iniciar timer de monitoreo de health"""
        if not self.health_enabled:
            return
        if self._health_timer is not None:
            self._health_timer.stop()
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(int(self.health_sample_s * 1000))
        self._health_timer.timeout.connect(self._update_health_panel)
        self._health_timer.start()

    def _on_loop_probe(self):
        """Medir drift del event-loop"""
        now = time.time()
        expected = self._loop_probe_last + self._loop_probe_interval_s
        drift = max(0.0, (now - expected) * 1000.0)  # ms
        self._loop_lat_samples.append(drift)
        self._loop_probe_last = now

    def _loop_latency_avg_ms(self):
        """Calcular latencia promedio del loop"""
        if not self._loop_lat_samples:
            return None
        return sum(self._loop_lat_samples) / len(self._loop_lat_samples)

    def _update_health_panel(self):
        """Actualizar panel Health con datos en vivo (consolidated)"""
        try:
            if not hasattr(self, 'health_widget') or not self.health_widget:
                return

            # --- Collect lightweight metrics ---
            cpu_pct = None
            cpu_load = None
            ram_pct = None
            ram_used_mb = None
            ram_total_mb = None
            if PSUTIL_AVAILABLE:
                try:
                    cpu_pct = psutil.cpu_percent(interval=None)
                    cpu_load = list(os.getloadavg()) if hasattr(os, 'getloadavg') else None
                    mem = psutil.virtual_memory()
                    ram_pct = mem.percent
                    ram_used_mb = int(mem.used / (1024 * 1024))
                    ram_total_mb = int(mem.total / (1024 * 1024))
                except Exception:
                    pass

            loop_lat = self._loop_latency_avg_ms()

            # --- Avolites status ---
            avolites_status = None
            try:
                avolites_status = self.avolites.get_status()
                # Hook: Apply pending operations when Titan becomes READY
                ready = avolites_status.get("ready", False) if avolites_status else False
                if ready and (self._pending_console_baseline or self._pending_initial_apply):
                    self._apply_pending_on_ready()
            except Exception:
                pass

            # --- Call consolidated update_all ---
            self.health_widget.update_all(
                cpu_pct=cpu_pct,
                cpu_load=cpu_load,
                ram_pct=ram_pct,
                ram_used_mb=ram_used_mb,
                ram_total_mb=ram_total_mb,
                loop_lat_ms=loop_lat,
                avolites_status=avolites_status,
                vision_manager=getattr(self, 'vision_manager', None),
                audio_engine=getattr(self, 'engine', None),
                audio_monitor=getattr(self, 'audio_monitor', None),
                calendar_manager=getattr(self, 'calendar_manager', None),
            )

            # Actualizar VisionConfigWidget si existe
            if hasattr(self, 'vision_config_widget') and self.vision_config_widget:
                try:
                    self.vision_config_widget.update_status()
                except Exception:
                    pass

        except Exception:
            pass

    def _log_analyzer_stats(self):
        """V12: Log único al inicio con estadísticas de analizadores Motor Real + Legacy"""
        # Motor Real modules
        motor_real = self.modules_bajada + self.modules_golpe + self.modules_ataque + self.modules_brake

        # Legacy modules
        legacy = (
            self.modules_bajada_legacy +
            self.modules_golpe_legacy +
            self.modules_ataque_legacy +
            self.modules_brake_legacy
        )

        all_modules = motor_real + legacy

        motor_active = sum(1 for m in motor_real if getattr(m, 'active', True))
        legacy_active = sum(1 for m in legacy if getattr(m, 'active', True))
        disabled_count = sum(1 for m in all_modules if getattr(m, 'disabled_by_preset', False))
        placeholder_count = sum(1 for m in all_modules if getattr(m, 'is_placeholder', False))

        print("=" * 60)
        print(f"[V12] Motor Real: {motor_active} | Legacy: {legacy_active} | Disabled: {disabled_count} | Placeholders: {placeholder_count}")

        disabled_names = [m.name for m in all_modules if getattr(m, 'disabled_by_preset', False)]
        if disabled_names:
            print(f"[V12] Disabled by preset: {', '.join(disabled_names)}")

        placeholder_names = [m.name for m in all_modules if getattr(m, 'is_placeholder', False)]
        if placeholder_names:
            print(f"[V12] Placeholders: {', '.join(placeholder_names)}")

        print("=" * 60)

    def _get_active_modules(self, modules_list):
        """Retorna solo módulos activos para votación"""
        return [m for m in modules_list if getattr(m, 'active', True)]

    def _setup_ui(self):
        # V12: Apply Neon Pro stylesheet
        if NEON_STYLES_AVAILABLE:
            self.setStyleSheet(get_full_stylesheet())
            print("[MAIN] V12 Neon Pro styling applied")

        top = QWidget()
        top.setObjectName("TopBar")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(S_LG, 0, S_LG, 0)

        # V13: Only status indicators in top bar - all controls in Red/Consola tab
        top_layout.addStretch()
        self.lbl_info = QLabel("🎙 Sin conectar")
        self.vu_db = QLabel("Nivel: - dBFS")
        top_layout.addWidget(self.lbl_info)
        top_layout.addWidget(self.vu_db)

        self.waveform = SmoothWaveform(seconds=8.0, samplerate=48000, fps=30, px_per_sec=120)
        self.waveform.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.waveform.setFixedHeight(120)

        self.status_bajada_box, self._labels_bajada = self._build_status_box(self.modules_bajada)
        self.status_golpe_box, self._labels_golpe = self._build_status_box(self.modules_golpe)
        self.status_ataque_box, self._labels_ataque = self._build_status_box(self.modules_ataque)
        self.status_brake_box, self._labels_brake = self._build_status_box(self.modules_brake)

        self.waveform_hosts = {}
        for name in ["bajada", "golpe", "ataque", "brake", "monitor", "cues", "red"]:
            host = QFrame()
            host.setFixedHeight(120)
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0,0,0,0)
            self.waveform_hosts[name] = host

        self.view_stack = QStackedWidget()
        self.sidebar = SidebarNav()
        self.sidebar.set_stack(self.view_stack)

        # Bajada
        tab_bajada = QWidget()
        layout_bajada = QVBoxLayout(tab_bajada)
        layout_bajada.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        layout_bajada.setSpacing(GRID_SPACING)
        layout_bajada.addWidget(self.waveform_hosts["bajada"])
        status_card_bajada = GlassCard("BAJADA — STATUS")
        status_card_bajada.add_widget(self.status_bajada_box)
        layout_bajada.addWidget(status_card_bajada)
        modules_card_bajada = GlassCard("MÓDULOS")
        modules_card_bajada.add_widget(make_grid(self.modules_bajada, cols=4))
        layout_bajada.addWidget(modules_card_bajada)
        self.view_stack.addWidget(tab_bajada)
        self.tab_bajada = tab_bajada

        # Golpe
        tab_golpe = QWidget()
        layout_golpe = QVBoxLayout(tab_golpe)
        layout_golpe.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        layout_golpe.setSpacing(GRID_SPACING)
        layout_golpe.addWidget(self.waveform_hosts["golpe"])
        status_card_golpe = GlassCard("BASE GOLPE — STATUS")
        status_card_golpe.add_widget(self.status_golpe_box)
        layout_golpe.addWidget(status_card_golpe)
        modules_card_golpe = GlassCard("MÓDULOS")
        modules_card_golpe.add_widget(make_grid(self.modules_golpe, cols=4))
        layout_golpe.addWidget(modules_card_golpe)
        self.view_stack.addWidget(tab_golpe)
        self.tab_golpe = tab_golpe

        # Ataque
        tab_ataque = QWidget()
        layout_ataque = QVBoxLayout(tab_ataque)
        layout_ataque.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        layout_ataque.setSpacing(GRID_SPACING)
        layout_ataque.addWidget(self.waveform_hosts["ataque"])
        status_card_ataque = GlassCard("ATAQUE — STATUS")
        status_card_ataque.add_widget(self.status_ataque_box)
        layout_ataque.addWidget(status_card_ataque)
        modules_card_ataque = GlassCard("MÓDULOS")
        modules_card_ataque.add_widget(make_grid(self.modules_ataque, cols=3))
        layout_ataque.addWidget(modules_card_ataque)
        self.view_stack.addWidget(tab_ataque)
        self.tab_ataque = tab_ataque

        # Brake
        tab_brake = QWidget()
        layout_brake = QVBoxLayout(tab_brake)
        layout_brake.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        layout_brake.setSpacing(GRID_SPACING)
        layout_brake.addWidget(self.waveform_hosts["brake"])
        status_card_brake = GlassCard("BRAKE — STATUS")
        status_card_brake.add_widget(self.status_brake_box)
        layout_brake.addWidget(status_card_brake)
        modules_card_brake = GlassCard("MÓDULOS")
        modules_card_brake.add_widget(make_grid(self.modules_brake, cols=3))
        layout_brake.addWidget(modules_card_brake)
        self.view_stack.addWidget(tab_brake)
        self.tab_brake = tab_brake

        # V12: Legacy Analyzers Tab
        tab_legacy = QWidget()
        layout_legacy = QVBoxLayout(tab_legacy)
        layout_legacy.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        layout_legacy.setSpacing(GRID_SPACING)

        # Legacy title
        legacy_title = QLabel("ANALIZADORES ADICIONALES / LEGACY")
        legacy_title.setStyleSheet("font-weight:700; color:#00e676; font-family:'Space Grotesk','Inter',sans-serif; font-size:14px; padding:8px;")
        layout_legacy.addWidget(legacy_title)

        legacy_desc = QLabel("Estos analizadores no participan en el motor de estados activo.\nSe mantienen para experimentación y monitoreo adicional.")
        legacy_desc.setStyleSheet("color:#a0a0b0; font-size:11px; padding:4px;")
        layout_legacy.addWidget(legacy_desc)

        # Collect all legacy modules
        all_legacy = (
            self.modules_bajada_legacy +
            self.modules_golpe_legacy +
            self.modules_ataque_legacy +
            self.modules_brake_legacy
        )

        if all_legacy:
            # Build status box for legacy modules
            self.status_legacy_box, self._labels_legacy = self._build_status_box(all_legacy)
            layout_legacy.addWidget(self.status_legacy_box)
            layout_legacy.addWidget(make_grid(all_legacy, cols=4))
        else:
            no_legacy_lbl = QLabel("No hay analizadores legacy activos.\nTodos los analizadores están en el Motor Real.")
            no_legacy_lbl.setStyleSheet("color:#606070; font-size:12px; padding:20px;")
            no_legacy_lbl.setAlignment(Qt.AlignCenter)
            layout_legacy.addWidget(no_legacy_lbl)
            self._labels_legacy = []

        layout_legacy.addStretch()
        self.view_stack.addWidget(tab_legacy)
        self.tab_legacy = tab_legacy

        # Cues
        if CUES_AVAILABLE and create_cues_monitor_tab:
            try:
                self.cues_tab = create_cues_monitor_tab(
                    avolites=self.avolites,
                    state_manager=self.state_manager,
                    energy_detector=self.energy_detector,
                    parent=self.view_stack,
                    cue_engine=self.cue_engine,
                    modules_bajada=self.modules_bajada,
                    modules_golpe=self.modules_golpe,
                    modules_ataque=self.modules_ataque,
                    modules_brake=self.modules_brake
                )
                if hasattr(self.cues_tab, 'layout'):
                    cues_layout = self.cues_tab.layout()
                    if cues_layout:
                        cues_layout.insertWidget(0, self.waveform_hosts["cues"])

                self.view_stack.addWidget(self.cues_tab)
                self.btn_cues.clicked.connect(lambda: self.sidebar.select_widget(self.cues_tab))
            except Exception as e:
                print(f"[MAIN] Error creando Cues tab: {e}")
                self.cues_tab = None
        else:
            self.cues_tab = None

        # ===================================================================
        # Monitor — WEB Control Room Dashboard
        # Layout: Metrics bar → 3-column card grid
        # Matches webapp/src/pages/Home.jsx
        # ===================================================================
        tab_monitor = QWidget()
        layout_monitor = QVBoxLayout(tab_monitor)
        layout_monitor.setContentsMargins(S_XL, S_LG, S_XL, S_LG)
        layout_monitor.setSpacing(GRID_SPACING)

        # -- Waveform (full-width) -----------------------------------------
        layout_monitor.addWidget(self.waveform_hosts["monitor"])

        # -- Metrics Bar (WEB: 4-column top bar) ---------------------------
        metrics_card = GlassCard()
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(GRID_SPACING)
        metrics_grid.setContentsMargins(CARD_PADDING, S_BASE, CARD_PADDING, S_BASE)

        _inset_ss = (
            f"QFrame{{background:{BG_INSET_SOLID}; border:1px solid #1e1e28; "
            f"border-radius:{R_MD}px; padding:{S_MD}px;}}"
        )

        def _make_metric(title, initial="—"):
            """Build a small inset metric panel (WEB: .inset inside metrics bar)."""
            f = QFrame()
            f.setStyleSheet(_inset_ss)
            fl = QVBoxLayout(f)
            fl.setContentsMargins(S_MD, S_SM, S_MD, S_SM)
            fl.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; font-weight:600; font-family:{FONT_TITLE}; border:none; background:transparent;")
            v = QLabel(initial)
            v.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:700; font-family:{FONT_MONO}; border:none; background:transparent;")
            fl.addWidget(t)
            fl.addWidget(v)
            return f, v

        m_vu, self.dash_vu_value = _make_metric("NIVEL AUDIO", "— dBFS")
        m_bpm, self.dash_bpm_value = _make_metric("BPM", "—")
        m_conn, self.dash_conn_value = _make_metric("CONSOLA", "Desconectado")
        m_state, self.dash_state_value = _make_metric("ESTADO", "—")

        metrics_grid.addWidget(m_vu, 0, 0)
        metrics_grid.addWidget(m_bpm, 0, 1)
        metrics_grid.addWidget(m_conn, 0, 2)
        metrics_grid.addWidget(m_state, 0, 3)
        for c in range(4):
            metrics_grid.setColumnStretch(c, 1)

        metrics_w = QWidget()
        metrics_w.setLayout(metrics_grid)
        metrics_card.add_widget(metrics_w)
        layout_monitor.addWidget(metrics_card)

        # -- Card Grid (WEB: repeat(auto-fit, minmax(320px, 1fr))) ---------
        dash_grid = QGridLayout()
        dash_grid.setSpacing(GRID_SPACING)
        for c in range(3):
            dash_grid.setColumnStretch(c, 1)

        _grid_row = 0
        _grid_col = 0

        def _next_cell():
            nonlocal _grid_row, _grid_col
            r, c = _grid_row, _grid_col
            _grid_col += 1
            if _grid_col >= 3:
                _grid_col = 0
                _grid_row += 1
            return r, c

        # Card: Placa de Sonido (Audio)
        audio_card = GlassCard("PLACA DE SONIDO")
        audio_inner = QVBoxLayout()
        audio_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
        audio_inner.setSpacing(S_SM)
        self.vu_main = QProgressBar()
        self.vu_main.setRange(0, 1000)
        self.vu_main.setTextVisible(False)
        self.vu_main.setFixedHeight(8)
        self.vu_main.setStyleSheet(
            f"QProgressBar{{background:{BG_INSET_SOLID}; border:1px solid {BORDER_SOLID}; border-radius:4px;}} "
            f"QProgressBar::chunk{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0, "
            f"stop:0 {NEON_GREEN}, stop:1 #4dd0e1); border-radius:3px;}}"
        )
        self.dash_audio_device = QLabel("—")
        self.dash_audio_device.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;")
        self.dash_audio_level = QLabel("Nivel: —")
        self.dash_audio_level.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px; font-weight:600; font-family:{FONT_MONO}; border:none; background:transparent;")
        audio_inner.addWidget(self.dash_audio_device)
        audio_inner.addWidget(self.dash_audio_level)
        audio_inner.addWidget(self.vu_main)
        audio_w = QWidget()
        audio_w.setLayout(audio_inner)
        audio_card.add_widget(audio_w)
        r, c = _next_cell()
        dash_grid.addWidget(audio_card, r, c)

        # Card: Consola Avolites
        console_card = GlassCard("CONSOLA AVOLITES")
        console_inner = QVBoxLayout()
        console_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
        console_inner.setSpacing(S_SM)
        self.dash_console_ip = QLabel("IP: —")
        self.dash_console_ip.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;")
        self.dash_console_status = QLabel("● Desconectado")
        self.dash_console_status.setStyleSheet(f"color:#e74c3c; font-size:13px; font-weight:700; border:none; background:transparent;")
        self.dash_console_latency = QLabel("Latencia: —")
        self.dash_console_latency.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; border:none; background:transparent;")
        console_inner.addWidget(self.dash_console_ip)
        console_inner.addWidget(self.dash_console_status)
        console_inner.addWidget(self.dash_console_latency)
        console_w = QWidget()
        console_w.setLayout(console_inner)
        console_card.add_widget(console_w)
        r, c = _next_cell()
        dash_grid.addWidget(console_card, r, c)

        # Card: Red Local (Network)
        net_card_dash = GlassCard("RED LOCAL")
        net_inner = QVBoxLayout()
        net_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
        net_inner.setSpacing(S_SM)
        self.dash_net_ip = QLabel("IP: —")
        self.dash_net_ip.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;")
        self.dash_net_iface = QLabel("Interfaz: —")
        self.dash_net_iface.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; border:none; background:transparent;")
        net_inner.addWidget(self.dash_net_ip)
        net_inner.addWidget(self.dash_net_iface)
        net_w = QWidget()
        net_w.setLayout(net_inner)
        net_card_dash.add_widget(net_w)
        r, c = _next_cell()
        dash_grid.addWidget(net_card_dash, r, c)

        # Card: Energy Monitor
        if ENERGY_AVAILABLE:
            energy_card = GlassCard("ENERGY")
            self.energy_widget = EnergyMonitorWidget(self.energy_detector)
            self.energy_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.energy_widget.setMinimumHeight(180)
            energy_card.add_widget(self.energy_widget)
            energy_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            r, c = _next_cell()
            dash_grid.addWidget(energy_card, r, c)

        # Card: Current State
        if STATE_WIDGET_AVAILABLE:
            state_card = GlassCard("CURRENT STATE")
            self.state_widget = StateMonitorWidget(self.state_manager)
            self.state_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.state_widget.setMinimumHeight(180)
            state_card.add_widget(self.state_widget)
            state_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            r, c = _next_cell()
            dash_grid.addWidget(state_card, r, c)
        else:
            self.state_widget = None

        # Card: Modules (WEB: 4 module rows with LED dots)
        modules_card = GlassCard("MODULES")
        modules_inner = QVBoxLayout()
        modules_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
        modules_inner.setSpacing(S_SM)
        modules_inner.addWidget(self.status_bajada_box)
        modules_inner.addWidget(self.status_golpe_box)
        modules_inner.addWidget(self.status_ataque_box)
        modules_inner.addWidget(self.status_brake_box)
        modules_wrapper = QWidget()
        modules_wrapper.setLayout(modules_inner)
        modules_card.add_widget(modules_wrapper)
        r, c = _next_cell()
        dash_grid.addWidget(modules_card, r, c)

        # Card: Cues Engine
        if self.cue_engine:
            try:
                cues_card = GlassCard("LAST CUE")
                self.cues_debug_widget = create_cue_engine_debug_widget(self.cue_engine)
                try:
                    self.cues_debug_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                except Exception:
                    pass
                cues_card.add_widget(self.cues_debug_widget)
                cues_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                r, c = _next_cell()
                dash_grid.addWidget(cues_card, r, c)
            except:
                self.cues_debug_widget = None
        else:
            self.cues_debug_widget = None

        # Card: Haze (Vision)
        if VISION_AVAILABLE:
            haze_card = GlassCard("HAZE")
            haze_inner = QHBoxLayout()
            haze_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
            haze_inner.setSpacing(S_SM)
            self.haze_bar = QProgressBar()
            self.haze_bar.setOrientation(Qt.Vertical)
            self.haze_bar.setRange(0, 100)
            self.haze_bar.setValue(0)
            self.haze_bar.setTextVisible(False)
            self.haze_bar.setFixedWidth(20)
            self.haze_bar.setMinimumHeight(120)
            self.haze_bar.setStyleSheet(
                f"QProgressBar{{background:{BG_INSET_SOLID}; border:1px solid {BORDER_SOLID}; border-radius:10px;}} "
                "QProgressBar::chunk{background:qlineargradient(x1:0, y1:1, x2:0, y2:0, "
                "stop:0 #4a90e2, stop:0.5 #7ec8e3, stop:1 #aaddff); border-radius:10px;}"
            )
            self.dash_haze_pct = QLabel("0%")
            self.dash_haze_pct.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:20px; font-weight:700; font-family:{FONT_MONO}; border:none; background:transparent;")
            self.dash_haze_pct.setAlignment(Qt.AlignCenter)
            haze_inner.addWidget(self.haze_bar)
            haze_inner.addWidget(self.dash_haze_pct, 1)
            haze_w = QWidget()
            haze_w.setLayout(haze_inner)
            haze_card.add_widget(haze_w)
            r, c = _next_cell()
            dash_grid.addWidget(haze_card, r, c)
        else:
            self.haze_bar = None

        # Card: Transport
        transport_card = GlassCard("TRANSPORT")
        transport_inner = QVBoxLayout()
        transport_inner.setContentsMargins(CARD_PADDING, 0, CARD_PADDING, CARD_PADDING)
        transport_inner.setSpacing(S_SM)
        self.dash_transport_mode = QLabel("HTTP")
        self.dash_transport_mode.setStyleSheet(f"color:{NEON_GREEN}; font-size:14px; font-weight:700; font-family:{FONT_MONO}; border:none; background:transparent;")
        transport_inner.addWidget(self.dash_transport_mode)
        transport_w = QWidget()
        transport_w.setLayout(transport_inner)
        transport_card.add_widget(transport_w)
        r, c = _next_cell()
        dash_grid.addWidget(transport_card, r, c)

        layout_monitor.addLayout(dash_grid)
        layout_monitor.addStretch()
        
        self.view_stack.addWidget(tab_monitor)
        self.tab_monitor = tab_monitor

        # === PANEL RED/CONSOLA UNIFICADO ===
        tab_net = QWidget()
        ln = QVBoxLayout(tab_net)
        ln.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        ln.setSpacing(GRID_SPACING)

        # === Sección: LOAD SHOW (Perfil Único) ===
        show_frame = QFrame()
        show_frame.setStyleSheet(f"QFrame{{background:#1a141a; border:1px solid #4a2a4a; border-radius:{CARD_RADIUS}px;}}")
        show_layout = QVBoxLayout(show_frame)
        show_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        show_layout.setSpacing(S_SM)
        show_title = QLabel("LOAD SHOW")
        show_title.setStyleSheet("font-weight:700; color:#f8f; font-size:12px;")
        show_layout.addWidget(show_title)

        row_show_path = QHBoxLayout()
        row_show_path.addWidget(QLabel("Perfil:"))
        self.txt_show_path = QLineEdit()
        self.txt_show_path.setText(self.preset_path)
        self.txt_show_path.setReadOnly(True)
        self.txt_show_path.setStyleSheet("background:#0e0e14; border:1px solid #2e2e38; border-radius:10px; padding:4px; color:#f0f0f0;")
        row_show_path.addWidget(self.txt_show_path, 2)
        self.btn_show_browse = QPushButton("Elegir...")
        self.btn_show_browse.setStyleSheet("QPushButton{background:#2e2e38; border:1px solid #2e2e38; border-radius:10px; padding:6px; color:#f0f0f0;} QPushButton:hover{background:#2e2e38;}")
        row_show_path.addWidget(self.btn_show_browse)
        show_layout.addLayout(row_show_path)

        row_show_btns = QHBoxLayout()
        self.btn_show_load = QPushButton("Cargar Perfil")
        self.btn_show_load.setStyleSheet("QPushButton{background:#27ae60; border:1px solid #229954; border-radius:10px; padding:8px 16px; color:#fff; font-weight:700;} QPushButton:hover{background:#2ecc71;}")
        self.btn_show_save = QPushButton("Guardar Perfil")
        self.btn_show_save.setStyleSheet("QPushButton{background:#3498db; border:1px solid #2980b9; border-radius:10px; padding:8px 16px; color:#fff; font-weight:700;} QPushButton:hover{background:#5dade2;}")
        row_show_btns.addWidget(self.btn_show_load)
        row_show_btns.addWidget(self.btn_show_save)
        row_show_btns.addStretch()
        show_layout.addLayout(row_show_btns)
        ln.addWidget(show_frame)

        # === Sección: AUDIO DEVICE ===
        audio_frame = QFrame()
        audio_frame.setStyleSheet(f"QFrame{{background:#141a14; border:1px solid #2a4a2a; border-radius:{CARD_RADIUS}px;}}")
        audio_layout = QVBoxLayout(audio_frame)
        audio_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        audio_layout.setSpacing(S_SM)
        audio_title = QLabel("AUDIO DEVICE")
        audio_title.setStyleSheet("font-weight:700; color:#8f8; font-size:12px;")
        audio_layout.addWidget(audio_title)

        row_audio_device = QHBoxLayout()
        row_audio_device.addWidget(QLabel("Entrada:"))
        self.cmb_audio_device = QComboBox()
        self.cmb_audio_device.setMinimumWidth(300)
        self._populate_audio_devices()
        row_audio_device.addWidget(self.cmb_audio_device, 2)
        self.lbl_audio_status = QLabel("● Sin conectar")
        self.lbl_audio_status.setStyleSheet("color:#e74c3c; font-weight:700;")
        row_audio_device.addWidget(self.lbl_audio_status)
        row_audio_device.addStretch()
        audio_layout.addLayout(row_audio_device)

        row_audio_info = QHBoxLayout()
        self.lbl_audio_sr = QLabel("SR: —")
        self.lbl_audio_sr.setStyleSheet("color:#8a8a8a;")
        row_audio_info.addWidget(self.lbl_audio_sr)
        self.lbl_audio_db = QLabel("dBFS: —")
        self.lbl_audio_db.setStyleSheet("color:#8a8a8a;")
        row_audio_info.addWidget(self.lbl_audio_db)
        row_audio_info.addStretch()
        audio_layout.addLayout(row_audio_info)

        row_audio_btns = QHBoxLayout()
        self.btn_audio_connect = QPushButton("Conectar Audio")
        self.btn_audio_connect.setStyleSheet("QPushButton{background:#27ae60; border:1px solid #229954; border-radius:10px; padding:6px; color:#fff;} QPushButton:hover{background:#2ecc71;}")
        self.btn_audio_disconnect = QPushButton("Desconectar")
        self.btn_audio_disconnect.setStyleSheet("QPushButton{background:#e74c3c; border:1px solid #c0392b; border-radius:10px; padding:6px; color:#fff;} QPushButton:hover{background:#ec7063;}")
        row_audio_btns.addWidget(self.btn_audio_connect)
        row_audio_btns.addWidget(self.btn_audio_disconnect)
        row_audio_btns.addStretch()
        audio_layout.addLayout(row_audio_btns)
        ln.addWidget(audio_frame)

        # Encabezado con estado
        header_frame = QFrame()
        header_frame.setStyleSheet(f"QFrame{{background:{CARD_BACKGROUND}; border:1px solid {CARD_BORDER}; border-radius:{CARD_RADIUS}px; padding:{S_SM}px;}}")
        header_layout = QHBoxLayout(header_frame)
        self.net_status_badge = QLabel("● Desconectado")
        self.net_status_badge.setStyleSheet("color:#e74c3c; font-weight:700; font-size:14px;")
        header_layout.addWidget(self.net_status_badge)
        self.net_latency_label = QLabel("")
        self.net_latency_label.setStyleSheet("color:#8a8a8a; font-size:11px;")
        header_layout.addWidget(self.net_latency_label)
        header_layout.addStretch()
        self.btn_net_reconnect = QPushButton("Reconectar")
        self.btn_net_stop = QPushButton("Detener")
        self.btn_net_refresh = QPushButton("Refrescar")
        for btn in [self.btn_net_reconnect, self.btn_net_stop, self.btn_net_refresh]:
            btn.setStyleSheet("QPushButton{background:#2e2e38; border:1px solid #2e2e38; border-radius:10px; padding:6px; color:#a6a6a6;} QPushButton:hover{background:#2e2e38;}")
            header_layout.addWidget(btn)
        ln.addWidget(header_frame)
        
        # ================================================================
        # TARJETA UNIFICADA: RED / CONSOLA (Titan)
        # Contiene: Destino + NIC local + Transporte + Auto-connect
        # ================================================================
        net_card = QFrame()
        net_card.setStyleSheet(f"QFrame{{background:{CARD_BACKGROUND}; border:1px solid {CARD_BORDER}; border-radius:{CARD_RADIUS}px;}}")
        net_card_layout = QVBoxLayout(net_card)
        net_card_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        net_card_layout.setSpacing(S_MD)

        # Título de la tarjeta
        net_card_title = QLabel("RED / CONSOLA (Titan)")
        net_card_title.setStyleSheet("font-weight:700; color:#f0f0f0; font-size:14px; border:none;")
        net_card_layout.addWidget(net_card_title)

        # Separador visual
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("background:#2e2e38; border:none;")
        sep1.setFixedHeight(1)
        net_card_layout.addWidget(sep1)

        # --- Subsección: Destino Consola ---
        dest_subtitle = QLabel("Destino Consola")
        dest_subtitle.setStyleSheet("font-weight:600; color:#3498db; font-size:11px; border:none;")
        net_card_layout.addWidget(dest_subtitle)

        row_ip = QHBoxLayout()
        lbl_ip = QLabel("IP:")
        lbl_ip.setStyleSheet("color:#a6a6a6; border:none;")
        row_ip.addWidget(lbl_ip)
        self.ed_console_ip = QLineEdit()
        self.ed_console_ip.setPlaceholderText("10.0.0.1")
        self.ed_console_ip.setMaximumWidth(140)
        row_ip.addWidget(self.ed_console_ip)
        lbl_port = QLabel("Puerto:")
        lbl_port.setStyleSheet("color:#a6a6a6; border:none;")
        row_ip.addWidget(lbl_port)
        self.ed_console_port = QLineEdit()
        self.ed_console_port.setPlaceholderText("4430")
        self.ed_console_port.setMaximumWidth(70)
        row_ip.addWidget(self.ed_console_port)
        row_ip.addStretch()
        net_card_layout.addLayout(row_ip)

        row_dest_btns = QHBoxLayout()
        self.btn_save_reconnect = QPushButton("Guardar y Reconectar")
        self.btn_save_reconnect.setStyleSheet("QPushButton{background:#27ae60; border:1px solid #229954; border-radius:10px; padding:6px 12px; color:#fff; font-weight:700;} QPushButton:hover{background:#2ecc71;}")
        row_dest_btns.addWidget(self.btn_save_reconnect)
        self.chk_auto_retry = QCheckBox("Auto-reintento")
        self.chk_auto_retry.setStyleSheet("color:#a6a6a6;")
        row_dest_btns.addWidget(self.chk_auto_retry)
        row_dest_btns.addStretch()
        net_card_layout.addLayout(row_dest_btns)

        # Separador
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("background:#2e2e38; border:none;")
        sep2.setFixedHeight(1)
        net_card_layout.addWidget(sep2)

        # --- Subsección: NIC Local ---
        nic_subtitle = QLabel("NIC Local (bind)")
        nic_subtitle.setStyleSheet("font-weight:600; color:#e67e22; font-size:11px; border:none;")
        net_card_layout.addWidget(nic_subtitle)

        row_nic = QHBoxLayout()
        lbl_nic = QLabel("NIC:")
        lbl_nic.setStyleSheet("color:#a6a6a6; border:none;")
        row_nic.addWidget(lbl_nic)
        self.cmb_nic = QComboBox()
        self.cmb_nic.setMinimumWidth(280)
        row_nic.addWidget(self.cmb_nic, 2)
        lbl_eff = QLabel("IP efectiva:")
        lbl_eff.setStyleSheet("color:#a6a6a6; border:none;")
        row_nic.addWidget(lbl_eff)
        self.lbl_local_ip = QLabel("—")
        self.lbl_local_ip.setStyleSheet("color:#27ae60; font-weight:700; border:none;")
        row_nic.addWidget(self.lbl_local_ip)
        row_nic.addStretch()
        net_card_layout.addLayout(row_nic)

        row_nic_btns = QHBoxLayout()
        self.btn_apply_nic = QPushButton("Guardar NIC")
        self.btn_apply_nic.setStyleSheet("QPushButton{background:#e67e22; border:1px solid #d35400; border-radius:10px; padding:6px 12px; color:#fff;} QPushButton:hover{background:#f39c12;}")
        row_nic_btns.addWidget(self.btn_apply_nic)
        self.chk_nic_auto_connect = QCheckBox("Auto-connect al iniciar")
        self.chk_nic_auto_connect.setChecked(True)
        self.chk_nic_auto_connect.setStyleSheet("color:#a6a6a6;")
        self.chk_nic_auto_connect.setToolTip("Si está marcado, aplica esta NIC automáticamente al reiniciar la app")
        row_nic_btns.addWidget(self.chk_nic_auto_connect)
        row_nic_btns.addStretch()
        net_card_layout.addLayout(row_nic_btns)

        # Separador
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("background:#2e2e38; border:none;")
        sep3.setFixedHeight(1)
        net_card_layout.addWidget(sep3)

        # --- Subsección: Transporte (solo si soportado) ---
        self.transport_frame = QFrame()
        self.transport_frame.setStyleSheet("border:none;")
        transport_layout = QVBoxLayout(self.transport_frame)
        transport_layout.setContentsMargins(0, 0, 0, 0)
        transport_layout.setSpacing(8)

        transport_subtitle = QLabel("Transporte")
        transport_subtitle.setStyleSheet("font-weight:600; color:#9b59b6; font-size:11px; border:none;")
        transport_layout.addWidget(transport_subtitle)

        row_transport = QHBoxLayout()
        self.transport_group = QButtonGroup()
        self.radio_http = QRadioButton("HTTP")
        self.radio_artnet = QRadioButton("Art-Net")
        self.radio_sacn = QRadioButton("sACN")
        self.radio_http.setStyleSheet("color:#a6a6a6;")
        self.radio_artnet.setStyleSheet("color:#a6a6a6;")
        self.radio_sacn.setStyleSheet("color:#a6a6a6;")
        self.transport_group.addButton(self.radio_http)
        self.transport_group.addButton(self.radio_artnet)
        self.transport_group.addButton(self.radio_sacn)
        self.radio_http.setChecked(True)
        row_transport.addWidget(self.radio_http)
        row_transport.addWidget(self.radio_artnet)
        row_transport.addWidget(self.radio_sacn)
        row_transport.addStretch()
        transport_layout.addLayout(row_transport)

        # Subparámetros sACN
        self.sacn_params = QFrame()
        self.sacn_params.setStyleSheet("border:none;")
        sacn_layout = QHBoxLayout(self.sacn_params)
        sacn_layout.setContentsMargins(0, 0, 0, 0)
        lbl_univ = QLabel("Universe:")
        lbl_univ.setStyleSheet("color:#a6a6a6; border:none;")
        sacn_layout.addWidget(lbl_univ)
        self.spin_sacn_universe = QSpinBox()
        self.spin_sacn_universe.setRange(1, 63999)
        self.spin_sacn_universe.setValue(1)
        sacn_layout.addWidget(self.spin_sacn_universe)
        lbl_prio = QLabel("Priority:")
        lbl_prio.setStyleSheet("color:#a6a6a6; border:none;")
        sacn_layout.addWidget(lbl_prio)
        self.spin_sacn_priority = QSpinBox()
        self.spin_sacn_priority.setRange(0, 200)
        self.spin_sacn_priority.setValue(100)
        sacn_layout.addWidget(self.spin_sacn_priority)
        sacn_layout.addStretch()
        transport_layout.addWidget(self.sacn_params)

        # Subparámetros Art-Net
        self.artnet_params = QFrame()
        self.artnet_params.setStyleSheet("border:none;")
        artnet_layout = QHBoxLayout(self.artnet_params)
        artnet_layout.setContentsMargins(0, 0, 0, 0)
        lbl_net = QLabel("Net:")
        lbl_net.setStyleSheet("color:#a6a6a6; border:none;")
        artnet_layout.addWidget(lbl_net)
        self.spin_artnet_net = QSpinBox()
        self.spin_artnet_net.setRange(0, 127)
        artnet_layout.addWidget(self.spin_artnet_net)
        lbl_sub = QLabel("Subnet:")
        lbl_sub.setStyleSheet("color:#a6a6a6; border:none;")
        artnet_layout.addWidget(lbl_sub)
        self.spin_artnet_subnet = QSpinBox()
        self.spin_artnet_subnet.setRange(0, 15)
        artnet_layout.addWidget(self.spin_artnet_subnet)
        lbl_univ2 = QLabel("Universe:")
        lbl_univ2.setStyleSheet("color:#a6a6a6; border:none;")
        artnet_layout.addWidget(lbl_univ2)
        self.spin_artnet_universe = QSpinBox()
        self.spin_artnet_universe.setRange(0, 15)
        artnet_layout.addWidget(self.spin_artnet_universe)
        artnet_layout.addStretch()
        transport_layout.addWidget(self.artnet_params)
        self.artnet_params.setVisible(False)
        self.sacn_params.setVisible(False)

        row_transport_btn = QHBoxLayout()
        self.btn_apply_transport = QPushButton("Aplicar Transporte")
        self.btn_apply_transport.setStyleSheet("QPushButton{background:#9b59b6; border:1px solid #8e44ad; border-radius:10px; padding:6px 12px; color:#fff;} QPushButton:hover{background:#a569bd;}")
        row_transport_btn.addWidget(self.btn_apply_transport)
        row_transport_btn.addStretch()
        transport_layout.addLayout(row_transport_btn)

        if hasattr(self.avolites, 'set_transport'):
            net_card_layout.addWidget(self.transport_frame)
        else:
            self.transport_frame.setVisible(False)

        ln.addWidget(net_card)

        # === Sección: Avolites Cue Offset ===
        offset_frame = QFrame()
        offset_frame.setStyleSheet(f"QFrame{{background:{CARD_BACKGROUND}; border:1px solid {CARD_BORDER}; border-radius:{CARD_RADIUS}px;}}")
        offset_layout = QVBoxLayout(offset_frame)
        offset_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        offset_layout.setSpacing(8)
        offset_title = QLabel("AVOLITES CUE OFFSET")
        offset_title.setStyleSheet("font-weight:700; color:#f0f0f0; font-size:12px;")
        offset_layout.addWidget(offset_title)

        row_offset = QHBoxLayout()
        row_offset.addWidget(QLabel("Offset (lógico → real):"))
        self.spin_cue_offset = QSpinBox()
        self.spin_cue_offset.setRange(0, 300)
        self.spin_cue_offset.setValue(169)
        self.spin_cue_offset.setToolTip("Offset para mapear cues lógicos (1-59) a IDs reales en Titan")
        row_offset.addWidget(self.spin_cue_offset)
        row_offset.addWidget(QLabel("Ejemplo: 1 → "))
        self.lbl_offset_example = QLabel("170")
        self.lbl_offset_example.setStyleSheet("color:#27ae60; font-weight:700;")
        row_offset.addWidget(self.lbl_offset_example)
        row_offset.addStretch()
        offset_layout.addLayout(row_offset)

        row_offset_btn = QHBoxLayout()
        self.btn_apply_cue_offset = QPushButton("Guardar Offset")
        self.btn_apply_cue_offset.setStyleSheet("QPushButton{background:#e67e22; border:1px solid #d35400; border-radius:10px; padding:6px; color:#fff;} QPushButton:hover{background:#f39c12;}")
        row_offset_btn.addWidget(self.btn_apply_cue_offset)
        row_offset_btn.addStretch()
        offset_layout.addLayout(row_offset_btn)
        ln.addWidget(offset_frame)

        # === Sistema Vision PRO (Multicámara) ===
        if VISION_AVAILABLE and hasattr(self, "vision_manager"):
            try:
                self.vision_config_widget = VisionConfigWidget(self.vision_manager)
                ln.addWidget(self.vision_config_widget)
                print("[MAIN] VisionConfigWidget añadido a Red/Consola")
            except Exception as e:
                print(f"[MAIN] Error creando VisionConfigWidget: {e}")

        # Sección: Diagnóstico
        diag_frame = QFrame()
        diag_frame.setStyleSheet(f"QFrame{{background:{CARD_BACKGROUND}; border:1px solid {CARD_BORDER}; border-radius:{CARD_RADIUS}px;}}")
        diag_layout = QVBoxLayout(diag_frame)
        diag_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        diag_layout.setSpacing(8)
        diag_title = QLabel("DIAGNÓSTICO")
        diag_title.setStyleSheet("font-weight:700; color:#f0f0f0; font-size:12px;")
        diag_layout.addWidget(diag_title)
        
        row_ping = QHBoxLayout()
        self.btn_ping = QPushButton("Ping")
        self.btn_ping.setStyleSheet("QPushButton{background:#2e2e38; border:1px solid #2e2e38; border-radius:10px; padding:6px; color:#a6a6a6;} QPushButton:hover{background:#2e2e38;}")
        row_ping.addWidget(self.btn_ping)
        self.lbl_ping_result = QLabel("—")
        self.lbl_ping_result.setStyleSheet("color:#8a8a8a;")
        row_ping.addWidget(self.lbl_ping_result)
        row_ping.addStretch()
        diag_layout.addLayout(row_ping)
        
        row_error = QHBoxLayout()
        row_error.addWidget(QLabel("Último error:"))
        self.lbl_last_error = QLabel("—")
        self.lbl_last_error.setStyleSheet("color:#e74c3c; font-size:10px;")
        self.lbl_last_error.setWordWrap(True)
        row_error.addWidget(self.lbl_last_error, 1)
        diag_layout.addLayout(row_error)
        
        events_lbl = QLabel("Eventos recientes:")
        events_lbl.setStyleSheet("color:#8a8a8a; font-size:10px;")
        diag_layout.addWidget(events_lbl)
        self.net_events_list = QLabel("—")
        self.net_events_list.setStyleSheet("color:#616161; font-size:9px; background:#0a0a0f; border:1px solid #0e0e14; border-radius:10px; padding:6px;")
        self.net_events_list.setWordWrap(True)
        self.net_events_list.setMinimumHeight(80)
        diag_layout.addWidget(self.net_events_list)
        ln.addWidget(diag_frame)
        
        ln.addStretch()
        self.view_stack.addWidget(tab_net)
        self.tab_net = tab_net

        # === PANEL HEALTH ===
        tab_health = QWidget()
        health_layout = QVBoxLayout(tab_health)
        health_layout.setContentsMargins(S_LG, S_LG, S_LG, S_LG)
        health_layout.setSpacing(GRID_SPACING)
        
        self.health_widget = HealthMonitorWidget(self)
        health_layout.addWidget(self.health_widget)
        
        self.view_stack.addWidget(tab_health)
        self.tab_health = tab_health

        # === TAP TEMPO TAB ===
        if TAP_TEMPO_AVAILABLE and self.auto_clock:
            try:
                # V13: Pass both auto_clock and kick_detector to ClockWidget
                kick_det = getattr(self, 'kick_detector', None)
                self.clock_widget = ClockWidget(self.auto_clock, kick_det, self)
                self.view_stack.addWidget(self.clock_widget)
                print(f"[MAIN] ClockWidget V13 (auto_clock + kick_detector={kick_det is not None})")
            except Exception as e:
                self.clock_widget = None
                print(f"[MAIN] Error creando TAP Tempo tab: {e}")
        else:
            self.clock_widget = None

        # === PANEL VISION SYSTEM PRO - 3 TABS INDEPENDIENTES ===
        if VISION_AVAILABLE and self.vision_manager:
            try:
                # Tab 1: Haze Detector PRO (V16: pasa system_bridge para sync checkbox)
                self.vision_haze_tab = VisionHazeTab(self.vision_manager, self, system_bridge=self.system_bridge)
                self.view_stack.addWidget(self.vision_haze_tab)
                print("[MAIN] VisionHazeTab añadido correctamente")

                # Tab 2: DJ Detector PRO
                self.vision_dj_tab = VisionDJTab(self.vision_manager, self)
                self.view_stack.addWidget(self.vision_dj_tab)
                print("[MAIN] VisionDJTab añadido correctamente")

                # Tab 3: Artist Tracker PRO
                self.vision_artist_tab = VisionArtistTab(self.vision_manager, self)
                self.view_stack.addWidget(self.vision_artist_tab)
                print("[MAIN] VisionArtistTab añadido correctamente")

            except Exception as e:
                print(f"[MAIN] Error creando Vision tabs: {e}")
                self.vision_haze_tab = None
                self.vision_dj_tab = None
                self.vision_artist_tab = None
        else:
            self.vision_haze_tab = None
            self.vision_dj_tab = None
            self.vision_artist_tab = None

        # === CALENDAR TAB - Sistema de Gobierno Contextual ===
        if CALENDAR_TAB_AVAILABLE:
            try:
                self.calendar_tab = CalendarTab()
                self.view_stack.addWidget(self.calendar_tab)
                print("[MAIN] CalendarTab añadido correctamente")

                # Conectar CalendarManager si existe
                print(f"[MAIN] CalendarTab: calendar_manager exists={hasattr(self, 'calendar_manager')}, is_not_None={getattr(self, 'calendar_manager', None) is not None}")
                if hasattr(self, 'calendar_manager') and self.calendar_manager:
                    self.calendar_tab.set_calendar_manager(self.calendar_manager)
                    print("[MAIN] OK: CalendarManager conectado a CalendarTab")
                else:
                    print("[MAIN] WARN: CalendarManager NO conectado a CalendarTab (es None o no existe)")
            except Exception as e:
                print(f"[MAIN] Error creando Calendar tab: {e}")
                self.calendar_tab = None
        else:
            self.calendar_tab = None

        # Conectar señales
        self.btn_save_reconnect.clicked.connect(self._on_save_reconnect)
        self.btn_apply_nic.clicked.connect(self._on_apply_nic)
        self.btn_apply_transport.clicked.connect(self._on_apply_transport)
        self.btn_apply_cue_offset.clicked.connect(self._on_apply_cue_offset)
        self.spin_cue_offset.valueChanged.connect(self._on_cue_offset_changed)
        self.btn_ping.clicked.connect(self._on_ping)
        self.btn_net_reconnect.clicked.connect(self._on_net_reconnect)
        self.btn_net_stop.clicked.connect(self._on_net_stop)
        self.btn_net_refresh.clicked.connect(self._on_net_refresh)
        self.radio_http.toggled.connect(self._on_transport_radio_changed)
        self.radio_artnet.toggled.connect(self._on_transport_radio_changed)
        self.radio_sacn.toggled.connect(self._on_transport_radio_changed)
        # NIC combo change auto-persists
        self.cmb_nic.currentIndexChanged.connect(self._on_nic_combo_changed)
        
        self._net_timer = QTimer(self)
        self._net_timer.setInterval(1500)
        self._net_timer.timeout.connect(self._poll_net_status)
        self._net_timer.start()
        
        self._net_events = []

        self.view_stack.currentChanged.connect(self._on_tab_changed)

        # -- Sidebar navigation items ----------------------------------------
        self.sidebar.add_section("DASHBOARD")
        self.sidebar.add_item("Control Room", tab_monitor)

        self.sidebar.add_section("ANALYZERS")
        self.sidebar.add_item("Bajada", tab_bajada)
        self.sidebar.add_item("Base Golpe", tab_golpe)
        self.sidebar.add_item("Ataque", tab_ataque)
        self.sidebar.add_item("Brake", tab_brake)
        self.sidebar.add_item("Legacy", tab_legacy)

        self.sidebar.add_section("MONITORING")
        if self.cues_tab:
            self.sidebar.add_item("Cues Monitor", self.cues_tab)
        self.sidebar.add_item("Health", tab_health)

        self.sidebar.add_section("SYSTEM")
        self.sidebar.add_item("Red / Consola", tab_net)
        if self.clock_widget:
            self.sidebar.add_item("Tempo", self.clock_widget)
        if getattr(self, 'calendar_tab', None):
            self.sidebar.add_item("Calendario", self.calendar_tab)

        self.sidebar.add_section("VISION")
        if getattr(self, 'vision_haze_tab', None):
            self.sidebar.add_item("Vision Haze", self.vision_haze_tab)
        if getattr(self, 'vision_dj_tab', None):
            self.sidebar.add_item("Vision DJ", self.vision_dj_tab)
        if getattr(self, 'vision_artist_tab', None):
            self.sidebar.add_item("Vision Artist", self.vision_artist_tab)

        self.sidebar.finish()

        # -- Main layout: TopBar + (Sidebar | ViewStack) ---------------------
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout(body)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(top)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addWidget(self.sidebar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(self.view_stack)
        scroll.setWidget(page)
        content_row.addWidget(scroll, 1)

        main_layout.addLayout(content_row, 1)
        self.setCentralWidget(body)

        # V13: Audio controls removed from top bar - use Red/Consola tab instead
        # Audio section connections
        self.btn_audio_connect.clicked.connect(self._on_audio_connect)
        self.btn_audio_disconnect.clicked.connect(self._on_audio_disconnect)

        # LOAD SHOW section connections
        self.btn_show_browse.clicked.connect(self._on_show_browse)
        self.btn_show_load.clicked.connect(self._on_show_load)
        self.btn_show_save.clicked.connect(self._on_show_save)

        self._mount_waveform("bajada")
        self._refresh_nics()

        # Kiosk geometry: set to physical screen size and show (no showFullScreen)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.show()

    # ========== HELPERS DE PERSISTENCIA ==========

    def _get_preset_abs_path(self):
        """
        Return ABSOLUTE path to preset file, anchored to main.py directory.
        This fixes Windows CWD issues where relative paths write to wrong location.
        """
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "presetv10 bajada v54.json")

    def _load_preset(self, path):
        """Carga preset JSON completo"""
        try:
            abs_path = os.path.abspath(path)
            with open(abs_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[NET][ERR] Error cargando preset {path}: {e}")
            return {}
    
    def _save_preset(self, path, data):
        """Guarda preset JSON completo"""
        try:
            abs_path = os.path.abspath(path)
            print(f"[AUDIT] PRESET WRITE path={abs_path} cwd={os.getcwd()}")
            with open(abs_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            # Post-save verification
            nic = data.get("net_panel", {}).get("nic", {})
            print(f"[NIC] POST_WRITE: name={nic.get('local_nic_name')} ip={nic.get('local_ip')} id={nic.get('local_nic_id')}")
            return True
        except Exception as e:
            print(f"[NET][ERR] Error guardando preset: {e}")
            return False
    
    def _ensure_net_panel_defaults(self, data):
        """
        Crea bloque net_panel con defaults si no existe.
        Incluye migración de keys viejas (local_nic, local_ip, local_nic_id) a net_panel.nic block.
        """
        if "net_panel" not in data:
            data["net_panel"] = {
                "enabled": True,
                "console_ip": "10.0.0.1",
                "console_port": 4430,
                "cue_offset": 169,
                "auto_retry": True,
                "transport": "http",
                "audio": {
                    "input_device_name": None,
                    "input_device_index": None,
                    "sample_rate": 48000,
                    "auto_connect": True
                },
                "nic": {
                    "local_nic_name": "auto",
                    "local_nic_id": "",
                    "local_ip": "",
                    "auto_connect": True
                },
                "timeouts": {"connect_ms": 1500, "send_ms": 300},
                "retries": {"max": 5, "backoff_ms": [500, 1000, 2000]},
                "ui": {"show_latency": True, "show_events": True}
            }
            if hasattr(self.avolites, 'set_transport'):
                data["net_panel"]["sacn"] = {"universe": 1, "priority": 100}
                data["net_panel"]["artnet"] = {"net": 0, "subnet": 0, "universe": 0}

        # Ensure audio block exists (migration)
        if "audio" not in data.get("net_panel", {}):
            data["net_panel"]["audio"] = {
                "input_device_name": None,
                "input_device_index": None,
                "sample_rate": 48000,
                "auto_connect": True
            }

        # Ensure nic block exists (migration from old loose keys)
        if "nic" not in data.get("net_panel", {}):
            # Migrate from old format: local_nic, local_ip, local_nic_id at root level
            net = data.get("net_panel", {})
            data["net_panel"]["nic"] = {
                "local_nic_name": net.get("local_nic", "auto"),
                "local_nic_id": net.get("local_nic_id", ""),
                "local_ip": net.get("local_ip", ""),
                "auto_connect": True
            }
            print(f"[NIC] migrated old keys to net_panel.nic block")

        # Ensure cue_offset exists (migration)
        if "cue_offset" not in data.get("net_panel", {}):
            data["net_panel"]["cue_offset"] = 169

        return data
    
    def _merge_net_panel(self, data, patch):
        """Merge solo del bloque net_panel"""
        if "net_panel" not in data:
            data = self._ensure_net_panel_defaults(data)
        data["net_panel"].update(patch)
        return data

    # ========== PROFILE MANAGEMENT (SAFE SAVE/LOAD) ==========

    # Canonical base preset (DO NOT MODIFY)
    CANONICAL_BASE_PRESET = "presetv10 bajada v54.json"
    # Critical keys that must exist in a valid preset
    PRESET_CRITICAL_KEYS = {"version", "bajada", "base_golpe", "ataque", "brake", "enabled_flags"}
    # Minimum file size for a valid preset (bytes)
    PRESET_MIN_SIZE = 2000

    def _deep_merge(self, base, patch):
        """
        Recursively merge patch into base. Only updates keys present in patch.
        Does NOT delete keys that exist in base but not in patch.

        Args:
            base: Base dictionary (source of truth)
            patch: Patch dictionary (updates to apply)

        Returns:
            Merged dictionary (base is modified in place and returned)
        """
        if not isinstance(base, dict) or not isinstance(patch, dict):
            return patch

        for key, value in patch.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # Recursive merge for nested dicts
                self._deep_merge(base[key], value)
            else:
                # Overwrite or add key
                base[key] = value

        return base

    def _ensure_profile_exists(self):
        """
        Ensure the profile file exists. If not, clone from canonical base.

        Returns:
            bool: True if profile exists (or was created), False on error
        """
        try:
            # If profile already exists and has content, use it
            if os.path.exists(self.preset_path):
                size = os.path.getsize(self.preset_path)
                if size >= self.PRESET_MIN_SIZE:
                    # Verify it has critical keys
                    try:
                        data = self._load_preset(self.preset_path)
                        missing = self.PRESET_CRITICAL_KEYS - set(data.keys())
                        if not missing:
                            print(f"[PROFILE] using existing: {self.preset_path} ({size} bytes)")
                            return True
                        else:
                            print(f"[PROFILE][WARN] {self.preset_path} missing keys: {missing}")
                    except:
                        pass

            # Profile doesn't exist or is invalid - clone from canonical base
            base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.CANONICAL_BASE_PRESET)

            if not os.path.exists(base_path):
                print(f"[PROFILE][ERR] canonical base not found: {base_path}")
                return False

            # Load canonical base
            base_data = self._load_preset(base_path)
            if not base_data:
                print(f"[PROFILE][ERR] failed to load canonical base")
                return False

            # Extend net_panel with new fields
            base_data = self._ensure_net_panel_defaults(base_data)

            # Save as new profile
            if self._safe_save_preset(self.preset_path, base_data):
                print(f"[PROFILE] created from canonical base: {self.preset_path}")
                return True
            else:
                print(f"[PROFILE][ERR] failed to create profile")
                return False

        except Exception as e:
            print(f"[PROFILE][ERR] _ensure_profile_exists: {e}")
            return False

    def _safe_save_preset(self, path, data):
        """
        Safely save preset with validation and atomic write.

        Checks:
        - Data has critical keys
        - Serialized size >= minimum
        - Atomic write (temp file + rename)

        Args:
            path: Target file path
            data: Preset data dictionary

        Returns:
            bool: True if save succeeded
        """
        # Normalize to absolute path (Windows CWD fix)
        abs_path = os.path.abspath(path)
        print(f"[AUDIT] PRESET WRITE path={abs_path} cwd={os.getcwd()}")
        try:
            # Validate critical keys
            missing = self.PRESET_CRITICAL_KEYS - set(data.keys())
            if missing:
                print(f"[PROFILE][ERR] refusing to save - missing keys: {missing}")
                return False

            # Serialize to string first to check size
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            if len(json_str) < self.PRESET_MIN_SIZE:
                print(f"[PROFILE][ERR] refusing to save - too small: {len(json_str)} bytes (min {self.PRESET_MIN_SIZE})")
                return False

            # Atomic write: write to temp file, then rename
            temp_path = abs_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(json_str)

            # Rename temp to final (atomic on most filesystems)
            if os.path.exists(abs_path):
                os.replace(temp_path, abs_path)
            else:
                os.rename(temp_path, abs_path)

            # Post-save verification
            nic = data.get("net_panel", {}).get("nic", {})
            print(f"[NIC] POST_WRITE: name={nic.get('local_nic_name')} ip={nic.get('local_ip')} id={nic.get('local_nic_id')}")
            print(f"[PROFILE] saved: {abs_path} ({len(json_str)} bytes)")
            return True

        except Exception as e:
            print(f"[PROFILE][ERR] _safe_save_preset: {e}")
            # Clean up temp file if it exists
            try:
                temp_cleanup = abs_path + ".tmp"
                if os.path.exists(temp_cleanup):
                    os.remove(temp_cleanup)
            except:
                pass
            return False

    def _collect_ui_state_patch(self):
        """
        Collect current UI state as a patch dictionary.
        Only includes fields that should be persisted.

        Returns:
            dict: Patch with modules, flags, and net_panel
        """
        patch = {
            "version": 15,
            "architecture": "modular_v4.2",
            "cue_engine_modular_v42": True,
            "brake_analyzer_real": True,
        }

        # Collect module states
        try:
            patch["bajada"] = {m.name: m.card.to_preset() for m in self.modules_bajada if hasattr(m, "card")}
            patch["base_golpe"] = {m.name: m.card.to_preset() for m in self.modules_golpe if hasattr(m, "card")}
            patch["ataque"] = {m.name: m.card.to_preset() for m in self.modules_ataque if hasattr(m, "card")}
            patch["brake"] = {m.name: m.card.to_preset() for m in self.modules_brake if hasattr(m, "card")}
            patch["enabled_flags"] = {
                m.name: getattr(m, 'active', True)
                for m in (self.modules_bajada + self.modules_golpe + self.modules_ataque + self.modules_brake)
            }
        except Exception as e:
            print(f"[PROFILE][WARN] error collecting modules: {e}")

        # Collect net_panel state
        try:
            net_patch = {}

            # Console config
            if hasattr(self, 'ed_console_ip'):
                net_patch["console_ip"] = self.ed_console_ip.text().strip() or "10.0.0.1"
            if hasattr(self, 'ed_console_port'):
                net_patch["console_port"] = int(self.ed_console_port.text().strip() or "4430")
            if hasattr(self, 'spin_cue_offset'):
                net_patch["cue_offset"] = self.spin_cue_offset.value()
            if hasattr(self, 'chk_auto_retry'):
                net_patch["auto_retry"] = self.chk_auto_retry.isChecked()

            # Transport
            if hasattr(self, '_get_current_transport'):
                net_patch["transport"] = self._get_current_transport()

            # NIC config (nested block like audio)
            if hasattr(self, 'cmb_nic'):
                nic_data = self.cmb_nic.currentData()
                # Read auto_connect from checkbox (defaults to True)
                nic_auto_connect = True
                if hasattr(self, 'chk_nic_auto_connect'):
                    nic_auto_connect = self.chk_nic_auto_connect.isChecked()

                if nic_data and len(nic_data) >= 3:
                    name, ip, mac, *_ = nic_data
                    if name == "auto":
                        # Auto mode: clear NIC config
                        net_patch["nic"] = {
                            "local_nic_name": "auto",
                            "local_nic_id": "",
                            "local_ip": "",
                            "auto_connect": nic_auto_connect
                        }
                    else:
                        # Generate stable ID (MAC or hash fallback)
                        stable_id = self._generate_stable_nic_id(name, ip, mac)
                        net_patch["nic"] = {
                            "local_nic_name": name,
                            "local_nic_id": stable_id,
                            "local_ip": ip or "",
                            "auto_connect": nic_auto_connect
                        }

            # Audio config
            if hasattr(self, 'cmb_audio_device'):
                idx = self.cmb_audio_device.currentData()
                text = self.cmb_audio_device.currentText()
                sr = 48000
                if self.engine:
                    sr = getattr(self.engine, 'samplerate', None) or getattr(self.engine, 'sr', None) or 48000
                net_patch["audio"] = {
                    "input_device_name": text.split(" ", 1)[1] if " " in text else text,
                    "input_device_index": idx,
                    "sample_rate": sr,
                    "auto_connect": True
                }

            if net_patch:
                patch["net_panel"] = net_patch

        except Exception as e:
            print(f"[PROFILE][WARN] error collecting net_panel: {e}")

        return patch

    def _populate_audio_devices(self):
        """Populate audio device combobox"""
        try:
            self.cmb_audio_device.clear()
            for i, d in enumerate(sd.query_devices()):
                if d.get('max_input_channels', 0) > 0:
                    self.cmb_audio_device.addItem(f"#{i} {d['name']}", i)
        except Exception as e:
            print(f"[AUDIO] Error listing devices: {e}")

    def _on_audio_connect(self):
        """Connect to selected audio device using canonical start() method."""
        try:
            idx = self.cmb_audio_device.currentData()
            if idx is None:
                QMessageBox.warning(self, "Audio", "Selecciona un dispositivo de audio")
                return

            # Stop existing engine if running
            if hasattr(self, 'engine') and self.engine:
                self.stop()

            # Use canonical start() - this initializes the full pipeline:
            # engine + AudioMonitor + waveform + _clock + _acc + t_frame
            self.start(device_index=idx)

            # Verify engine actually started
            if not self.engine:
                self.lbl_audio_status.setText("● Error al conectar")
                self.lbl_audio_status.setStyleSheet("color:#e74c3c; font-weight:700;")
                return

            # Update Red/Consola UI labels (start() updates top bar only)
            sr = getattr(self.engine, 'samplerate', None) or getattr(self.engine, 'sr', None) or 48000
            self.lbl_audio_status.setText("● Conectado")
            self.lbl_audio_status.setStyleSheet("color:#27ae60; font-weight:700;")
            self.lbl_audio_sr.setText(f"SR: {sr} Hz")

            print(f"[AUDIO] Pipeline started: device=#{idx} sr={sr} t_frame=running")

        except Exception as e:
            self.lbl_audio_status.setText(f"● Error: {e}")
            self.lbl_audio_status.setStyleSheet("color:#e74c3c; font-weight:700;")
            print(f"[AUDIO] Connect error: {e}")

    def _on_audio_disconnect(self):
        """Disconnect audio device"""
        try:
            if hasattr(self, 'engine') and self.engine:
                self.stop()
            self.lbl_audio_status.setText("● Desconectado")
            self.lbl_audio_status.setStyleSheet("color:#e74c3c; font-weight:700;")
            self.lbl_audio_sr.setText("SR: —")
            self.lbl_audio_db.setText("dBFS: —")
            self.lbl_info.setText("🎙 Sin conectar")
            print("[AUDIO] Disconnected")
        except Exception as e:
            print(f"[AUDIO] Disconnect error: {e}")

    # ========== LOAD SHOW HANDLERS ==========

    def _on_show_browse(self):
        """Browse for a different preset file"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Elegir Perfil",
            os.path.dirname(self.preset_path) or ".",
            "JSON (*.json)"
        )
        if filename:
            self.preset_path = filename
            self.txt_show_path.setText(filename)
            print(f"[SHOW] Selected preset: {filename}")

    def _on_show_load(self):
        """Load preset from self.preset_path"""
        # Ensure profile exists (clone from v54 if needed)
        self._ensure_profile_exists()

        if not os.path.exists(self.preset_path):
            QMessageBox.warning(self, "Load Show", f"Archivo no encontrado:\n{self.preset_path}")
            return

        try:
            # Load and apply preset
            self.load_preset(filepath=self.preset_path)
            QMessageBox.information(self, "Load Show", f"Perfil cargado:\n{os.path.basename(self.preset_path)}")
            print(f"[SHOW] Loaded preset: {self.preset_path}")
        except Exception as e:
            QMessageBox.critical(self, "Load Show", f"Error cargando perfil:\n{e}")
            print(f"[SHOW] Load error: {e}")

    def _on_show_save(self):
        """Save current state to self.preset_path"""
        try:
            self.save_preset(filepath=self.preset_path)
            QMessageBox.information(self, "Save Show", f"Perfil guardado:\n{os.path.basename(self.preset_path)}")
            print(f"[SHOW] Saved preset: {self.preset_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Show", f"Error guardando perfil:\n{e}")
            print(f"[SHOW] Save error: {e}")

    def _startup_auto_apply(self):
        """
        Apply profile settings on startup (autonomous boot).

        V14 Boot Sequence (100ms):
        1. Ensure profile exists (clone from v54 if needed)
        2. FULL LOAD: load_preset() applies modules/analyzers/enabled_flags
        3. Apply audio config + auto-connect
        4. Apply NIC config (BEFORE Titan connect)
        5. Apply Avolites config + auto-connect

        Note: Cues are handled separately in _execute_bootstrap (500ms).
        """
        try:
            print("[PROFILE] ========== STARTUP AUTO-APPLY ==========")
            print(f"[AUDIT] preset_path={self.preset_path} exists={os.path.exists(self.preset_path)} cwd={os.getcwd()}")

            # Ensure profile exists (clone from canonical v54 if needed)
            self._ensure_profile_exists()

            if not os.path.exists(self.preset_path):
                print(f"[PROFILE] Preset not found: {self.preset_path}")
                return

            # ============================================================
            # PHASE 1: FULL PRESET LOAD (modules, analyzers, enabled_flags)
            # This is the KEY step that applies all module configurations!
            # ============================================================
            try:
                self._load_preset_silent(self.preset_path)
                print(f"[PROFILE] preset applied: modules/analyzers/flags OK")
            except Exception as e:
                print(f"[PROFILE] preset load error: {e}")

            # ============================================================
            # PHASE 2: NET_PANEL (audio, NIC, avolites)
            # ============================================================
            data = self._load_preset(self.preset_path)
            data = self._ensure_net_panel_defaults(data)
            net = data.get("net_panel", {})
            nic_cfg = net.get("nic", {})
            print(f"[PROFILE] loaded net_panel from {self.preset_path}")
            print(f"[NIC] loaded: name={nic_cfg.get('local_nic_name')} ip={nic_cfg.get('local_ip')} id={nic_cfg.get('local_nic_id')}")

            # Apply audio config (with wait for USB device)
            audio_cfg = net.get("audio", {})
            if audio_cfg.get("auto_connect", True):
                device_name = audio_cfg.get("input_device_name")
                print(f"[AUDIO] Preset audio config: name='{device_name}' idx={audio_cfg.get('input_device_index')}")

                # Build search keywords — only use saved name if it's specific
                # (not "default", "hw:", etc.). Always include hardware identifiers.
                keywords = ["PS22", "Maono"]
                if device_name and device_name.lower() not in _GENERIC_DEVICE_NAMES:
                    keywords = [device_name] + keywords

                # Wait for USB audio device to appear in ALSA
                # NOTE: input_device_index is intentionally ignored — ALSA indices
                # are volatile across reboots and would select the wrong device.
                target_idx, found_name = wait_for_audio_device(
                    keywords=keywords, timeout=15.0, poll_interval=1.0
                )

                if target_idx is not None:
                    try:
                        self._start_with_retry(device_index=target_idx, max_retries=10, retry_interval=2.0)

                        if self.engine:
                            sr = getattr(self.engine, 'samplerate', None) or getattr(self.engine, 'sr', None) or 48000
                            print(f"[AUDIO] Audio engine started: device=#{target_idx} '{found_name}' sr={sr}")

                            # Update Red/Consola UI labels
                            if hasattr(self, 'cmb_audio_device'):
                                for i in range(self.cmb_audio_device.count()):
                                    if self.cmb_audio_device.itemData(i) == target_idx:
                                        self.cmb_audio_device.setCurrentIndex(i)
                                        break
                                self.lbl_audio_status.setText("● Conectado")
                                self.lbl_audio_status.setStyleSheet("color:#27ae60; font-weight:700;")
                                self.lbl_audio_sr.setText(f"SR: {sr} Hz")
                        else:
                            print(f"[AUDIO] Audio connect failed for device #{target_idx}")
                    except Exception as e:
                        print(f"[AUDIO] Audio connect error: {e}")
                else:
                    print("[AUDIO] WARNING: Maono PS22 not found. System running without audio.")
                    print("[AUDIO] Connect the device and use Red/Consola tab to start manually.")

            # Apply Avolites config (without connecting yet)
            console_ip = net.get("console_ip", "10.0.0.1")
            console_port = net.get("console_port", 4430)
            cue_offset = net.get("cue_offset", 169)
            transport = net.get("transport", "http")

            self.avolites.config_manager.config["console_ip"] = console_ip
            self.avolites.config_manager.config["console_port"] = console_port

            if hasattr(self.avolites, 'set_cue_offset'):
                self.avolites.set_cue_offset(cue_offset)

            # Apply NIC config BEFORE connecting (same pattern as audio)
            nic_cfg = net.get("nic", {})
            local_nic_id = nic_cfg.get("local_nic_id", "")
            local_ip = nic_cfg.get("local_ip", "")
            local_nic_name = nic_cfg.get("local_nic_name", "auto")
            nic_auto_connect = nic_cfg.get("auto_connect", True)

            # P0 audit: log loaded NIC config
            print(f"[NET] loaded nic -> ip={local_ip} name={local_nic_name} auto={nic_auto_connect}")

            nic_applied = False
            if nic_auto_connect and (local_nic_id or local_ip):
                # Find NIC by MAC first, fallback to IP
                nic_found = self._find_nic_by_id(local_nic_id, local_ip)
                if nic_found:
                    name, ip, mac, up = nic_found
                    # P0 audit: log applying NIC bind BEFORE Titan connect
                    print(f"[NET] applying nic bind -> {name} ({ip}) [before Titan connect]")
                    # Set local_ip_effective BEFORE connecting
                    self.local_ip_effective = ip
                    # Configure avolites with local interface
                    if ip:
                        self.avolites.set_local_interface(ip)

                    # Update combo selection (block signals to prevent re-save during boot)
                    if hasattr(self, 'cmb_nic'):
                        self.cmb_nic.blockSignals(True)
                        for i in range(self.cmb_nic.count()):
                            item_data = self.cmb_nic.itemData(i)
                            if item_data and len(item_data) >= 3:
                                if mac and item_data[2] and item_data[2].lower() == mac.lower():
                                    self.cmb_nic.setCurrentIndex(i)
                                    break
                        self.cmb_nic.blockSignals(False)
                    if hasattr(self, 'lbl_local_ip'):
                        self.lbl_local_ip.setText(ip if ip else "Auto")
                    print(f"[NIC] selected: name={name} ip={ip} id={local_nic_id}")
                    nic_applied = True
                else:
                    print(f"[NIC] not found: id={local_nic_id} ip={local_ip}")
            else:
                print(f"[NET] NIC config: auto (no saved NIC)")

            # Now connect to Titan (only once)
            if net.get("auto_retry", True):
                try:
                    print(f"[TITAN] connecting to {console_ip}:{console_port} from {self.local_ip_effective or 'auto'}")
                    self.avolites.connect()
                    print(f"[PROFILE] avolites connected: {console_ip}:{console_port} [{transport}] offset={cue_offset}")
                except Exception as e:
                    print(f"[PROFILE] avolites connect error (will retry): {e}")

            print("[PROFILE] ========== STARTUP COMPLETE ==========")

        except Exception as e:
            print(f"[PROFILE] Startup auto-apply error: {e}")
            import traceback
            traceback.print_exc()

    def _load_net_panel_from_preset(self):
        """Carga configuración de red desde preset al inicio"""
        try:
            if not os.path.exists(self.preset_path):
                print(f"[NET] Preset no encontrado: {self.preset_path}")
                return
            
            data = self._load_preset(self.preset_path)
            data = self._ensure_net_panel_defaults(data)
            net = data.get("net_panel", {})
            
            self.ed_console_ip.setText(str(net.get("console_ip", "10.0.0.1")))
            self.ed_console_port.setText(str(net.get("console_port", 4430)))
            self.chk_auto_retry.setChecked(bool(net.get("auto_retry", True)))
            
            transport = net.get("transport", "http")
            if transport == "http":
                self.radio_http.setChecked(True)
            elif transport == "artnet":
                self.radio_artnet.setChecked(True)
            elif transport == "sacn":
                self.radio_sacn.setChecked(True)
            
            if hasattr(self.avolites, 'set_transport'):
                if transport == "sacn":
                    sacn = net.get("sacn", {})
                    self.spin_sacn_universe.setValue(sacn.get("universe", 1))
                    self.spin_sacn_priority.setValue(sacn.get("priority", 100))
                elif transport == "artnet":
                    artnet = net.get("artnet", {})
                    self.spin_artnet_net.setValue(artnet.get("net", 0))
                    self.spin_artnet_subnet.setValue(artnet.get("subnet", 0))
                    self.spin_artnet_universe.setValue(artnet.get("universe", 0))

            # Cargar cue offset desde profile (net_panel.cue_offset)
            try:
                offset = int(net.get("cue_offset", 169))
                self.spin_cue_offset.setValue(offset)
                self._on_cue_offset_changed()  # Actualizar ejemplo
                # Sync to avolites
                if hasattr(self.avolites, 'set_cue_offset'):
                    self.avolites.set_cue_offset(offset)
            except Exception as e:
                print(f"[NET] Error cargando cue_offset: {e}")

            # Cargar audio device desde profile (net_panel.audio)
            try:
                audio_cfg = net.get("audio", {})
                device_name = audio_cfg.get("input_device_name")
                device_idx = audio_cfg.get("input_device_index")

                # Seleccionar device en combo si existe
                if hasattr(self, 'cmb_audio_device'):
                    found = False
                    if device_name:
                        for i in range(self.cmb_audio_device.count()):
                            if device_name in self.cmb_audio_device.itemText(i):
                                self.cmb_audio_device.setCurrentIndex(i)
                                found = True
                                break
                    if not found and device_idx is not None:
                        for i in range(self.cmb_audio_device.count()):
                            if self.cmb_audio_device.itemData(i) == device_idx:
                                self.cmb_audio_device.setCurrentIndex(i)
                                break
                print(f"[PROFILE] audio config loaded: device={device_name}")
            except Exception as e:
                print(f"[PROFILE] Error loading audio: {e}")

            self.avolites.config_manager.config["console_ip"] = str(net.get("console_ip", "10.0.0.1"))
            self.avolites.config_manager.config["console_port"] = int(net.get("console_port", 4430))

            # Load NIC config from net_panel.nic block (same pattern as audio)
            try:
                nic_cfg = net.get("nic", {})
                local_nic_name = nic_cfg.get("local_nic_name", "auto")
                local_nic_id = nic_cfg.get("local_nic_id", "")
                local_ip = nic_cfg.get("local_ip", "")
                nic_auto_connect = nic_cfg.get("auto_connect", True)

                # Update auto_connect checkbox
                if hasattr(self, 'chk_nic_auto_connect'):
                    self.chk_nic_auto_connect.setChecked(nic_auto_connect)

                # Select NIC in combo if exists (same pattern as audio combo)
                if hasattr(self, 'cmb_nic'):
                    self.cmb_nic.blockSignals(True)  # Prevent combo change handler
                    found = False
                    # Priority 1: match by stable ID (MAC or hash)
                    if local_nic_id:
                        for i in range(self.cmb_nic.count()):
                            item_data = self.cmb_nic.itemData(i)
                            if item_data and len(item_data) >= 3:
                                name, ip, mac, *_ = item_data
                                item_id = self._generate_stable_nic_id(name, ip, mac)
                                if item_id.lower() == local_nic_id.lower():
                                    self.cmb_nic.setCurrentIndex(i)
                                    found = True
                                    break
                    # Priority 2: match by IP
                    if not found and local_ip:
                        for i in range(self.cmb_nic.count()):
                            item_data = self.cmb_nic.itemData(i)
                            if item_data and len(item_data) >= 2:
                                if item_data[1] == local_ip:
                                    self.cmb_nic.setCurrentIndex(i)
                                    found = True
                                    break
                    self.cmb_nic.blockSignals(False)

                # Update label
                if hasattr(self, 'lbl_local_ip'):
                    self.lbl_local_ip.setText(local_ip if local_ip else "Auto")

                # Set effective IP
                if local_ip:
                    self.avolites.config_manager.config["local_ip"] = local_ip
                    self.local_ip_effective = local_ip
                elif local_nic_id:
                    nic_found = self._find_nic_by_id(local_nic_id, None)
                    if nic_found:
                        self.avolites.config_manager.config["local_ip"] = nic_found[1]
                        self.local_ip_effective = nic_found[1]

                print(f"[NIC] config loaded: name={local_nic_name} ip={local_ip} id={local_nic_id}")
            except Exception as e:
                print(f"[NIC] Error loading nic config: {e}")

            self._add_net_event(f"Config cargada: {net.get('console_ip')}:{net.get('console_port')} [{transport}]")
            print(f"[NET] Config cargada desde preset")
            
        except Exception as e:
            print(f"[NET][ERR] Error cargando net_panel: {e}")
    
    # ========== HANDLERS DEL PANEL DE RED ==========
    
    def _on_save_reconnect(self):
        """Guardar destino de consola y reconectar"""
        try:
            ip = self.ed_console_ip.text().strip()
            port_str = self.ed_console_port.text().strip()
            
            # Validación IP
            if not ip:
                QMessageBox.warning(self, "Red", "IP de consola requerida")
                return
            parts = ip.split('.')
            if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                QMessageBox.warning(self, "Red", "IP inválida")
                return
            
            # Validación puerto
            try:
                port = int(port_str)
                if port < 1 or port > 65535:
                    raise ValueError()
            except:
                QMessageBox.warning(self, "Red", "Puerto inválido (1-65535)")
                return
            
            # Validación transporte vs puerto - BLOQUEO HTTP+6454
            transport = self._get_current_transport()
            if transport == "http" and port == 6454:
                QMessageBox.warning(
                    self, 
                    "Configuración inválida", 
                    "❌ Puerto 6454 es para Art-Net.\n\nPara Titan HTTP use puerto 4430."
                )
                return
            
            if not os.path.exists(self.preset_path):
                QMessageBox.warning(self, "Red", f"Preset no encontrado: {self.preset_path}")
                return
            
            # PERSISTIR en net_panel ANTES de cualquier operación
            data = self._load_preset(self.preset_path)
            data = self._ensure_net_panel_defaults(data)
            
            patch = {
                "console_ip": ip,
                "console_port": port,
                "auto_retry": self.chk_auto_retry.isChecked(),
                "transport": transport
            }
            data = self._merge_net_panel(data, patch)
            
            if not self._save_preset(self.preset_path, data):
                QMessageBox.critical(self, "Red", "Error guardando preset")
                return
            
            print(f"[NET] target set ip={ip} port={port} transport={transport}")
            
            # APLICAR configuración al controlador
            if hasattr(self.avolites, 'set_transport'):
                self.avolites.set_transport(transport)
            
            self.avolites.set_console_ip(ip)
            self.avolites.set_console_port(port)
            
            # SIEMPRE reconectar
            if hasattr(self.avolites, 'reconnect'):
                self.avolites.reconnect()
            elif hasattr(self.avolites, 'connect'):
                self.avolites.connect()
            
            self._add_net_event(f"Destino guardado: {ip}:{port} [{transport}]")
            QMessageBox.information(self, "Red", f"Destino guardado y aplicado:\n{ip}:{port}\nTransporte: {transport}")
            
        except Exception as e:
            print(f"[NET][ERR] {e}")
            QMessageBox.critical(self, "Red", f"Error: {e}")
    
    def _on_apply_nic(self):
        """
        Aplicar NIC seleccionada (mismo patrón que Conectar Audio).
        El botón hace: aplicar a runtime + guardar a preset.
        """
        try:
            idx = self.cmb_nic.currentIndex()
            if idx < 0:
                return

            nic_data = self.cmb_nic.currentData()
            if not nic_data:
                return

            name, ip, mac, up = nic_data
            stable_id = self._generate_stable_nic_id(name, ip, mac)
            auto_connect = self.chk_nic_auto_connect.isChecked() if hasattr(self, 'chk_nic_auto_connect') else True

            # Log: apply clicked
            print(f"[NIC] Guardar NIC clicked -> name={name} ip={ip} id={stable_id} auto_connect={auto_connect}")

            # Apply NIC to runtime
            success = self._apply_nic_config(name, ip, mac)

            if success:
                # Save to preset (same as audio button pattern)
                self.save_preset(filepath=self.preset_path)

                # Post-save verification: re-read and log (P0 audit requirement)
                try:
                    data = self._load_preset(self.preset_path)
                    saved_nic = data.get("net_panel", {}).get("nic", {})
                    print(f"[NET] saved nic -> {saved_nic}")
                except Exception as verify_err:
                    print(f"[NET][WARN] post-save verify failed: {verify_err}")

                self._add_net_event(f"NIC guardada: {name} ({ip})")
            else:
                self._add_net_event(f"NIC fallida: {name}")

        except Exception as e:
            print(f"[NIC][ERR] {e}")
            QMessageBox.critical(self, "Red", f"Error: {e}")

    def _on_nic_combo_changed(self, index):
        """
        Combo change handler (same pattern as audio combo).
        Changing combo only updates UI label - does NOT apply or save.
        Use the "Guardar NIC" button to apply + save.
        """
        if index < 0:
            return

        try:
            nic_data = self.cmb_nic.currentData()
            if not nic_data:
                return

            name, ip, mac, up = nic_data

            # Update UI label only (no apply, no save)
            if name == "auto":
                self.lbl_local_ip.setText("Auto")
            else:
                self.lbl_local_ip.setText(ip if ip else "—")

        except Exception as e:
            print(f"[NIC][ERR] _on_nic_combo_changed: {e}")

    def _generate_stable_nic_id(self, name, ip, mac):
        """
        Generate a stable ID for NIC matching across boots.
        Priority: MAC address > hash(name+ip)
        """
        import hashlib

        # If MAC exists and is valid, use it
        if mac and mac.strip() and mac != "00:00:00:00:00:00":
            return mac.lower()

        # Fallback: generate stable hash from name+ip
        if name and name != "auto":
            stable_str = f"{name}:{ip or '0.0.0.0'}"
            hash_id = hashlib.sha1(stable_str.encode()).hexdigest()[:16]
            return f"hash:{hash_id}"

        return ""

    def _apply_nic_config(self, name, ip, mac):
        """
        Apply NIC configuration to runtime (does NOT persist - use combo change for that).

        Args:
            name: NIC display name (for logging)
            ip: IP address to bind to
            mac: MAC address for stable identification

        Returns:
            bool: True if NIC was applied successfully
        """
        try:
            # Store effective IP for transport binding
            if name == "auto":
                self.local_ip_effective = None
                interface_value = None
            else:
                self.local_ip_effective = ip
                interface_value = ip  # Always use IP for binding (more reliable)

            # Apply to Avolites controller
            if interface_value:
                print(f"[NET] applying interface: {interface_value}")
                self.avolites.set_local_interface(interface_value)

            # Reconnect with new NIC
            if hasattr(self.avolites, 'reconnect'):
                self.avolites.reconnect()
            elif hasattr(self.avolites, 'connect'):
                self.avolites.connect()

            # Update UI
            self.lbl_local_ip.setText(ip if ip else "Auto")

            # Verify effective bind
            try:
                status = self.avolites.get_status()
                effective_ip = status.get("local_ip", ip)
                if effective_ip and effective_ip != ip:
                    print(f"[NET][WARN] requested bind={ip} but effective={effective_ip}")
                else:
                    print(f"[NET] bind OK: {effective_ip}")
            except:
                pass

            return True

        except Exception as e:
            print(f"[NET][ERR] _apply_nic_config: {e}")
            return False

    def _find_nic_by_id(self, nic_id, fallback_ip=None):
        """
        Find a NIC by its stable ID (MAC or hash) or fallback to IP.

        Args:
            nic_id: MAC address or hash:XXXX to search for
            fallback_ip: IP address to try if ID not found

        Returns:
            tuple: (name, ip, mac, up) or None if not found
        """
        try:
            if not NETWORK_UTILS_AVAILABLE:
                return None

            interfaces = list_interfaces()

            # First: try to match by ID
            if nic_id:
                nic_id_clean = nic_id.lower().strip()

                # Check if this is a hash-based ID
                if nic_id_clean.startswith("hash:"):
                    # Match by regenerating hash for each interface
                    for name, ip, mac, up in interfaces:
                        generated_id = self._generate_stable_nic_id(name, ip, mac)
                        if generated_id and generated_id.lower() == nic_id_clean:
                            print(f"[NET] selected nic by id/ip: {name} ({ip}) [hash match]")
                            return (name, ip, mac, up)
                else:
                    # Match by MAC address
                    for name, ip, mac, up in interfaces:
                        if mac and mac.lower().strip() == nic_id_clean:
                            print(f"[NET] selected nic by id/ip: {name} ({ip}) [{mac}]")
                            return (name, ip, mac, up)

            # Second: try to match by IP (fallback)
            if fallback_ip:
                ip_clean = fallback_ip.strip()
                for name, ip, mac, up in interfaces:
                    if ip and ip.strip() == ip_clean:
                        print(f"[NET] selected nic by id/ip: {name} ({ip}) [by IP]")
                        return (name, ip, mac, up)

            print(f"[NET] NIC not found: id={nic_id} ip={fallback_ip}")
            return None

        except Exception as e:
            print(f"[NET][ERR] _find_nic_by_id: {e}")
            return None

    def _is_ip_address(self, text):
        """Verifica si el texto es una dirección IPv4 válida"""
        try:
            parts = text.split('.')
            if len(parts) != 4:
                return False
            return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
        except:
            return False
    
    def _on_apply_transport(self):
        """Aplicar configuración de transporte"""
        try:
            if not hasattr(self.avolites, 'set_transport'):
                return
            
            transport = self._get_current_transport()
            
            if transport == "sacn":
                universe = self.spin_sacn_universe.value()
                priority = self.spin_sacn_priority.setValue()
                sub_params = {"universe": universe, "priority": priority}
            elif transport == "artnet":
                net = self.spin_artnet_net.value()
                subnet = self.spin_artnet_subnet.value()
                universe = self.spin_artnet_universe.value()
                sub_params = {"net": net, "subnet": subnet, "universe": universe}
            else:
                sub_params = {}
            
            if not os.path.exists(self.preset_path):
                QMessageBox.warning(self, "Red", f"Preset no encontrado: {self.preset_path}")
                return
            
            # PERSISTIR en net_panel
            data = self._load_preset(self.preset_path)
            data = self._ensure_net_panel_defaults(data)
            
            patch = {"transport": transport}
            if transport == "sacn":
                patch["sacn"] = sub_params
            elif transport == "artnet":
                patch["artnet"] = sub_params
            data = self._merge_net_panel(data, patch)
            
            if not self._save_preset(self.preset_path, data):
                QMessageBox.critical(self, "Red", "Error guardando preset")
                return
            
            print(f"[NET] transport set mode={transport}")
            self.avolites.set_transport(transport)
            
            # SIEMPRE reconectar después de cambiar transporte
            if hasattr(self.avolites, 'reconnect'):
                self.avolites.reconnect()
            
            self._add_net_event(f"Transporte: {transport}")
            QMessageBox.information(self, "Red", f"Transporte aplicado: {transport}")
            
        except Exception as e:
            print(f"[NET][ERR] {e}")
            QMessageBox.critical(self, "Red", f"Error: {e}")

    def _on_cue_offset_changed(self):
        """Actualizar ejemplo de mapeo cuando cambia el offset"""
        try:
            offset = self.spin_cue_offset.value()
            example_real = 1 + offset
            self.lbl_offset_example.setText(str(example_real))
        except:
            pass

    def _on_apply_cue_offset(self):
        """Aplicar offset de cues"""
        try:
            if not hasattr(self.avolites, 'set_cue_offset'):
                QMessageBox.warning(self, "Offset", "Método set_cue_offset no disponible")
                return

            offset = self.spin_cue_offset.value()

            # Aplicar en AvolitesController
            if self.avolites.set_cue_offset(offset):
                self._add_net_event(f"Cue Offset → {offset}")
                QMessageBox.information(
                    self,
                    "Offset Guardado",
                    f"✅ Offset aplicado: {offset}\n\nEjemplos de mapeo:\n" +
                    f"  Lógico 1 → Real {1+offset}\n" +
                    f"  Lógico 10 → Real {10+offset}\n" +
                    f"  Lógico 42 → Real {42+offset}"
                )
                print(f"[OFFSET] Aplicado offset={offset}")
            else:
                QMessageBox.warning(self, "Offset", "Error aplicando offset")

        except Exception as e:
            print(f"[OFFSET][ERR] {e}")
            QMessageBox.critical(self, "Offset", f"Error: {e}")

    def _get_current_transport(self):
        """Obtener transporte actual seleccionado"""
        if self.radio_http.isChecked():
            return "http"
        elif self.radio_artnet.isChecked():
            return "artnet"
        elif self.radio_sacn.isChecked():
            return "sacn"
        return "http"
    
    def _on_ping(self):
        """Ejecutar ping no bloqueante"""
        def _do_ping():
            try:
                ip = self.ed_console_ip.text().strip()
                if not ip:
                    return "FAIL: IP vacía", "#e74c3c"
                
                param = "-n" if platform.system().lower() == "windows" else "-c"
                cmd = ["ping", param, "3", "-w" if platform.system().lower() == "windows" else "-W", "500", ip]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, errors='replace')
                output = result.stdout + result.stderr
                
                if result.returncode == 0:
                    lines = output.split('\n')
                    times = []
                    for line in lines:
                        if 'time=' in line.lower() or 'tiempo=' in line.lower():
                            try:
                                import re
                                match = re.search(r'time[=<]\s*(\d+\.?\d*)', line.lower())
                                if match:
                                    times.append(float(match.group(1)))
                            except:
                                pass
                    
                    if times:
                        avg = sum(times) / len(times)
                        minv = min(times)
                        maxv = max(times)
                        loss = 3 - len(times)
                        return f"OK: {minv:.1f}/{avg:.1f}/{maxv:.1f}ms, pérdida {loss}/3", "#27ae60"
                    else:
                        return "OK (sin tiempos)", "#f39c12"
                else:
                    return "FAIL: Host no responde", "#e74c3c"
                    
            except subprocess.TimeoutExpired:
                return "FAIL: Timeout", "#e74c3c"
            except Exception as e:
                return f"Error: {str(e)[:40]}", "#e74c3c"
        
        def _update_ui(result_tuple):
            result, color = result_tuple
            self.lbl_ping_result.setText(result)
            if color:
                self.lbl_ping_result.setStyleSheet(f"color:{color};")
        
        self.lbl_ping_result.setText("Pinging...")
        self.lbl_ping_result.setStyleSheet("color:#f39c12;")
        
        thread = threading.Thread(target=lambda: _update_ui(_do_ping()), daemon=True)
        thread.start()
    
    def _on_net_reconnect(self):
        """Reconectar manualmente"""
        try:
            if hasattr(self.avolites, 'reconnect'):
                self.avolites.reconnect()
            elif hasattr(self.avolites, 'connect'):
                self.avolites.connect()
            self._add_net_event("Reconexión manual")
        except Exception as e:
            self._add_net_event(f"Error reconexión: {e}")
    
    def _on_net_stop(self):
        """Detener conexión"""
        try:
            if hasattr(self.avolites, 'stop'):
                self.avolites.stop()
            elif hasattr(self.avolites, 'kill_all_cues'):
                self.avolites.kill_all_cues()
            self._add_net_event("Conexión detenida")
        except Exception as e:
            self._add_net_event(f"Error deteniendo: {e}")
    
    def _on_net_refresh(self):
        """Refrescar lista de NICs"""
        self._refresh_nics()
        self._add_net_event("NICs refrescadas")
    
    def _on_transport_radio_changed(self):
        """Cambiar visibilidad de parámetros de transporte"""
        transport = self._get_current_transport()
        
        if transport == "sacn":
            self.sacn_params.setVisible(True)
            self.artnet_params.setVisible(False)
        elif transport == "artnet":
            self.sacn_params.setVisible(False)
            self.artnet_params.setVisible(True)
        else:
            self.sacn_params.setVisible(False)
            self.artnet_params.setVisible(False)
        
        # Auto-ajustar puerto según transporte
        current_port = self.ed_console_port.text().strip()
        if transport == "http" and current_port in ("6454", "0", ""):
            self.ed_console_port.setText("4430")
        elif transport == "artnet" and current_port in ("4430", "0", ""):
            self.ed_console_port.setText("6454")
    
    def _refresh_nics(self):
        """Refrescar lista de interfaces de red y seleccionar NIC guardada"""
        try:
            # Block signal to prevent overwriting saved NIC on selection
            self.cmb_nic.blockSignals(True)

            self.cmb_nic.clear()

            if NETWORK_UTILS_AVAILABLE:
                interfaces = list_interfaces()
            else:
                interfaces = [("Auto", "0.0.0.0", "00:00:00:00:00:00", True)]

            self.cmb_nic.addItem("● Auto (detectar automáticamente)", ("auto", "0.0.0.0", "", True))

            for name, ip, mac, up in interfaces:
                status = "🟢" if up else "🔴"
                label = f"{status} {name} ({ip}) [{mac[:17]}]"
                self.cmb_nic.addItem(label, (name, ip, mac, up))

            # Load saved NIC config from preset (from net_panel.nic block)
            saved_nic_id = ""
            saved_ip = ""
            try:
                if os.path.exists(self.preset_path):
                    data = self._load_preset(self.preset_path)
                    data = self._ensure_net_panel_defaults(data)
                    nic_cfg = data.get("net_panel", {}).get("nic", {})
                    saved_nic_id = nic_cfg.get("local_nic_id", "")
                    saved_ip = nic_cfg.get("local_ip", "")
                    print(f"[NIC] _refresh_nics: saved_id={saved_nic_id} saved_ip={saved_ip}")
            except:
                pass

            # Priority 1: Select by saved ID (MAC or hash)
            if saved_nic_id:
                saved_id_lower = saved_nic_id.lower().strip()

                # Handle hash-based IDs
                if saved_id_lower.startswith("hash:"):
                    for i in range(self.cmb_nic.count()):
                        item_data = self.cmb_nic.itemData(i)
                        if item_data and len(item_data) >= 3:
                            name, ip, mac, *_ = item_data
                            # Regenerate hash for this interface and compare
                            generated_id = self._generate_stable_nic_id(name, ip, mac)
                            if generated_id and generated_id.lower() == saved_id_lower:
                                self.cmb_nic.setCurrentIndex(i)
                                self.lbl_local_ip.setText(ip)
                                print(f"[NET] NIC selected by hash: {name} ({ip})")
                                self.cmb_nic.blockSignals(False)
                                return
                else:
                    # Handle MAC-based IDs
                    for i in range(self.cmb_nic.count()):
                        item_data = self.cmb_nic.itemData(i)
                        if item_data and len(item_data) >= 3:
                            mac = item_data[2]
                            if mac and mac.lower().strip() == saved_id_lower:
                                self.cmb_nic.setCurrentIndex(i)
                                self.lbl_local_ip.setText(item_data[1])
                                print(f"[NET] NIC selected by MAC: {item_data[0]} ({item_data[1]})")
                                self.cmb_nic.blockSignals(False)
                                return

            # Priority 2: Select by saved IP
            if saved_ip:
                saved_ip_clean = saved_ip.strip()
                for i in range(self.cmb_nic.count()):
                    item_data = self.cmb_nic.itemData(i)
                    if item_data and len(item_data) >= 2:
                        ip = item_data[1]
                        if ip and ip.strip() == saved_ip_clean:
                            self.cmb_nic.setCurrentIndex(i)
                            self.lbl_local_ip.setText(ip)
                            print(f"[NET] NIC selected by IP: {item_data[0]} ({ip})")
                            self.cmb_nic.blockSignals(False)
                            return

            # Priority 3: Select first 10.0.0.x NIC (Titan network) - NO PERSIST
            for i in range(self.cmb_nic.count()):
                item_data = self.cmb_nic.itemData(i)
                if item_data and len(item_data) >= 2:
                    ip = item_data[1]
                    if ip.startswith("10.0.0."):
                        self.cmb_nic.setCurrentIndex(i)
                        self.lbl_local_ip.setText(ip)
                        print(f"[NET] NIC selected by 10.0.0.x fallback: {item_data[0]} ({ip}) [NOT PERSISTED]")
                        self.cmb_nic.blockSignals(False)
                        return

            # Priority 4: Select first UP interface - NO PERSIST
            for i in range(1, self.cmb_nic.count()):
                item_data = self.cmb_nic.itemData(i)
                if item_data and len(item_data) >= 4 and item_data[3]:
                    self.cmb_nic.setCurrentIndex(i)
                    self.lbl_local_ip.setText(item_data[1])
                    print(f"[NET] NIC selected by first-UP fallback: {item_data[0]} [NOT PERSISTED]")
                    self.cmb_nic.blockSignals(False)
                    return

            self.cmb_nic.blockSignals(False)

        except Exception as e:
            self.cmb_nic.blockSignals(False)
            print(f"[NET][ERR] Error refrescando NICs: {e}")
    
    def _poll_net_status(self):
        """Actualizar estado de red periódicamente"""
        try:
            status = self.avolites.get_status()
            connected = status.get("connected", False)
            
            if connected:
                self.net_status_badge.setText("● Conectado")
                self.net_status_badge.setStyleSheet("color:#27ae60; font-weight:700; font-size:14px;")
            else:
                self.net_status_badge.setText("● Desconectado")
                self.net_status_badge.setStyleSheet("color:#e74c3c; font-weight:700; font-size:14px;")
            
            if hasattr(self.avolites, 'get_last_error'):
                err = self.avolites.get_last_error()
                if err:
                    self.lbl_last_error.setText(str(err)[:100])
                else:
                    self.lbl_last_error.setText("—")
            
        except Exception as e:
            print(f"[NET][ERR] Error polling status: {e}")
    
    def _add_net_event(self, msg):
        """Añadir evento a la lista (máx 5)"""
        timestamp = QDateTime.currentDateTime().toString("HH:mm:ss")
        self._net_events.append(f"[{timestamp}] {msg}")
        if len(self._net_events) > 5:
            self._net_events.pop(0)
        self.net_events_list.setText("\n".join(self._net_events))

    def _build_status_box(self, modules):
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#141418; border:1px solid #2e2e38; border-radius:12px;}")
        frame.setFixedHeight(65)
        layout = QGridLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        labels = {}
        cols = 6
        for i, m in enumerate(modules):
            r, c = divmod(i, cols)
            # Robustez: obtener name con fallback
            text = getattr(m, "name", m.__class__.__name__)
            lbl = QLabel(f"◯ {text}")
            lbl.setStyleSheet(
                "color:#777; font-weight:700; font-size:9px; "
                "padding:1px 4px; border:1px solid #2b2b2b; border-radius:3px; background:#0f0f0f;"
            )
            layout.addWidget(lbl, r, c)
            labels[text] = lbl
        return frame, labels

    def _refresh_status_box(self, labels_map, modules):
        for m in modules:
            try:
                on = False
                name = getattr(m, 'name', 'Unknown')
                
                is_inactive = getattr(m, 'is_placeholder', False) or getattr(m, 'disabled_by_preset', False)
                
                if not is_inactive and hasattr(m, 'card') and m.card:
                    if hasattr(m.card, 'is_on') and callable(m.card.is_on):
                        try:
                            on = bool(m.card.is_on())
                        except:
                            on = bool(getattr(m.card, '_on', False))
            except:
                on = False
            lbl = labels_map.get(name, None)
            if lbl:
                if is_inactive:
                    text = f"◯ {name}"
                    color = '#555'
                else:
                    text = f"{'◉' if on else '◯'} {name}"
                    color = '#00f08a' if on else '#777'
                
                if lbl.text() != text:
                    lbl.setText(text)
                    lbl.setStyleSheet(
                        f"color:{color}; font-weight:700; font-size:9px; "
                        "padding:1px 4px; border:1px solid #2b2b2b; border-radius:3px; background:#0f0f0f;"
                    )

    def _mount_waveform(self, tab_name):
        for name, host in self.waveform_hosts.items():
            if host.layout().count() > 0:
                widget = host.layout().itemAt(0).widget()
                if widget and widget == self.waveform:
                    if name != tab_name:
                        widget.setVisible(False)
        
        host = self.waveform_hosts.get(tab_name)
        if host:
            if host.layout().count() == 0 or host.layout().itemAt(0).widget() != self.waveform:
                if self.waveform.parent() is not None:
                    self.waveform.setParent(None)
                host.layout().addWidget(self.waveform)
            
            self.waveform.setVisible(True)
            self.waveform.show()

    def _on_tab_changed(self, idx):
        w = self.view_stack.currentWidget()
        if w is getattr(self, "tab_bajada", None):
            self._active_tab_name = "bajada"
        elif w is getattr(self, "tab_golpe", None):
            self._active_tab_name = "golpe"
        elif w is getattr(self, "tab_ataque", None):
            self._active_tab_name = "ataque"
        elif w is getattr(self, "tab_brake", None):
            self._active_tab_name = "brake"
        elif w is getattr(self, "tab_monitor", None):
            self._active_tab_name = "monitor"
        elif w is getattr(self, "cues_tab", None):
            self._active_tab_name = "cues"
        elif w is getattr(self, "tab_net", None):
            self._active_tab_name = "red"
        elif w is getattr(self, "tab_health", None):
            self._active_tab_name = "health"
        else:
            self._active_tab_name = "bajada"
        
        self._mount_waveform(self._active_tab_name)

    def start(self, device_index=None):
        """Start audio engine - CANONICAL method for audio pipeline.

        This is the ONLY method that should initialize audio. It sets up:
        - AudioEngine (stream)
        - AudioMonitor (consumers)
        - waveform samplerate
        - _clock and _acc (timing)
        - t_frame timer (main processing loop)

        V13: device_index parameter required (controls moved to Red/Consola tab).
        """
        if self.engine:
            print("[AUDIO] start() called but engine already running")
            return

        # V13: If no device_index provided, try from Red/Consola combo
        if device_index is None:
            if hasattr(self, 'cmb_audio_device'):
                device_index = self.cmb_audio_device.currentData()
            if device_index is None:
                print("[AUDIO] No device selected - use Red/Consola tab")
                return

        print(f"[AUDIO] start() device=#{device_index}")

        try:
            self.engine = AudioEngine(device_index=int(device_index), ring_seconds=3.0)
            self.engine.start()
            print(f"[AUDIO] stream opened OK")
        except Exception as e:
            QMessageBox.critical(self, "Audio", f"Error abriendo dispositivo:\n{e}")
            self.engine = None
            return

        # Initialize AudioMonitor (wires consumers to engine)
        try:
            config_path = os.path.join(BASE_DIR, "config", "audio_monitor.json")
            with open(config_path, "r") as f:
                monitor_config = json.load(f)
            self.audio_monitor = AudioMonitor(self.engine, monitor_config)
            print(f"[AUDIO] AudioMonitor wired OK")
        except Exception as e:
            print(f"[AUDIO_MONITOR] Error initializing: {e}")
            self.audio_monitor = None

        st = self.engine.get_status()
        sr = st['samplerate']
        bs = st['blocksize']
        self.lbl_info.setText(f"🎙 Dev #{device_index} | SR {sr} | BS {bs}")
        self.waveform.set_samplerate(sr)

        # Start timing and main processing loop
        self._clock.restart()
        self._acc = {k: 0.0 for k in self.CADENCE.keys()}
        self.t_frame.start()
        print(f"[AUDIO] t_frame started (main loop) sr={sr} bs={bs}")

    def _start_with_retry(self, device_index, max_retries=10, retry_interval=2.0):
        """Start audio engine with retry logic for USB devices.

        If the first start() fails (device not ready), retries up to max_retries
        times with retry_interval seconds between attempts.
        """
        for attempt in range(1, max_retries + 1):
            try:
                self.start(device_index=device_index)
                if self.engine:
                    return  # success
            except Exception as e:
                print(f"[AUDIO] Init attempt {attempt}/{max_retries} failed: {e}")

            if attempt < max_retries:
                print(f"[AUDIO] Retrying in {retry_interval}s...")
                time.sleep(retry_interval)

                # Clean up failed engine
                if self.engine:
                    try:
                        self.engine.stop()
                    except Exception:
                        pass
                    self.engine = None

        if not self.engine:
            print(f"[AUDIO] WARNING: Failed to start after {max_retries} attempts")

    def stop(self):
        self.t_frame.stop()

        if self.engine:
            try:
                self.engine.stop()
            except:
                pass
        self.engine = None
        self._first_audio_buffer_logged = False  # Reset for next start
        self.lbl_info.setText("🎙 Sin conectar")
        self.vu_db.setText("Nivel: - dBFS")
        self.waveform.clear()
        self.vu_main.setValue(0)
        print("[AUDIO] stopped")

    def calibrate(self):
        if self.engine:
            self.engine.calibrate_noise(1.0)

    def save_preset(self, filepath=None):
        """
        Save preset using safe merge strategy.

        Strategy:
        1. Load existing preset (or canonical base if not exists)
        2. Collect current UI state as patch
        3. Deep merge patch into base (preserves all existing keys)
        4. Validate and atomic write

        This NEVER creates an empty/partial preset.
        """
        if filepath:
            filename = filepath
        else:
            filename, _ = QFileDialog.getSaveFileName(self, "Guardar preset", "preset.json", "JSON (*.json)")
            if not filename:
                return

        try:
            # Step 1: Load base (existing preset or canonical base)
            base_data = None

            if os.path.exists(filename):
                base_data = self._load_preset(filename)
                # Verify base is valid
                if base_data and len(base_data) > 0:
                    missing = self.PRESET_CRITICAL_KEYS - set(base_data.keys())
                    if missing:
                        print(f"[PROFILE][WARN] existing file missing keys: {missing}")
                        base_data = None

            # Fallback to canonical base
            if not base_data:
                base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.CANONICAL_BASE_PRESET)
                if os.path.exists(base_path):
                    base_data = self._load_preset(base_path)
                    print(f"[PROFILE] using canonical base for save")
                else:
                    print(f"[PROFILE][ERR] canonical base not found: {base_path}")
                    QMessageBox.critical(self, "Error", "No se encontró el preset base canónico")
                    return

            if not base_data:
                print(f"[PROFILE][ERR] no base data available")
                QMessageBox.critical(self, "Error", "No hay datos base para guardar")
                return

            # Step 2: Collect current UI state as patch
            patch = self._collect_ui_state_patch()

            # Step 3: Deep merge (preserves existing keys not in patch)
            merged = self._deep_merge(base_data, patch)

            # Ensure net_panel has all required fields
            merged = self._ensure_net_panel_defaults(merged)

            # Step 4: Safe save with validation
            if self._safe_save_preset(filename, merged):
                print(f"[PROFILE] save_preset OK: {filename}")
            else:
                QMessageBox.critical(self, "Error", "Error guardando preset - ver consola")

        except Exception as e:
            print(f"[PROFILE][ERR] save_preset: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error guardando preset:\n{e}")

    def load_preset(self, filepath=None):
        """Load preset from file. If filepath not provided, shows file dialog."""
        if filepath:
            filename = filepath
        else:
            filename, _ = QFileDialog.getOpenFileName(self, "Cargar preset", "", "JSON (*.json)")
            if not filename:
                return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version", 1)
            if version < 10:
                reply = QMessageBox.question(
                    self, "Versión Antigua", 
                    f"Este preset es v{version}. ¿Cargar de todas formas?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
            enabled_flags = data.get("enabled_flags", {})
            
            groups = [
                ("bajada", self.modules_bajada),
                ("base_golpe", self.modules_golpe), 
                ("ataque", self.modules_ataque),
                ("brake", self.modules_brake)
            ]
            for group_key, modules in groups:
                group_data = data.get(group_key, {})
                by_name = {m.name: m for m in modules if hasattr(m, "card")}
                for name, cfg in group_data.items():
                    if name in by_name:
                        try:
                            by_name[name].card.from_preset(cfg)
                            
                            if name in enabled_flags:
                                is_enabled = enabled_flags[name]
                                if not is_enabled:
                                    by_name[name].disabled_by_preset = True
                                    by_name[name].active = False
                                    if hasattr(by_name[name].card, 'mark_as_disabled'):
                                        by_name[name].card.mark_as_disabled()
                            
                            if "enabled" in cfg and not cfg["enabled"]:
                                by_name[name].disabled_by_preset = True
                                by_name[name].active = False
                                if hasattr(by_name[name].card, 'mark_as_disabled'):
                                    by_name[name].card.mark_as_disabled()
                                    
                        except Exception as e:
                            print(f"[PRESET] Error {name}: {e}")
            
            self.preset_path = filename
            self._load_net_panel_from_preset()
            self._log_analyzer_stats()
            
            print(f"[PRESET] Cargado: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error:\n{e}")

    def _load_preset_silent(self, filepath):
        """
        Load preset silently (no dialogs). Used for boot autoload.
        Applies: modules, analyzers, enabled_flags, net_panel.
        """
        if not filepath or not os.path.exists(filepath):
            raise FileNotFoundError(f"Preset not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("version", 1)
        if version < 10:
            print(f"[PRESET][WARN] Loading old preset v{version}")

        enabled_flags = data.get("enabled_flags", {})

        groups = [
            ("bajada", self.modules_bajada),
            ("base_golpe", self.modules_golpe),
            ("ataque", self.modules_ataque),
            ("brake", self.modules_brake)
        ]

        modules_applied = 0
        for group_key, modules in groups:
            group_data = data.get(group_key, {})
            by_name = {m.name: m for m in modules if hasattr(m, "card")}
            for name, cfg in group_data.items():
                if name in by_name:
                    try:
                        by_name[name].card.from_preset(cfg)
                        modules_applied += 1

                        # Apply enabled_flags
                        if name in enabled_flags:
                            is_enabled = enabled_flags[name]
                            if not is_enabled:
                                by_name[name].disabled_by_preset = True
                                by_name[name].active = False
                                if hasattr(by_name[name].card, 'mark_as_disabled'):
                                    by_name[name].card.mark_as_disabled()

                        # Apply inline enabled flag
                        if "enabled" in cfg and not cfg["enabled"]:
                            by_name[name].disabled_by_preset = True
                            by_name[name].active = False
                            if hasattr(by_name[name].card, 'mark_as_disabled'):
                                by_name[name].card.mark_as_disabled()

                    except Exception as e:
                        print(f"[PRESET] Error applying {name}: {e}")

        self.preset_path = filepath
        self._load_net_panel_from_preset()
        self._log_analyzer_stats()

        print(f"[PRESET] autoload: {filepath} ({modules_applied} modules applied)")

    def _frame_tick(self):
        if not self.engine:
            return
        
        dt = self._clock.restart()
        
        for k in self._acc:
            self._acc[k] += dt

        # FIX 1+2: Kick detector with incremental read + real block_start_ts
        # Runs every tick (~33ms) for minimum latency. Reads only NEW samples.
        if hasattr(self, 'kick_detector') and self.kick_detector:
            try:
                kick_block, kick_ts, kick_sr = self.engine.read_new_for_kick()
                if kick_block is not None and kick_block.size > 0:
                    self.kick_detector.process_audio(kick_block, kick_sr, kick_ts)

                kicks = self.kick_detector.pop_all_kicks()
                for kt in kicks:
                    if hasattr(self, 'auto_clock') and self.auto_clock:
                        self.auto_clock.register_hit(kt)
                    if hasattr(self, 'clock_widget') and self.clock_widget:
                        self.clock_widget.pulse_kick()
                    if hasattr(self, 'tap_bridge') and self.tap_bridge:
                        self.tap_bridge.feed_kick(True)
                    # FIX 6: Count kicks for DEBUG_TEMPO
                    self._debug_tempo_kicks += 1
            except:
                pass

        # FIX 6: DEBUG_TEMPO=1 — 1 line/sec with pipeline telemetry
        if self._debug_tempo:
            import time as _time
            _now = _time.monotonic()
            if _now - self._debug_tempo_last >= 1.0:
                self._debug_tempo_last = _now
                _kicks_s = self._debug_tempo_kicks
                self._debug_tempo_kicks = 0
                _kd = getattr(self, 'kick_detector', None)
                _ac = getattr(self, 'auto_clock', None)
                _ts = getattr(self, 'tap_sender', None)
                _energy = _kd._last_energy if _kd else 0.0
                _thr = _kd._last_threshold if _kd else 0.0
                _bpm = _ac.get_bpm() if _ac else 0.0
                _int_ms = _ac.interval_ms if _ac else 0.0
                _lock = _ac.get_lock_state().value if _ac else "?"
                _hits = len(_ac.hit_times) if _ac else 0
                _bursts = _ts._bursts if _ts else 0
                print(f"[TEMPO] kicks/s={_kicks_s} energy={_energy:.4f} thr={_thr:.4f} int_ms={_int_ms:.1f} bpm={_bpm:.1f} lock={_lock} hits={_hits} bursts={_bursts}")

        block_modules = None
        block_scope = None
        
        needs_modules = self._acc["modules"] >= self.CADENCE["modules"]
        needs_scope = self._acc["scope"] >= self.CADENCE["scope"]
        needs_energy = self._acc["energy"] >= self.CADENCE["energy"]

        if needs_modules or needs_energy:
            block_modules = self.engine.get_recent(0.25)
            # Log first buffer received (once only)
            if block_modules is not None and block_modules.size > 0 and not self._first_audio_buffer_logged:
                self._first_audio_buffer_logged = True
                print(f"[AUDIO] first buffer received: {block_modules.size} samples")
        
        if needs_scope or needs_energy:
            block_scope = self.engine.get_recent(0.05)
        
        if needs_scope and block_scope is not None and block_scope.size > 0:
            self._acc["scope"] = 0.0
            try:
                _block = sanitize_audio(block_scope)
                if _block is not None:
                    self.waveform.push(_block, self.engine.samplerate)
            except:
                pass

        if self._acc["vu"] >= self.CADENCE["vu"]:
            self._acc["vu"] = 0.0
            self._update_vu()

        if needs_modules and block_modules is not None and block_modules.size > 0:
            self._acc["modules"] = 0.0
            try:
                self._process_modules_limited(block_modules)
            except:
                pass

        if needs_energy and block_scope is not None:
            self._acc["energy"] = 0.0
            self._update_energy(block_scope)

        if self._acc["cues"] >= self.CADENCE["cues"]:
            self._acc["cues"] = 0.0
            self._update_cue_engine()

        if self._acc["status"] >= self.CADENCE["status"]:
            self._acc["status"] = 0.0
            self._update_status_boxes()

        # Update audio monitor
        if hasattr(self, "audio_monitor") and self.audio_monitor:
            try:
                st = self.engine.get_status()
                rms = st.get("rms_raw", 0.0)
                self.audio_monitor.update(block_modules, rms)
            except:
                pass

        # Update AutoClock / TAP Tempo
        if hasattr(self, "auto_clock") and self.auto_clock:
            try:
                # Tick the clock
                if self.auto_clock.tick():
                    # Clock beat - pulse the LED
                    if hasattr(self, "clock_widget") and self.clock_widget:
                        self.clock_widget.pulse_clock()

                # Apply corrections periodically
                self.auto_clock.apply_correction()

                # Update widget display
                if hasattr(self, "clock_widget") and self.clock_widget:
                    self.clock_widget.update_display()

                # TapTempoSender: observe state and fire burst if needed
                if hasattr(self, "tap_sender") and self.tap_sender:
                    ui = self.auto_clock.get_ui_state()
                    self.tap_sender.update(ui.lock_state, ui.interval_ms)
            except:
                pass

    def _set_audio_processing_enabled(self, enabled: bool) -> None:
        """
        Callback del SystemBridge para habilitar/deshabilitar procesamiento de audio.

        Cuando está deshabilitado:
        - Los módulos de análisis musical NO procesan
        - El StateManager NO se actualiza
        - El CueEngine sigue corriendo pero con estados bloqueados
        - El waveform sigue actualizándose (visual)

        Args:
            enabled: True para habilitar, False para deshabilitar
        """
        was_enabled = getattr(self, '_audio_processing_enabled', True)
        self._audio_processing_enabled = enabled

        if was_enabled != enabled:
            status = "HABILITADO" if enabled else "DESHABILITADO"
            print(f"[MAIN] CALENDAR: Analisis musical {status} por calendario")

    def _process_modules_limited(self, block):
        try:
            block = sanitize_audio(block)
            if block is None:
                return

            sr = self.engine.samplerate

            # ===== CALENDAR BRIDGE: BYPASS DE ANÁLISIS MUSICAL =====
            # Si el análisis de audio está deshabilitado por el calendario,
            # no procesar módulos ni actualizar StateManager
            if not getattr(self, '_audio_processing_enabled', True):
                # Aún así, actualizar métricas básicas para el waveform
                return

            # Motor Real: Active modules that drive state machine
            active_modules = [
                *self._get_active_modules(self.modules_bajada),
                *self._get_active_modules(self.modules_golpe),
                *self._get_active_modules(self.modules_ataque)
            ]

            for module in active_modules:
                try:
                    module.process(block, sr)
                except:
                    pass

            # Procesar módulos brake
            for module in self._get_active_modules(self.modules_brake):
                try:
                    module.process(block, sr)
                except Exception as e:
                    print(f"[BRAKE] Error procesando {getattr(module, 'name', 'unknown')}: {e}")

            # V12: Process legacy modules (for UI display only, not for voting)
            legacy_modules = [
                *self._get_active_modules(self.modules_bajada_legacy),
                *self._get_active_modules(self.modules_golpe_legacy),
                *self._get_active_modules(self.modules_ataque_legacy),
                *self._get_active_modules(self.modules_brake_legacy)
            ]
            for module in legacy_modules:
                try:
                    module.process(block, sr)
                except:
                    pass

            # Music Structure Engine: process audio BEFORE StateManager
            if self.music_structure_engine is not None:
                try:
                    self.music_structure_engine.process(block, sr)
                    mse_state = self.music_structure_engine.get_state()
                    self.state_manager.update_music_structure(mse_state)
                except Exception:
                    pass
            # State manager update uses ONLY Motor Real modules (not legacy)
            try:
                self.state_manager.update(
                    self._get_active_modules(self.modules_bajada),
                    self._get_active_modules(self.modules_golpe),
                    self._get_active_modules(self.modules_ataque),
                    self._get_active_modules(self.modules_brake)
                )
            except:
                pass

            # V11: Actualizar flags de analizadores cada frame para votación en tiempo real
            try:
                if self.cue_engine and hasattr(self.cue_engine, 'm_bg') and self.cue_engine.m_bg:
                    self.cue_engine.m_bg.update_analyzer_flags()
            except:
                pass

            # V18: Kick processing moved to _frame_tick() — uses incremental read
            # with real block_start_ts (FIX 1+2). See _frame_tick().

        except Exception as e:
            print(f"[MAIN] Error módulos: {e}")

    def _update_energy(self, block):
        try:
            block = sanitize_audio(block)
            if block is not None and block.size > 0:
                self.energy_detector.process(block, self.engine.samplerate)
            if hasattr(self, "energy_widget") and self.energy_widget:
                self.energy_widget.update_display()
        except:
            pass

    def _update_cue_engine(self):
        """
        Actualiza el CueEngine - SIEMPRE CORRE EL ENGINE.
        
        FIX v4.11: Eliminado el bloqueo "if total_updates == 0" que impedía
        que el engine corriera. Ahora siempre llama a update() si el método existe.
        El CueEngine decide internamente si puede disparar cues basándose en su
        lógica y estado. No bloqueamos desde el main loop.
        """
        if not self.cue_engine:
            return
        try:
            # SIEMPRE correr el engine si tiene el método update
            # El engine/transporte decide si puede enviar comandos
            if hasattr(self.cue_engine, 'update'):
                try:
                    self.cue_engine.update()
                except Exception as e:
                    # Log solo si es verbose, no bloquear el loop
                    pass
            
            # Actualizar widget de debug
            if hasattr(self, 'cues_debug_widget') and self.cues_debug_widget:
                self.cues_debug_widget.update_display()
        except:
            pass

    def _update_vu(self):
        try:
            st = self.engine.get_status()
            rms = st.get("rms_raw", 0.0)
            db = dbfs(rms)
            new_text = f"Nivel: {db:.1f} dBFS"
            if self._vu_last_text != new_text:
                self._vu_last_text = new_text
                self.vu_db.setText(new_text)
            v = int(round(max(0.0, min(1.0, float(rms))) * 1000))
            if self._vu_last_val != v:
                self._vu_last_val = v
                self.vu_main.setValue(v)
        except:
            pass

    def _update_status_boxes(self):
        try:
            tab = getattr(self, "_active_tab_name", "bajada")
            
            if tab == "bajada":
                self._refresh_status_box(self._labels_bajada, self.modules_bajada)
            elif tab == "golpe":
                self._refresh_status_box(self._labels_golpe, self.modules_golpe)
            elif tab == "ataque":
                self._refresh_status_box(self._labels_ataque, self.modules_ataque)
            elif tab == "brake":
                self._refresh_status_box(self._labels_brake, self.modules_brake)
            elif tab == "monitor":
                self._refresh_status_box(self._labels_bajada, self.modules_bajada)
                self._refresh_status_box(self._labels_golpe, self.modules_golpe)
                self._refresh_status_box(self._labels_ataque, self.modules_ataque)
                self._refresh_status_box(self._labels_brake, self.modules_brake)
            
            if self.state_widget and hasattr(self.state_widget, 'update_display'):
                self.state_widget.update_display()
        except:
            pass

    def _update_vision_ui(self):
        """Update Vision System UI (haze bar) from VisionState"""
        try:
            if not self.vision_manager or not self.haze_bar:
                return

            vision_state = self.vision_manager.get_state()
            haze_data = vision_state.get("haze", {})
            haze_level = haze_data.get("level", 0.0)

            # Update haze bar with current level (0-100)
            self.haze_bar.setValue(int(haze_level))

        except Exception as e:
            # Silently fail to avoid spamming logs
            pass


    def closeEvent(self, event):
        try:
            if hasattr(self, 't_frame'):
                self.t_frame.stop()
            if hasattr(self, '_net_timer'):
                self._net_timer.stop()
            if hasattr(self, '_loop_probe'):
                self._loop_probe.stop()
            if hasattr(self, '_health_timer'):
                self._health_timer.stop()
            if hasattr(self, 't_vision') and self.t_vision:
                self.t_vision.stop()
            if self.vision_manager:
                try:
                    self.vision_manager.stop()
                    print("[MAIN] VisionManager detenido correctamente")
                except Exception as e:
                    print(f"[MAIN] Error deteniendo VisionManager: {e}")
            if self.cue_engine:
                try:
                    self.cue_engine.stop_auto_update()
                    if hasattr(self.cue_engine, 'reset'):
                        self.cue_engine.reset()
                except:
                    pass
            if self.engine:
                try:
                    self.engine.stop()
                except:
                    pass
                self.engine = None
        except:
            pass
        super().closeEvent(event)

if __name__ == "__main__":
    import traceback
    try:
        print("=" * 60)
        print("911 Fiesta - v4.2 + BRAKE ANALYZER REAL + RED PANEL + HEALTH")
        print("=" * 60)
        print("  [OK] Cadencias 3x mas rapidas")
        print("  [OK] BrakeAnalyzer REAL con triple condicion")
        print("  [OK] Procesamiento directo con process(block, sr)")
        print("  [OK] Panel Red/Consola unificado con persistencia")
        print("  [OK] Health Monitor en vivo con loop probe")
        print("=" * 60)
        app = QApplication(sys.argv)
        w = Main()
        sys.exit(app.exec())
    except Exception as e:
        print(f"\nERROR: {e}")
        traceback.print_exc()
        input("\nPresiona Enter...")