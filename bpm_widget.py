from PySide6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QPushButton, QInputDialog, QMessageBox
from PySide6.QtCore import Qt

class BPMMonitorWidget(QWidget):
    def __init__(self, bpm_detector, parent=None):
        super().__init__(parent)
        self.bpm_detector = bpm_detector

        # Estilos cacheados
        self._bpm_style_stable = (
            "color:#00f08a; font-weight:700; font-size:24px; background:#0a0a0a; "
            "border:1px solid #333; border-radius:6px; padding:8px; text-align:center;"
        )
        self._bpm_style_unstable = (
            "color:#ffaa00; font-weight:700; font-size:24px; background:#0a0a0a; "
            "border:1px solid #333; border-radius:6px; padding:8px; text-align:center;"
        )
        self._bpm_style_off = (
            "color:#888; font-weight:700; font-size:24px; background:#0a0a0a; "
            "border:1px solid #333; border-radius:6px; padding:8px; text-align:center;"
        )
        self._last_bpm_style = None

        root = QVBoxLayout(self)

        title = QLabel("BPM")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:700;")
        root.addWidget(title)

        grid = QGridLayout()
        root.addLayout(grid)

        self.bpm_main = QLabel("--")
        self.bpm_main.setAlignment(Qt.AlignCenter)
        self.bpm_main.setMinimumWidth(120)

        self.bpm_hint = QLabel("—")
        self.bpm_hint.setAlignment(Qt.AlignCenter)

        self.btn_reset = QPushButton("Reset")
        self.btn_force = QPushButton("Forzar BPM")

        grid.addWidget(QLabel("Actual"), 0, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.bpm_main,    0, 1)
        grid.addWidget(QLabel("Estado"), 1, 0, alignment=Qt.AlignRight)
        grid.addWidget(self.bpm_hint,    1, 1)
        grid.addWidget(self.btn_reset,   2, 0)
        grid.addWidget(self.btn_force,   2, 1)

        self.btn_reset.clicked.connect(self.reset_bpm)
        self.btn_force.clicked.connect(self.force_bpm_dialog)

        self.update_display()

    # ---------------------------------------------------------------------
    def update_display(self):
        bpm = 0.0
        stable = False
        info = {}
        try:
            if hasattr(self.bpm_detector, "get_info"):
                info = self.bpm_detector.get_info() or {}
                bpm = float(info.get("bpm", 0.0))
                stable = bool(info.get("stable", False))
            elif hasattr(self.bpm_detector, "current_bpm"):
                bpm = float(getattr(self.bpm_detector, "current_bpm") or 0.0)
                stable = bool(getattr(self.bpm_detector, "is_stable", False))
        except Exception:
            bpm = 0.0
            stable = False

        self.bpm_main.setText(f"{bpm:.1f}" if bpm > 0 else "--")

        if bpm <= 0:
            want = self._bpm_style_off
            self.bpm_hint.setText("sin lock")
        else:
            if stable:
                want = self._bpm_style_stable
                self.bpm_hint.setText("estable")
            else:
                want = self._bpm_style_unstable
                self.bpm_hint.setText("buscando…")

        if want != self._last_bpm_style:
            self.bpm_main.setStyleSheet(want)
            self._last_bpm_style = want

    # ---------------------------------------------------------------------
    def force_bpm_dialog(self):
        val, ok = QInputDialog.getDouble(self, "Forzar BPM", "BPM:", 128.0, 40.0, 220.0, 1)
        if not ok:
            return
        try:
            if hasattr(self.bpm_detector, "force_bpm"):
                self.bpm_detector.force_bpm(val)
            elif hasattr(self.bpm_detector, "set_bpm"):
                self.bpm_detector.set_bpm(val)
            else:
                if hasattr(self.bpm_detector, "current_bpm"):
                    self.bpm_detector.current_bpm = float(val)
            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "BPM", f"No se pudo forzar el BPM:\n{e}")

    # ---------------------------------------------------------------------
    def reset_bpm(self):
        try:
            if hasattr(self.bpm_detector, "reset"):
                self.bpm_detector.reset()
            else:
                if hasattr(self.bpm_detector, "set_bpm"):
                    self.bpm_detector.set_bpm(0.0)
                elif hasattr(self.bpm_detector, "current_bpm"):
                    self.bpm_detector.current_bpm = 0.0
            self.update_display()
        except Exception as e:
            QMessageBox.warning(self, "BPM", f"No se pudo resetear el BPM:\n{e}")
