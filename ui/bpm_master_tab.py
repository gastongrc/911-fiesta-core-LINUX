# ui/bpm_master_tab.py
# BPM MASTER TAB - Gráfico 30s con trazas RAW/SMOOTH/MASTER + controles

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QGroupBox, QGridLayout
)
from PySide6.QtCore import Qt
from collections import deque
import time

# Intentar importar PyQtGraph, fallback a matplotlib si no está
try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    print("[BPM_UI] PyQtGraph no disponible, gráfico deshabilitado")


class BpmMasterTab(QWidget):
    """
    Tab BPM Master con:
    - Gráfico lineal 30s con trazas RAW/SMOOTH/MASTER
    - Controles: mostrar/ocultar trazas, reset PLL, freeze BPM
    - Indicadores: BPM actual, estado PLL locked/unlocked
    """

    def __init__(self):
        super().__init__()

        # Buffers de datos (30s @ 4 Hz = 120 muestras)
        self.buffer_size = 120
        self.buffer_time = deque(maxlen=self.buffer_size)
        self.buffer_raw = deque(maxlen=self.buffer_size)
        self.buffer_smooth = deque(maxlen=self.buffer_size)
        self.buffer_master = deque(maxlen=self.buffer_size)

        # Tiempo de inicio
        self.start_time = time.time()

        # Estados de visualización
        self.show_raw = True
        self.show_smooth = True
        self.show_master = True
        self.frozen = False

        # Último estado
        self.last_raw = None
        self.last_smooth = None
        self.last_master = None
        self.last_phase = 0.0

        # Setup UI
        self._setup_ui()

    def _setup_ui(self):
        """Configura la interfaz."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # === PANEL SUPERIOR: INDICADORES ===
        indicators = self._build_indicators_panel()
        layout.addWidget(indicators)

        # === GRÁFICO ===
        if PYQTGRAPH_AVAILABLE:
            self.graph_widget = self._build_pyqtgraph()
            layout.addWidget(self.graph_widget, stretch=3)
        else:
            no_graph = QLabel("Gráfico no disponible (instalar pyqtgraph)")
            no_graph.setStyleSheet("color: #888; font-size: 14px;")
            no_graph.setAlignment(Qt.AlignCenter)
            layout.addWidget(no_graph, stretch=3)

        # === CONTROLES ===
        controls = self._build_controls_panel()
        layout.addWidget(controls)

    def _build_indicators_panel(self) -> QGroupBox:
        """Panel de indicadores BPM."""
        group = QGroupBox("BPM Master Indicators")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #444;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #aaa;
            }
        """)

        layout = QGridLayout(group)
        layout.setSpacing(10)

        # RAW
        layout.addWidget(QLabel("RAW:"), 0, 0)
        self.lbl_raw = QLabel("— BPM")
        self.lbl_raw.setStyleSheet("color: #FFD700; font-size: 18px; font-weight: bold;")
        layout.addWidget(self.lbl_raw, 0, 1)

        # SMOOTH
        layout.addWidget(QLabel("SMOOTH:"), 1, 0)
        self.lbl_smooth = QLabel("— BPM")
        self.lbl_smooth.setStyleSheet("color: #1E90FF; font-size: 18px; font-weight: bold;")
        layout.addWidget(self.lbl_smooth, 1, 1)

        # MASTER
        layout.addWidget(QLabel("MASTER:"), 2, 0)
        self.lbl_master = QLabel("— BPM")
        self.lbl_master.setStyleSheet("color: #00FF64; font-size: 24px; font-weight: bold;")
        layout.addWidget(self.lbl_master, 2, 1)

        # PLL Status
        layout.addWidget(QLabel("PLL Status:"), 3, 0)
        self.lbl_pll_status = QLabel("UNLOCKED")
        self.lbl_pll_status.setStyleSheet("color: #FF6666; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_pll_status, 3, 1)

        # === ROBUST v2 Indicators ===
        # Confidence
        layout.addWidget(QLabel("Confidence:"), 0, 2)
        self.lbl_confidence = QLabel("0%")
        self.lbl_confidence.setStyleSheet("color: #bbb; font-size: 14px;")
        layout.addWidget(self.lbl_confidence, 0, 3)

        # OCR State
        layout.addWidget(QLabel("OCR State:"), 1, 2)
        self.lbl_ocr_state = QLabel("INIT")
        self.lbl_ocr_state.setStyleSheet("color: #bbb; font-size: 14px;")
        layout.addWidget(self.lbl_ocr_state, 1, 3)

        # Harmonic Fix
        layout.addWidget(QLabel("Harmonic Fix:"), 2, 2)
        self.lbl_harmonic_fix = QLabel("none")
        self.lbl_harmonic_fix.setStyleSheet("color: #bbb; font-size: 14px;")
        layout.addWidget(self.lbl_harmonic_fix, 2, 3)

        # Drift
        layout.addWidget(QLabel("Drift:"), 3, 2)
        self.lbl_drift = QLabel("0.0ms")
        self.lbl_drift.setStyleSheet("color: #bbb; font-size: 14px;")
        layout.addWidget(self.lbl_drift, 3, 3)

        # Lock Mode
        layout.addWidget(QLabel("Lock Mode:"), 4, 0)
        self.lbl_lock_mode = QLabel("UNLOCKED")
        self.lbl_lock_mode.setStyleSheet("color: #FF6666; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.lbl_lock_mode, 4, 1)

        return group

    def _build_pyqtgraph(self) -> pg.PlotWidget:
        """Crea el gráfico con PyQtGraph."""
        # Configurar estilo oscuro
        pg.setConfigOption('background', '#0a0a0a')
        pg.setConfigOption('foreground', '#aaa')

        # Crear widget de gráfico
        graph = pg.PlotWidget()
        graph.setLabel('left', 'BPM', color='#aaa', size='12pt')
        graph.setLabel('bottom', 'Tiempo (s)', color='#aaa', size='12pt')
        graph.setTitle('BPM History (30s)', color='#aaa', size='14pt')
        graph.showGrid(x=True, y=True, alpha=0.3)
        graph.setYRange(60, 180)

        # Crear curvas
        self.curve_raw = graph.plot(
            pen=pg.mkPen(color='#FFD700', width=2),
            name='RAW'
        )
        self.curve_smooth = graph.plot(
            pen=pg.mkPen(color='#1E90FF', width=2),
            name='SMOOTH'
        )
        self.curve_master = graph.plot(
            pen=pg.mkPen(color='#00FF64', width=3),
            name='MASTER'
        )

        # Leyenda
        graph.addLegend()

        return graph

    def _build_controls_panel(self) -> QGroupBox:
        """Panel de controles."""
        group = QGroupBox("Controls")
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #444;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background: #1a1a1a;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #aaa;
            }
        """)

        layout = QHBoxLayout(group)

        # Checkboxes para mostrar/ocultar trazas
        self.chk_raw = QCheckBox("Show RAW")
        self.chk_raw.setChecked(True)
        self.chk_raw.setStyleSheet("color: #FFD700;")
        self.chk_raw.toggled.connect(self._on_toggle_raw)
        layout.addWidget(self.chk_raw)

        self.chk_smooth = QCheckBox("Show SMOOTH")
        self.chk_smooth.setChecked(True)
        self.chk_smooth.setStyleSheet("color: #1E90FF;")
        self.chk_smooth.toggled.connect(self._on_toggle_smooth)
        layout.addWidget(self.chk_smooth)

        self.chk_master = QCheckBox("Show MASTER")
        self.chk_master.setChecked(True)
        self.chk_master.setStyleSheet("color: #00FF64;")
        self.chk_master.toggled.connect(self._on_toggle_master)
        layout.addWidget(self.chk_master)

        layout.addStretch()

        # Botones
        btn_style = """
            QPushButton {
                background: #333;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ccc;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #444;
            }
            QPushButton:pressed {
                background: #222;
            }
        """

        self.btn_reset = QPushButton("RESET PLL")
        self.btn_reset.setStyleSheet(btn_style)
        self.btn_reset.clicked.connect(self._on_reset_pll)
        layout.addWidget(self.btn_reset)

        self.btn_freeze = QPushButton("FREEZE")
        self.btn_freeze.setStyleSheet(btn_style)
        self.btn_freeze.setCheckable(True)
        self.btn_freeze.toggled.connect(self._on_toggle_freeze)
        layout.addWidget(self.btn_freeze)

        return group

    # === CALLBACKS ===
    def _on_toggle_raw(self, checked):
        """Toggle RAW trace."""
        self.show_raw = checked
        if PYQTGRAPH_AVAILABLE and hasattr(self, 'curve_raw'):
            self.curve_raw.setVisible(checked)

    def _on_toggle_smooth(self, checked):
        """Toggle SMOOTH trace."""
        self.show_smooth = checked
        if PYQTGRAPH_AVAILABLE and hasattr(self, 'curve_smooth'):
            self.curve_smooth.setVisible(checked)

    def _on_toggle_master(self, checked):
        """Toggle MASTER trace."""
        self.show_master = checked
        if PYQTGRAPH_AVAILABLE and hasattr(self, 'curve_master'):
            self.curve_master.setVisible(checked)

    def _on_reset_pll(self):
        """Reset PLL (debe ser implementado por el caller)."""
        print("[BPM_UI] Reset PLL requested")
        # El main.py debe conectar esto a self.bpm_pll.reset()

    def _on_toggle_freeze(self, checked):
        """Freeze/unfreeze BPM display."""
        self.frozen = checked
        if checked:
            self.btn_freeze.setText("UNFREEZE")
        else:
            self.btn_freeze.setText("FREEZE")

    # === UPDATE METHOD ===
    def update_bpm(self, state: dict):
        """
        Actualiza el tab con nuevos datos de BPM.

        Args:
            state: dict con keys 'raw', 'smooth', 'master', 'phase', 'locked'
        """
        if self.frozen:
            return

        raw = state.get('raw')
        smooth = state.get('smooth')
        master = state.get('master')
        phase = state.get('phase', 0.0)
        locked = state.get('locked', False)

        # Actualizar indicadores
        if raw is not None:
            self.lbl_raw.setText(f"{raw:.1f} BPM")
            self.last_raw = raw
        else:
            self.lbl_raw.setText("— BPM")

        if smooth is not None:
            self.lbl_smooth.setText(f"{smooth:.1f} BPM")
            self.last_smooth = smooth
        else:
            self.lbl_smooth.setText("— BPM")

        if master is not None:
            self.lbl_master.setText(f"{master:.1f} BPM")
            self.last_master = master
        else:
            self.lbl_master.setText("— BPM")

        # Estado PLL
        if locked:
            self.lbl_pll_status.setText("LOCKED")
            self.lbl_pll_status.setStyleSheet("color: #00FF64; font-size: 14px; font-weight: bold;")
        else:
            self.lbl_pll_status.setText("UNLOCKED")
            self.lbl_pll_status.setStyleSheet("color: #FF6666; font-size: 14px; font-weight: bold;")

        # === ROBUST v2 Metrics ===
        # Confidence
        confidence = state.get('confidence', 0.0)
        self.lbl_confidence.setText(f"{confidence*100:.0f}%")
        if confidence >= 0.8:
            self.lbl_confidence.setStyleSheet("color: #00FF64; font-size: 14px;")
        elif confidence >= 0.5:
            self.lbl_confidence.setStyleSheet("color: #FFD700; font-size: 14px;")
        else:
            self.lbl_confidence.setStyleSheet("color: #FF6666; font-size: 14px;")

        # OCR State
        ocr_state = state.get('ocr_state', 'INIT')
        self.lbl_ocr_state.setText(ocr_state)

        # Harmonic Fix
        harmonic_correction = state.get('harmonic_correction', 'none')
        self.lbl_harmonic_fix.setText(harmonic_correction)
        if harmonic_correction != 'none':
            self.lbl_harmonic_fix.setStyleSheet("color: #FFD700; font-size: 14px; font-weight: bold;")
        else:
            self.lbl_harmonic_fix.setStyleSheet("color: #bbb; font-size: 14px;")

        # Drift
        drift_ms = state.get('drift_ms', 0.0)
        self.lbl_drift.setText(f"{drift_ms:.2f}ms")
        if abs(drift_ms) > 1.0:
            self.lbl_drift.setStyleSheet("color: #FF6666; font-size: 14px;")
        elif abs(drift_ms) > 0.5:
            self.lbl_drift.setStyleSheet("color: #FFD700; font-size: 14px;")
        else:
            self.lbl_drift.setStyleSheet("color: #00FF64; font-size: 14px;")

        # Lock Mode
        lock_mode = state.get('lock_mode', 'UNLOCKED')
        self.lbl_lock_mode.setText(lock_mode)
        if lock_mode == 'HARD_LOCK':
            self.lbl_lock_mode.setStyleSheet("color: #00FF64; font-size: 14px; font-weight: bold;")
        elif lock_mode == 'SOFT_LOCK':
            self.lbl_lock_mode.setStyleSheet("color: #FFD700; font-size: 14px; font-weight: bold;")
        else:
            self.lbl_lock_mode.setStyleSheet("color: #FF6666; font-size: 14px; font-weight: bold;")

        # Actualizar buffers para gráfico
        current_time = time.time() - self.start_time
        self.buffer_time.append(current_time)
        self.buffer_raw.append(raw if raw is not None else 0.0)
        self.buffer_smooth.append(smooth if smooth is not None else 0.0)
        self.buffer_master.append(master if master is not None else 0.0)

        # Actualizar gráfico
        if PYQTGRAPH_AVAILABLE and hasattr(self, 'curve_raw'):
            try:
                times = list(self.buffer_time)
                if self.show_raw:
                    self.curve_raw.setData(times, list(self.buffer_raw))
                if self.show_smooth:
                    self.curve_smooth.setData(times, list(self.buffer_smooth))
                if self.show_master:
                    self.curve_master.setData(times, list(self.buffer_master))

                # Ajustar rango X para mostrar últimos 30s
                if len(times) > 0:
                    max_time = max(times)
                    self.graph_widget.setXRange(max(0, max_time - 30), max_time + 1)
            except Exception as e:
                print(f"[BPM_UI] Error actualizando gráfico: {e}")
