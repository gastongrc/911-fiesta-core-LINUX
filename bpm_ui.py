# bpm_ui.py
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QHBoxLayout, QPushButton, QInputDialog
from PySide6.QtCore import Qt

class BPMMonitorWidget(QWidget):
    """
    Panel de monitoreo de BPM desacoplado del main.
    Recibe un detector con interfaz:
      - get_status_info() -> dict(bpm, confidence, stable, delay_ms, genre_hint)
      - reset(), force_bpm(bpm)
    """
    def __init__(self, bpm_detector=None, available=True):
        super().__init__()
        self.detector = bpm_detector
        self.available = available

        self._last_main = None; self._last_color = None
        self._last_conf = None; self._last_stable = None
        self._last_genre = None; self._last_delay = None

        layout = QVBoxLayout(self); layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(6)
        title = QLabel("BPM DETECTOR")
        title.setStyleSheet("font-weight:700; color:#ddd; font-size:12px;")
        layout.addWidget(title)

        self.bpm_main = QLabel("-- BPM")
        self.bpm_main.setStyleSheet("color:#888; font-weight:700; font-size:24px; background:#0a0a0a; border:1px solid #333; border-radius:6px; padding:8px;")
        self.bpm_main.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.bpm_main)

        info_layout = QGridLayout(); info_layout.setSpacing(4)
        info_layout.addWidget(QLabel("Confidence:"), 0, 0)
        self.confidence_label = QLabel("0%"); self.confidence_label.setStyleSheet("color:#bbb;")
        info_layout.addWidget(self.confidence_label, 0, 1)

        info_layout.addWidget(QLabel("Estable:"), 1, 0)
        self.stable_label = QLabel("No"); self.stable_label.setStyleSheet("color:#bbb;")
        info_layout.addWidget(self.stable_label, 1, 1)

        info_layout.addWidget(QLabel("Género:"), 2, 0)
        self.genre_label = QLabel("Unknown"); self.genre_label.setStyleSheet("color:#bbb;")
        info_layout.addWidget(self.genre_label, 2, 1)

        info_layout.addWidget(QLabel("Delay:"), 3, 0)
        self.delay_label = QLabel("0ms"); self.delay_label.setStyleSheet("color:#bbb;")
        info_layout.addWidget(self.delay_label, 3, 1)

        layout.addLayout(info_layout)

        btn_layout = QHBoxLayout()
        self.btn_force_bpm = QPushButton("Force BPM")
        self.btn_reset = QPushButton("Reset")
        for b in (self.btn_force_bpm, self.btn_reset):
            b.setStyleSheet("QPushButton{background:#333; border:1px solid #555; border-radius:4px; padding:6px; color:#ccc;} QPushButton:hover{background:#444;}")
        btn_layout.addWidget(self.btn_force_bpm); btn_layout.addWidget(self.btn_reset)
        layout.addLayout(btn_layout)

        self.btn_reset.clicked.connect(self.reset_bpm)
        self.btn_force_bpm.clicked.connect(self.force_bpm_dialog)

        self.setStyleSheet("QWidget{background:#151515; border:1px solid #333; border-radius:6px;} QLabel{color:#ccc;}")

    # --- API pública ---
    def set_detector(self, detector, available=True):
        self.detector = detector
        self.available = available

    def update_display(self):
        if not self.available or not self.detector:
            if self._last_main != "NO DISPONIBLE":
                self._last_main = "NO DISPONIBLE"
                self.bpm_main.setText(self._last_main)
            return

        info = self.detector.get_status_info() or {}
        bpm = float(info.get('bpm', 0) or 0)

        main_txt = f"{bpm:.1f} BPM" if bpm > 0 else "-- BPM"
        if main_txt != self._last_main:
            self._last_main = main_txt
            self.bpm_main.setText(main_txt)

        stable = bool(info.get('stable', False))
        color = "#00f08a" if stable and bpm>0 else ("#ffaa00" if bpm>0 else "#888")
        if color != self._last_color:
            self._last_color = color
            self.bpm_main.setStyleSheet(
                f"color:{color}; font-weight:700; font-size:24px; background:#0a0a0a; border:1px solid #333; border-radius:6px; padding:8px;"
            )

        conf_txt = f"{float(info.get('confidence', 0) or 0):.1f}%"
        if conf_txt != self._last_conf:
            self._last_conf = conf_txt; self.confidence_label.setText(conf_txt)

        stab_txt = "Sí" if stable else "No"
        if stab_txt != self._last_stable:
            self._last_stable = stab_txt
            self.stable_label.setText(stab_txt)
            self.stable_label.setStyleSheet(f"color:{'#00f08a' if stable else '#ff6666'};")

        genre = info.get('genre_hint', 'Unknown') or 'Unknown'
        if genre != self._last_genre:
            self._last_genre = genre; self.genre_label.setText(genre)

        delay = f"{int(info.get('delay_ms', 0) or 0)}ms"
        if delay != self._last_delay:
            self._last_delay = delay; self.delay_label.setText(delay)

    # --- acciones ---
    def reset_bpm(self):
        if self.available and self.detector:
            try: self.detector.reset()
            except Exception: pass

    def force_bpm_dialog(self):
        if not (self.available and self.detector): return
        current_bpm = 0.0
        try:
            get = getattr(self.detector, "get_current_bpm", None)
            if callable(get): current_bpm = float(get() or 120.0)
        except Exception:
            current_bpm = 120.0
        bpm, ok = QInputDialog.getDouble(self, "Force BPM", "Ingrese BPM manualmente:",
                                         current_bpm if current_bpm>0 else 120.0, 60.0, 240.0, 1)
        if ok:
            try: self.detector.force_bpm(bpm)
            except Exception: pass
