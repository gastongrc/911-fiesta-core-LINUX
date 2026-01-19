# module_card.py - VERSIÓN CON PLACEHOLDERS/DISABLED VISUAL
# Badges, atenuado, y estados claros en UI

import os
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QGridLayout, QSlider, QHBoxLayout, QWidget
)
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush

class ThresholdVU(QWidget):
    """Barra VU optimizada con caché de objetos Qt y threshold mejorado."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._lo = 0.25
        self._hi = 0.75
        self._match = 0.50
        self.setMinimumHeight(15)
        
        self._cached_colors = None
        self._cached_pens = None

    def set_value(self, v: float):
        if v is None:
            v = 0.0
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = 0.0
            
            if v > 1.0:
                v = v / 100.0
            
            v = max(0.0, min(1.0, v))
        
        if abs(v - self._value) > 0.01:
            self._value = v
            self.update()

    def set_thresholds(self, lo: float, hi: float):
        lo = float(max(0.0, min(1.0, lo)))
        hi = float(max(0.0, min(1.0, hi)))
        if lo > hi: lo, hi = hi, lo
        if abs(lo-self._lo) > 1e-4 or abs(hi-self._hi) > 1e-4:
            self._lo, self._hi = lo, hi
            self.update()

    def set_match(self, m01: float):
        m01 = float(max(0.0, min(1.0, m01)))
        if abs(m01 - self._match) > 1e-4:
            self._match = m01
            self.update()

    def paintEvent(self, ev):
        w = self.width(); h = self.height()
        p = QPainter(self)
        
        p.setRenderHint(QPainter.Antialiasing, False)

        if self._cached_colors is None:
            self._cached_colors = {
                'bg': QColor("#0f0f0f"),
                'border': QColor("#333333"),
                'fill': QColor("#00e676"),
                'min': QColor("#4fc3f7"),
                'max': QColor("#ffb74d"),
                'match': QColor("#ef5350")
            }
        
        colors = self._cached_colors
        
        p.setPen(QPen(colors['border'], 1))
        p.setBrush(QBrush(colors['bg']))
        rect = QRectF(0.5, 0.5, w-1.0, h-1.0)
        r = 5.0
        p.drawRoundedRect(rect, r, r)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(colors['fill']))
        val_w = max(0.0, min(rect.width(), self._value * rect.width()))
        p.drawRoundedRect(QRectF(rect.left(), rect.top(), val_w, rect.height()), r, r)

        def x_at(pos01: float) -> float:
            return rect.left() + pos01 * rect.width()

        if self._cached_pens is None:
            self._cached_pens = {
                'min': QPen(colors['min'], 1.8),
                'max': QPen(colors['max'], 1.8),
                'match': QPen(colors['match'], 1.2, Qt.DashLine)
            }

        pens = self._cached_pens
        rect_top = int(rect.top())
        rect_bottom = int(rect.bottom())

        p.setPen(pens['min'])
        x = int(x_at(self._lo))
        p.drawLine(x, rect_top, x, rect_bottom)

        p.setPen(pens['max'])
        x = int(x_at(self._hi))
        p.drawLine(x, rect_top, x, rect_bottom)

        p.setPen(pens['match'])
        x = int(x_at(self._match))
        p.drawLine(x, rect_top, x, rect_bottom)

        p.end()


class ModuleCard(QFrame):
    """
    Tarjeta estándar con soporte para placeholders y disabled state.
    """
    def __init__(self, title: str):
        super().__init__()
        
        self._on = False
        self._is_placeholder = False
        self._is_disabled = False
        
        self.setStyleSheet(
            "QFrame{background:#181818; border:1px solid #333; border-radius:6px;} "
            "QLabel{color:#ddd;}"
        )
        self.setMinimumWidth(290)
        self.setMaximumWidth(350)
        self.setMinimumHeight(180)

        self._sliders = {}
        self._slider_cfg = {}
        self._slider_val_lbl = {}
        self._leds = {}
        self._connections = []
        
        self._debug_mode = os.environ.get('MODULE_CARD_DEBUG', '0') == '1'

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8,8,8,8)
        lay.setSpacing(6)
        
        # Header con badges
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("QLabel{font-weight:700; color:#fff; font-size:12px;}")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        
        # Badge para PLACEHOLDER
        self.badge_placeholder = QLabel("PLACEHOLDER")
        self.badge_placeholder.setStyleSheet(
            "QLabel{background:#666; color:#fff; padding:2px 6px; "
            "border-radius:3px; font-size:9px; font-weight:700;}"
        )
        self.badge_placeholder.setVisible(False)
        header_layout.addWidget(self.badge_placeholder)
        
        # Badge para DISABLED
        self.badge_disabled = QLabel("DISABLED")
        self.badge_disabled.setStyleSheet(
            "QLabel{background:#c62828; color:#fff; padding:2px 6px; "
            "border-radius:3px; font-size:9px; font-weight:700;}"
        )
        self.badge_disabled.setVisible(False)
        header_layout.addWidget(self.badge_disabled)
        
        lay.addLayout(header_layout)

        vu_row = QHBoxLayout()
        self.vu = ThresholdVU()
        vu_row.addWidget(self.vu)
        lay.addLayout(vu_row)

        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        lay.addLayout(self.grid)
        self._grid_row = 0

        thr = QGridLayout()
        thr.setHorizontalSpacing(6)
        thr.setVerticalSpacing(4)

        min_lbl = QLabel("Min")
        min_lbl.setStyleSheet("QLabel{font-size:10px;}")
        thr.addWidget(min_lbl, 0, 0, Qt.AlignRight)
        
        self.s_min = QSlider(Qt.Horizontal)
        self.s_min.setRange(0,100)
        self.s_min.setValue(25)
        self.s_min.setMaximumHeight(16)
        thr.addWidget(self.s_min, 0, 1)
        
        self.lbl_min_val = QLabel("25%")
        self.lbl_min_val.setStyleSheet("QLabel{color:#9aa; font-size:10px;}")
        thr.addWidget(self.lbl_min_val, 0, 2, Qt.AlignLeft)

        max_lbl = QLabel("Max")
        max_lbl.setStyleSheet("QLabel{font-size:10px;}")
        thr.addWidget(max_lbl, 1, 0, Qt.AlignRight)
        
        self.s_max = QSlider(Qt.Horizontal)
        self.s_max.setRange(0,100)
        self.s_max.setValue(75)
        self.s_max.setMaximumHeight(16)
        thr.addWidget(self.s_max, 1, 1)
        
        self.lbl_max_val = QLabel("75%")
        self.lbl_max_val.setStyleSheet("QLabel{color:#9aa; font-size:10px;}")
        thr.addWidget(self.lbl_max_val, 1, 2, Qt.AlignLeft)

        match_lbl = QLabel("Match")
        match_lbl.setStyleSheet("QLabel{font-size:10px;}")
        thr.addWidget(match_lbl, 2, 0, Qt.AlignRight)
        
        self.s_match = QSlider(Qt.Horizontal)
        self.s_match.setRange(0,100)
        self.s_match.setValue(50)
        self.s_match.setMaximumHeight(16)
        thr.addWidget(self.s_match, 2, 1)
        
        self.lbl_match_val = QLabel("50%")
        self.lbl_match_val.setStyleSheet("QLabel{color:#9aa; font-size:10px;}")
        thr.addWidget(self.lbl_match_val, 2, 2, Qt.AlignLeft)

        lay.addLayout(thr)

        self.leds_grid = QGridLayout()
        self.leds_grid.setSpacing(4)
        lay.addLayout(self.leds_grid)
        self._led_row = 0

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("QLabel{font-size:10px; color:#9aa;}")
        lay.addWidget(self.lbl_status)

        self._connect_and_track(self.s_min.valueChanged, self._on_thr_change)
        self._connect_and_track(self.s_max.valueChanged, self._on_thr_change)
        self._connect_and_track(self.s_match.valueChanged, self._on_thr_change)
        
        self._refresh_thr_labels()
        self._push_thr_to_vu()

    def mark_as_placeholder(self):
        """Marca esta card como PLACEHOLDER"""
        self._is_placeholder = True
        self.badge_placeholder.setVisible(True)
        self._apply_inactive_style()
        self._disable_controls()
        self.set_status("status: inactive (placeholder)")

    def mark_as_disabled(self):
        """Marca esta card como DISABLED BY PRESET"""
        self._is_disabled = True
        self.badge_disabled.setVisible(True)
        self._apply_inactive_style()
        self._disable_controls()
        self.set_status("status: inactive (disabled by preset)")

    def _apply_inactive_style(self):
        """Aplica estilo visual de inactivo (atenuado)"""
        self.setStyleSheet(
            "QFrame{background:#181818; border:1px solid #333; border-radius:6px; opacity:0.6;} "
            "QLabel{color:#666;}"
        )

    def _disable_controls(self):
        """Deshabilita sliders y controles"""
        self.s_min.setEnabled(False)
        self.s_max.setEnabled(False)
        self.s_match.setEnabled(False)
        
        for slider in self._sliders.values():
            slider.setEnabled(False)

    def _connect_and_track(self, signal, slot):
        signal.connect(slot)
        self._connections.append((signal, slot))

    def _fmt_value(self, vmin, vmax, v):
        span = abs(vmax - vmin)
        if span >= 10:
            return f"{v:.0f}"
        elif span >= 1:
            return f"{v:.1f}"
        else:
            return f"{v:.2f}"

    def _map_slider(self, key, pos01):
        vmin, vmax = self._slider_cfg.get(key, (0.0, 1.0))
        return float(vmin + pos01 * (vmax - vmin))

    def _on_custom_slider_change(self, key):
        s = self._sliders.get(key)
        lbl = self._slider_val_lbl.get(key)
        if not s or not lbl: 
            return
        pos01 = s.value()/1000.0
        vmin, vmax = self._slider_cfg.get(key, (0.0, 1.0))
        v = self._map_slider(key, pos01)
        lbl.setText(self._fmt_value(vmin, vmax, v))

    def _refresh_thr_labels(self):
        self.lbl_min_val.setText(f"{self.s_min.value()}%")
        self.lbl_max_val.setText(f"{self.s_max.value()}%")
        self.lbl_match_val.setText(f"{self.s_match.value()}%")

    def _push_thr_to_vu(self):
        lo = min(self.s_min.value(), self.s_max.value())/100.0
        hi = max(self.s_min.value(), self.s_max.value())/100.0
        self.vu.set_thresholds(lo, hi)
        self.vu.set_match(self.s_match.value()/100.0)

    def _on_thr_change(self, *_):
        self._refresh_thr_labels()
        self._push_thr_to_vu()

    def add_slider(self, key, label, vmin, vmax, vdef):
        row = self._grid_row
        self._grid_row += 1
        
        lbl = QLabel(label)
        lbl.setStyleSheet("QLabel{font-size:10px;}")
        self.grid.addWidget(lbl, row, 0)
        
        s = QSlider(Qt.Horizontal)
        s.setRange(0,1000)
        s.setMaximumHeight(16)
        self._slider_cfg[key] = (float(vmin), float(vmax))
        
        if vmax == vmin:
            pos = 0
        else:
            pos = int((float(vdef) - float(vmin)) / (float(vmax) - float(vmin)) * 1000)
        pos = max(0, min(1000, pos))
        s.setValue(pos)
        self.grid.addWidget(s, row, 1)
        
        val_lbl = QLabel(self._fmt_value(float(vmin), float(vmax), float(vdef)))
        val_lbl.setStyleSheet("QLabel{color:#9aa; font-size:10px;}")
        self.grid.addWidget(val_lbl, row, 2)
        
        self._sliders[key] = s
        self._slider_val_lbl[key] = val_lbl
        
        self._connect_and_track(s.valueChanged, lambda _=None, k=key: self._on_custom_slider_change(k))
        self._on_custom_slider_change(key)

    def get_value(self, key):
        s = self._sliders.get(key)
        if not s: 
            return 0.0
        
        pos01 = max(0.0, min(1.0, s.value() / 1000.0))
        value = self._map_slider(key, pos01)
        
        vmin, vmax = self._slider_cfg.get(key, (0.0, 1.0))
        return float(max(vmin, min(vmax, value)))

    def add_led(self, key, label):
        col = 0
        if self._leds:
            col = len(self._leds) % 3
            if col == 0:
                self._led_row += 1
        
        lbl = QLabel(f"◯ {label}")
        lbl.setStyleSheet("QLabel{color:#777; font-weight:600; font-size:10px;}")
        self.leds_grid.addWidget(lbl, self._led_row, col)
        self._leds[key] = lbl

    def set_led(self, key, on: bool):
        lbl = self._leds.get(key)
        if not lbl: 
            return
        lbl.setText(f"{'◉' if on else '◯'} {lbl.text()[2:]}")
        lbl.setStyleSheet(f"QLabel{{color: {'#00f08a' if on else '#777'}; font-weight:700; font-size:10px;}}")

    def set_value(self, v):
        self.vu.set_value(v)

    def get_thresholds(self):
        try:
            min_val = self.s_min.value()
            max_val = self.s_max.value()
            
            min_val = max(0, min(100, min_val))
            max_val = max(0, min(100, max_val))
            
            lo = min(min_val, max_val) / 100.0
            hi = max(min_val, max_val) / 100.0
            
            return float(lo), float(hi)
        except Exception as e:
            print(f"[ModuleCard] Error en get_thresholds: {e}")
            return 0.25, 0.75

    def get_match(self):
        try:
            match_val = self.s_match.value()
            match_val = max(0, min(100, match_val))
            return float(match_val / 100.0)
        except Exception as e:
            print(f"[ModuleCard] Error en get_match: {e}")
            return 0.5

    def set_on(self, on: bool):
        self._on = bool(on)
        
        # No cambiar borde si está inactivo
        if self._is_placeholder or self._is_disabled:
            return
        
        self.setStyleSheet(
            f"QFrame{{background:#181818; border:2px solid {'#00f08a' if on else '#333'}; border-radius:6px;}} "
            "QLabel{color:#ddd;}"
        )

    def is_on(self): 
        return getattr(self, "_on", False)

    def to_preset(self):
        preset = {
            "min": self.s_min.value(),
            "max": self.s_max.value(),
            "match": self.s_match.value(),
            "sliders": {k: s.value() for k,s in self._sliders.items()}
        }
        
        # Incluir estado de enabled
        if self._is_disabled:
            preset["enabled"] = False
        
        return preset

    def from_preset(self, data: dict):
        try:
            self.s_min.setValue(int(data.get("min", 25)))
            self.s_max.setValue(int(data.get("max", 75)))
            self.s_match.setValue(int(data.get("match", 50)))
            sliders = data.get("sliders", {})
            for k, v in sliders.items():
                if k in self._sliders:
                    self._sliders[k].setValue(int(v))
            self._push_thr_to_vu()
            
            # Leer flag enabled
            if "enabled" in data and not data["enabled"]:
                self.mark_as_disabled()
                
        except Exception:
            pass

    def set_status(self, text: str):
        self.lbl_status.setText(text or "")

    def validate_state(self):
        issues = []
        
        try:
            lo, hi = self.get_thresholds()
            if not (0.0 <= lo <= 1.0):
                issues.append(f"Threshold LO fuera de rango: {lo}")
            if not (0.0 <= hi <= 1.0):
                issues.append(f"Threshold HI fuera de rango: {hi}")
            if lo > hi:
                issues.append(f"Threshold LO > HI: {lo} > {hi}")
        except Exception as e:
            issues.append(f"Error en thresholds: {e}")
        
        try:
            match = self.get_match()
            if not (0.0 <= match <= 1.0):
                issues.append(f"Match fuera de rango: {match}")
        except Exception as e:
            issues.append(f"Error en match: {e}")
        
        for key, slider in self._sliders.items():
            try:
                val = self.get_value(key)
                vmin, vmax = self._slider_cfg.get(key, (0.0, 1.0))
                if not (vmin <= val <= vmax):
                    issues.append(f"Slider '{key}' fuera de rango: {val} not in [{vmin}, {vmax}]")
            except Exception as e:
                issues.append(f"Error en slider '{key}': {e}")
        
        if issues and self._debug_mode:
            print(f"[ModuleCard:{self.lbl_title.text()}] Validation issues: {issues}")
        
        return issues

    def __del__(self):
        try:
            for signal, slot in self._connections:
                try:
                    signal.disconnect(slot)
                except:
                    pass
            
            self._connections.clear()
            self._sliders.clear()
            self._slider_cfg.clear()
            self._slider_val_lbl.clear()
            self._leds.clear()
            
        except Exception:
            pass