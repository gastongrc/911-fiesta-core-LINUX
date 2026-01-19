# waveform_widget.py
import numpy as np
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtCore import QRectF, Qt

def _stereo(x):
    """Devuelve (L,R) como float32 1D; si es mono, duplica."""
    x = np.asarray(x)
    if x.ndim == 1:
        l = x.astype(np.float32, copy=False)
        r = l
    else:
        if x.shape[1] == 1:
            l = x[:, 0].astype(np.float32, copy=False)
            r = l
        else:
            l = x[:, 0].astype(np.float32, copy=False)
            r = x[:, 1].astype(np.float32, copy=False)
    return l, r

class WaveformWidget(QWidget):
    """
    Forma de onda “humana”, 2 canales espejados.
    - Ring buffer de ~N segundos.
    - Dibujo por columna con percentiles vectorizados (rápido).
    - Auto-escala INSTANTÁNEA usando P99(|señal|) + headroom.
    """
    def __init__(self, seconds=8.0, samplerate=44100,
                 color_pos=QColor(255,170,0),   # arriba
                 color_neg=QColor(50,120,255),  # abajo
                 grid=True,
                 q_low=0.03, q_high=0.97,       # percentiles por columna
                 headroom=0.92,                 # margen visual
                 max_cols=1000,                 # techo de columnas para FPS
                 parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMinimumWidth(500)

        self.want_seconds = float(max(1.0, seconds))
        self.sr = int(max(8000, samplerate))
        cap = int(self.want_seconds * self.sr)

        self._bufL = np.zeros(cap, dtype=np.float32)
        self._bufR = np.zeros(cap, dtype=np.float32)
        self._wr = 0
        self._len = 0

        self.color_pos = color_pos
        self.color_neg = color_neg
        self.grid = bool(grid)

        self.q_low = float(np.clip(q_low, 0.0, 0.49))
        self.q_high = float(np.clip(q_high, 0.51, 1.0))
        self.headroom = float(np.clip(headroom, 0.5, 0.98))
        self.max_cols = int(max(100, max_cols))

        # estilado
        self._pen_grid  = QPen(QColor(70,70,70), 1, Qt.DotLine)
        self._pen_pos   = QPen(self.color_pos, 1, Qt.SolidLine)
        self._pen_neg   = QPen(self.color_neg, 1, Qt.SolidLine)
        self._pen_frame = QPen(QColor(50,50,50), 1, Qt.SolidLine)

    # ---------------- público ----------------
    def set_samplerate(self, sr):
        sr = int(sr)
        if sr <= 0 or sr == self.sr: return
        self.sr = sr
        self._realloc()

    def _realloc(self):
        cap = int(self.want_seconds * self.sr)
        self._bufL = np.zeros(cap, dtype=np.float32)
        self._bufR = np.zeros(cap, dtype=np.float32)
        self._wr = 0
        self._len = 0
        self.update()

    def clear(self):
        self._bufL[:] = 0
        self._bufR[:] = 0
        self._wr = 0
        self._len = 0
        self.update()

    def push_block(self, block, sr=None):
        """Append audio. block: (N,) o (N,2)."""
        if block is None: return
        if sr is not None: self.set_samplerate(sr)

        L, R = _stereo(block)
        # protección ante valores locos: clamp ±3.0
        L = np.clip(L, -3.0, 3.0)
        R = np.clip(R, -3.0, 3.0)

        n = L.size
        if n == 0: return

        # write ring
        cap = self._bufL.size
        if n >= cap:
            L = L[-cap:]; R = R[-cap:]; n = cap
            self._bufL[:] = L; self._bufR[:] = R
            self._wr = 0; self._len = cap
        else:
            end = self._wr + n
            if end <= cap:
                self._bufL[self._wr:end] = L
                self._bufR[self._wr:end] = R
            else:
                k = cap - self._wr
                self._bufL[self._wr:] = L[:k]
                self._bufR[self._wr:] = R[:k]
                self._bufL[:end-cap] = L[k:]
                self._bufR[:end-cap] = R[k:]
            self._wr = (self._wr + n) % cap
            self._len = min(cap, self._len + n)

        # pedimos repintado
        self.update()

    # ---------------- helpers ----------------
    def _visible(self):
        """Devuelve (L,R) en orden temporal (antiguo→reciente)."""
        cap = self._bufL.size
        n = self._len
        if n == 0:
            return np.zeros(0, np.float32), np.zeros(0, np.float32)
        start = (self._wr - n) % cap
        if start + n <= cap:
            return self._bufL[start:start+n], self._bufR[start:start+n]
        k = cap - start
        L = np.concatenate([self._bufL[start:], self._bufL[:n-k]])
        R = np.concatenate([self._bufR[start:], self._bufR[:n-k]])
        return L, R

    def _qminmax_per_column_fast(self, x, cols, q_low, q_high):
        """
        Percentiles por columna pero vectorizado:
        - se calcula un step = ceil(N/cols)
        - se paddea al múltiplo y se hace reshape (cols, step)
        - quantile(axis=1)
        """
        N = x.size
        if N == 0 or cols <= 0:
            return np.zeros(cols), np.zeros(cols)

        step = int(np.ceil(N / cols))
        pad = cols * step - N
        if pad > 0:
            x = np.pad(x, (0, pad), mode='edge')
        X = x.reshape(cols, step)
        # clamp suave por seguridad
        X = np.clip(X, -2.0, 2.0)
        mn = np.quantile(X, q_low, axis=1)
        mx = np.quantile(X, q_high, axis=1)
        return mn.astype(np.float32), mx.astype(np.float32)

    # ---------------- pintado ----------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect()

        # fondo y marco
        p.fillRect(rect, QColor(10,10,10))
        p.setPen(self._pen_frame)
        p.drawRect(QRectF(rect.left()+0.5, rect.top()+0.5, rect.width()-1.0, rect.height()-1.0))

        # grilla
        if self.grid:
            p.setPen(self._pen_grid)
            mid = rect.center().y()
            p.drawLine(rect.left()+1, mid, rect.right()-1, mid)
            y1 = rect.top() + rect.height()*0.25
            y3 = rect.top() + rect.height()*0.75
            p.drawLine(rect.left()+1, int(y1), rect.right()-1, int(y1))
            p.drawLine(rect.left()+1, int(y3), rect.right()-1, int(y3))

        # datos
        L, R = self._visible()
        if L.size == 0:
            p.end(); return

        # cols limitadas para FPS
        cols = min(rect.width(), self.max_cols)

        # percentiles rápidos por columna
        lmn, lmx = self._qminmax_per_column_fast(L, cols, self.q_low, self.q_high)
        rmn, rmx = self._qminmax_per_column_fast(R, cols, self.q_low, self.q_high)

        # auto-escala instantánea con P99(|señal|)
        p99 = float(np.percentile(np.concatenate([np.abs(L), np.abs(R)]), 99))
        p99 = max(p99, 0.05)
        s = self.headroom / p99

        # mapeo X si cols < width (estirar)
        x0 = rect.left()
        xw = rect.width()
        xs = xw / cols

        h = rect.height()
        mid = rect.center().y()
        top_half = h * 0.46  # cada canal ~46%

        # L arriba
        p.setPen(self._pen_pos)
        for i in range(cols):
            x = int(x0 + i * xs)
            y1 = int(mid - (lmx[i]*s)*top_half)
            y2 = int(mid - (lmn[i]*s)*top_half)
            if y2 < y1: y1, y2 = y2, y1
            p.drawLine(x, y1, x, y2)

        # R abajo (espejado)
        p.setPen(self._pen_neg)
        for i in range(cols):
            x = int(x0 + i * xs)
            y1 = int(mid + (rmn[i]*s)*top_half)
            y2 = int(mid + (rmx[i]*s)*top_half)
            if y2 < y1: y1, y2 = y2, y1
            p.drawLine(x, y1, x, y2)

        p.end()
