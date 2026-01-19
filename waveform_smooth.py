from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap
import numpy as np
from collections import deque
import time

class SmoothWaveform(QWidget):
    """
    Waveform ultra-fluido: actualización INDEPENDIENTE del audio
    FIX #7: Agregado límite superior al acumulador de píxeles
    """
    def __init__(self, seconds=8, samplerate=48000, fps=30, px_per_sec=120, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(90)

        # Parámetros
        self.sr = int(samplerate)
        self.seconds = float(seconds)
        self.fps = int(fps)
        self.px_per_sec = float(px_per_sec)

        # Buffer de entrada - THREAD-SAFE
        self._in_queue = deque()
        self._in_len = 0

        # Ring buffer
        self.capacity = int(self.sr * self.seconds * 2)
        self.ring = np.zeros(self.capacity, dtype=np.float32)
        self.wpos = 0

        # Colores
        self.bg = QColor("#0a0a0a")
        self.fg = QColor("#4da3ff")
        self.grid = QColor(255, 255, 255, 30)
        self.back = None

        # Control de scroll INDEPENDIENTE
        self._px_accumulated = 0.0
        self._last_update_time = time.perf_counter()
        
        # Timer INDEPENDIENTE - corre siempre a velocidad constante
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / self.fps))  # 33ms para 30fps
        self.timer.timeout.connect(self._tick)
        self.timer.start()

        self._last_width = 0
        self._last_height = 0

    def push(self, frame, sr=None):
        """Agrega audio de forma asíncrona"""
        if frame is None:
            return
        x = np.asarray(frame, dtype=np.float32)
        if x.size == 0:
            return
        if x.ndim == 2:
            x = x.mean(axis=1)
        x = np.clip(x, -1.0, 1.0)
        
        if sr and int(sr) != self.sr:
            self._set_samplerate(int(sr))
        
        # Agregar a la cola sin bloquear
        self._in_queue.append(x)
        self._in_len += x.size

    def push_block(self, block, sr=None):
        self.push(block, sr)

    def clear(self):
        self._in_queue.clear()
        self._in_len = 0
        self.ring.fill(0)
        self.wpos = 0
        self._px_accumulated = 0.0
        if self.back:
            self.back.fill(self.bg)
        self.update()

    def sizeHint(self):
        return QSize(800, 120)

    def set_samplerate(self, sr):
        self._set_samplerate(sr)

    def _set_samplerate(self, sr):
        self.sr = int(sr)
        self.capacity = int(self.sr * self.seconds * 2)
        self.ring = np.zeros(self.capacity, dtype=np.float32)
        self.wpos = 0
        if self.back:
            self.back.fill(self.bg)

    def _feed_ring_from_queue(self):
        """Procesa cola de entrada - rápido y sin bloqueos"""
        count = 0
        while self._in_queue and count < 5:  # Máximo 5 chunks por tick
            chunk = self._in_queue.popleft()
            n = chunk.size
            self._in_len -= n
            
            n1 = min(n, self.capacity - self.wpos)
            self.ring[self.wpos:self.wpos+n1] = chunk[:n1]
            self.wpos = (self.wpos + n1) % self.capacity
            rem = n - n1
            if rem > 0:
                self.ring[0:rem] = chunk[n1:n1+rem]
                self.wpos = rem
            count += 1

    def _tick(self):
        """
        Tick INDEPENDIENTE - se ejecuta a velocidad constante
        FIX #7: Agregado límite al acumulador de píxeles
        """
        # Procesar datos si hay
        self._feed_ring_from_queue()
        
        # Calcular tiempo transcurrido REAL
        current_time = time.perf_counter()
        dt = current_time - self._last_update_time
        self._last_update_time = current_time
        
        # Avanzar scroll basado en TIEMPO REAL (no en cadencia)
        pixels_to_advance = self.px_per_sec * dt
        
        # ✅ FIX #7: LÍMITE SUPERIOR para evitar acumulación infinita
        # Si el framerate baja mucho, limitamos a 100 píxeles máximo
        self._px_accumulated = min(self._px_accumulated + pixels_to_advance, 100.0)
        
        # Siempre repintar para mantener fluidez
        self.update()

    def _read_window(self, num_samples):
        """Lee ventana desde el ring buffer"""
        if num_samples <= 0 or num_samples > self.capacity:
            return np.zeros(max(1, num_samples), dtype=np.float32)
        
        start = int((self.wpos - num_samples) % self.capacity)
        
        if start + num_samples <= self.capacity:
            return self.ring[start:start+num_samples].copy()
        else:
            n1 = self.capacity - start
            n2 = num_samples - n1
            return np.concatenate([self.ring[start:], self.ring[:n2]]).copy()

    def _ensure_backbuffer(self):
        w, h = self.width(), self.height()
        if self.back is None or self._last_width != w or self._last_height != h:
            self.back = QPixmap(w, h)
            self.back.fill(self.bg)
            self._last_width = w
            self._last_height = h
            self._px_accumulated = 0.0

    def paintEvent(self, ev):
        """Paint con scroll continuo y fluido"""
        w = max(1, self.width())
        h = max(1, self.height())
        self._ensure_backbuffer()

        # Calcular cuántos pixels scrollear (puede ser fraccionario)
        dx = int(self._px_accumulated)
        
        if dx >= 1:
            self._px_accumulated -= dx
            
            # Limitar para evitar saltos bruscos
            dx = min(dx, 20)
            
            p = QPainter(self.back)
            p.setRenderHint(QPainter.Antialiasing, False)  # Más rápido
            
            # Scroll horizontal
            p.drawPixmap(0, 0, self.back, dx, 0, w-dx, h)
            p.fillRect(w-dx, 0, dx, h, self.bg)

            # Dibujar nueva franja
            spp = max(1, int(self.sr / self.px_per_sec))
            need = dx * spp
            
            data = self._read_window(need) if need > 0 else np.zeros(1, np.float32)
            if data.size < need:
                data = np.pad(data, (need - data.size, 0), mode="constant")

            try:
                samples_needed = dx * spp
                if data.size != samples_needed:
                    if data.size > samples_needed:
                        data = data[:samples_needed]
                    else:
                        data = np.pad(data, (0, samples_needed - data.size))
                cols = data.reshape(dx, spp)
            except:
                cols = np.zeros((dx, spp), dtype=np.float32)

            vmin = cols.min(axis=1)
            vmax = cols.max(axis=1)

            mid = h // 2
            scale = h * 0.45
            
            # Grid
            p.setPen(QPen(self.grid, 1))
            p.drawLine(w-dx, mid, w-1, mid)
            
            # Waveform
            pen = QPen(self.fg, 1)
            p.setPen(pen)
            for i in range(dx):
                x = w - dx + i
                y0 = int(mid - vmax[i] * scale)
                y1 = int(mid - vmin[i] * scale)
                if y0 == y1:
                    y1 = y0 + 1
                p.drawLine(x, y0, x, y1)
            
            p.end()

        # Pintar en pantalla
        p2 = QPainter(self)
        p2.setRenderHint(QPainter.Antialiasing, False)
        p2.drawPixmap(0, 0, self.back)
        p2.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._last_width = 0
        self._last_height = 0
        self.update()