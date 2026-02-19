import math, time, threading
import numpy as np
import sounddevice as sd

def rms(x: np.ndarray) -> float:
    if x is None or x.size == 0: return 0.0
    return float(np.sqrt(np.mean(np.square(x), dtype=np.float64)))

def to_stereo_f32(block, ch_want=2) -> np.ndarray:
    x = np.asarray(block)
    if x.ndim == 1:
        x = x.astype(np.float32, copy=False).reshape(-1, 1)
    else:
        x = x.astype(np.float32, copy=False)
    if x.shape[1] >= ch_want:
        return x[:, :ch_want]
    return np.repeat(x, ch_want, axis=1)

class AudioEngine:
    """
    Cadena: Input -> DC-Block -> HP 30 Hz -> (opcional Notch 50/60) -> [RAW]
            RAW * env -> [GATED]
    - calibrate_noise() usa RAW
    - get_recent(..., raw=True) devuelve RAW
    - get_recent(..., raw=False) devuelve GATED
    
    TAREA 1: Gate estable con schmitt trigger + min-open/min-close 80ms.
    """

    def __init__(self, device_index=None, samplerate=None, channels=2, blocksize=1024,
                 ring_seconds=3.0, use_notch=False, mains_hz=50.0,
                 gate_open_ratio=2.5, gate_close_ratio=1.6,
                 env_attack_ms=12.0, env_release_ms=180.0):
        self.device_index = device_index
        self.req_samplerate = samplerate
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.ring_seconds = float(max(1.0, ring_seconds))
        self.use_notch = bool(use_notch)
        self.mains_hz = float(mains_hz)

        # TAREA 1: parámetros de tuning del gate
        self.cfg = {
            'gate_open_ratio': float(gate_open_ratio),
            'gate_close_ratio': float(gate_close_ratio),
            'env_attack_ms': float(env_attack_ms),
            'env_release_ms': float(env_release_ms)
        }

        self.stream = None
        self.running = False
        self.samplerate = None

        # buffers (RAW y GATED)
        cap = int((self.req_samplerate or 44100) * self.ring_seconds)
        self._raw_filt = np.zeros((cap, 2), dtype=np.float32)   # RAW filtrado (DC+HP+notch)
        self._raw_clean = np.zeros((cap, 2), dtype=np.float32)  # RAW REAL sin filtros
        self._gated = np.zeros((cap, 2), dtype=np.float32)
        self._wr = 0
        self._len = 0
        self._lock = threading.Lock()

        # filtros
        self.dc_fc = 5.0
        self.dc_R = None
        self.dc_prev_x = np.zeros(2, np.float32)
        self.dc_prev_y = np.zeros(2, np.float32)

        self.hp_fc = 10.0  # FIX: dejar pasar más subgrave para BPM
        self.hp_b0 = self.hp_b1 = self.hp_a1 = 0.0
        self.hp_prev_x = np.zeros(2, np.float32)
        self.hp_prev_y = np.zeros(2, np.float32)

        self.notch_b = None
        self.notch_a = None
        self.notch_z = np.zeros((2, 2), np.float32)

        # gate
        self.noise_floor_rms = 0.002
        self.gate_open = False  # TAREA 1: estado del gate
        self.env = 0.0
        self._atk = self._rel = 0.0
        self.last_rms_raw = 0.0
        
        # TAREA 1: min-open/min-close 80ms
        self._min_gate_samples = 0
        self._gate_hold_counter = 0

        # FIX 1+2: Kick detector incremental read with real timestamps
        self._last_cb_ts: float = 0.0     # monotonic timestamp of last callback
        self._kick_rd: int = 0            # read cursor for kick-only path

    # ---------- init filtros ----------
    def _recalc_filters(self):
        """
        FIX #10: Proteger con lock para evitar race condition con callback.
        """
        with self._lock:
            fs = float(self.samplerate or 44100)

            # DC blocker
            self.dc_R = math.exp(-2.0 * math.pi * self.dc_fc / fs)

            # HP 1er orden
            K = math.tan(math.pi * self.hp_fc / fs)
            a0 = 1.0 + K
            self.hp_b0 =  1.0 / a0
            self.hp_b1 = -1.0 / a0
            self.hp_a1 = (1.0 - K) / a0

            # notch mains
            if self.use_notch and self.mains_hz > 0:
                f0 = self.mains_hz; Q = 12.0
                w0 = 2.0 * math.pi * f0 / fs
                alpha = math.sin(w0) / (2.0 * Q)
                b0 = 1.0; b1 = -2.0*math.cos(w0); b2 = 1.0
                a0 = 1.0 + alpha; a1 = -2.0*math.cos(w0); a2 = 1.0 - alpha
                self.notch_b = np.array([b0/a0, b1/a0, b2/a0], np.float32)
                self.notch_a = np.array([1.0, a1/a0, a2/a0], np.float32)
            else:
                self.notch_b = None; self.notch_a = None

            # envelope coef
            self._atk = math.exp(-1.0 / (fs * (self.cfg['env_attack_ms']/1000.0)))
            self._rel = math.exp(-1.0 / (fs * (self.cfg['env_release_ms']/1000.0)))
            
            # TAREA 1: samples para 80ms de min-hold
            self._min_gate_samples = int(0.080 * fs)

    # ---------- helpers ----------
    def _dc_block(self, x, ch):
        y = np.empty_like(x)
        prev_x = float(self.dc_prev_x[ch])
        prev_y = float(self.dc_prev_y[ch])
        R = float(self.dc_R)
        for i in range(x.size):
            xi = x[i]
            yi = (xi - prev_x) + R * prev_y
            y[i] = yi
            prev_x = xi; prev_y = yi
        self.dc_prev_x[ch] = prev_x
        self.dc_prev_y[ch] = prev_y
        return y

    def _hp_30(self, x, ch):
        y = np.empty_like(x)
        b0, b1, a1 = self.hp_b0, self.hp_b1, self.hp_a1
        xm1 = float(self.hp_prev_x[ch])
        ym1 = float(self.hp_prev_y[ch])
        for i in range(x.size):
            xi = x[i]
            yi = b0*xi + b1*xm1 - a1*ym1
            y[i] = yi
            xm1 = xi; ym1 = yi
        self.hp_prev_x[ch] = xm1
        self.hp_prev_y[ch] = ym1
        return y

    def _biquad(self, x, b, a, z, ch):
        y = b[0]*x + z[ch,0]
        z[ch,0] = b[1]*x - a[1]*y + z[ch,1]
        z[ch,1] = b[2]*x - a[2]*y
        return y

    # ---------- callback ----------
    def _callback(self, indata, frames, time_info, status):
        # FIX 1: Record capture-time timestamp (closest to real audio arrival)
        self._last_cb_ts = time.monotonic()

        x = to_stereo_f32(indata, 2)

        # RAW REAL (sin filtros, sin DC, sin HP, sin notch, sin gate)
        raw_clean = np.clip(x.copy().astype(np.float32), -1.0, 1.0)

        # DC block + HP
        y = np.empty_like(x)
        for ch in (0,1):
            y[:, ch] = self._hp_30(self._dc_block(x[:, ch], ch), ch)
        
        # Notch (opcional)
        if self.notch_b is not None:
            b, a = self.notch_b, self.notch_a
            for ch in (0,1):
                xn = y[:, ch]
                yn = np.empty_like(xn)
                for i in range(xn.size):
                    yn[i] = self._biquad(xn[i], b, a, self.notch_z, ch)
                y[:, ch] = yn

        # RAW después de filtros
        raw = np.clip(y, -3.0, 3.0)
        self.last_rms_raw = rms(raw)

        # TAREA 1: schmitt trigger + min-open/min-close
        open_th  = self.noise_floor_rms * self.cfg['gate_open_ratio']
        close_th = self.noise_floor_rms * self.cfg['gate_close_ratio']
        
        # Decisión de gate con histéresis
        if not self.gate_open:
            if self.last_rms_raw >= open_th:
                self.gate_open = True
                self._gate_hold_counter = self._min_gate_samples
        else:
            if self.last_rms_raw <= close_th:
                if self._gate_hold_counter <= 0:
                    self.gate_open = False
                    self._gate_hold_counter = self._min_gate_samples
        
        # Decrementar contador de hold
        if self._gate_hold_counter > 0:
            self._gate_hold_counter -= frames
        
        # Envelope suavizada
        target = 1.0 if self.gate_open else 0.0
        if target > self.env:
            self.env = target + (self.env - target) * self._atk
        else:
            self.env = target + (self.env - target) * self._rel

        # Clamp muy pequeño para cero real
        if self.env < 1e-3:
            self.env = 0.0

        gated = (raw * self.env).astype(np.float32, copy=False)

        # escribir buffers (raw_filt, raw_clean, gated)
        with self._lock:
            N = raw.shape[0]
            cap = self._raw_filt.shape[0]
            if N >= cap:
                self._raw_filt[:] = raw[-cap:]
                self._raw_clean[:] = raw_clean[-cap:]
                self._gated[:] = gated[-cap:]
                self._wr = 0; self._len = cap
            else:
                end = self._wr + N
                if end <= cap:
                    self._raw_filt[self._wr:end] = raw
                    self._raw_clean[self._wr:end] = raw_clean
                    self._gated[self._wr:end] = gated
                else:
                    k = cap - self._wr
                    self._raw_filt[self._wr:] = raw[:k]
                    self._raw_filt[:end-cap] = raw[k:]
                    self._raw_clean[self._wr:] = raw_clean[:k]
                    self._raw_clean[:end-cap] = raw_clean[k:]
                    self._gated[self._wr:] = gated[:k]
                    self._gated[:end-cap] = gated[k:]
                self._wr = (self._wr + N) % cap
                self._len = min(cap, self._len + N)

    # ---------- API ----------
    def start(self):
        if self.running: return
        dev = self.device_index if self.device_index is not None else sd.default.device[0]
        info = sd.query_devices(dev, 'input')
        fs = int(self.req_samplerate or info['default_samplerate'])
        self.samplerate = fs
        # realocar buffers al SR real
        cap = int(self.samplerate * self.ring_seconds)
        self._raw_filt  = np.zeros((cap, 2), np.float32)
        self._raw_clean = np.zeros((cap, 2), np.float32)
        self._gated = np.zeros((cap, 2), np.float32)
        self._wr = 0; self._len = 0
        self._kick_rd = 0  # FIX 2: reset kick read cursor

        self._recalc_filters()

        self.stream = sd.InputStream(
            device=dev, channels=self.channels, samplerate=self.samplerate,
            blocksize=self.blocksize, dtype='float32', callback=self._callback
        )
        self.stream.start()
        self.running = True

    def stop(self):
        if not self.running: return
        try:
            self.stream.stop(); self.stream.close()
        finally:
            self.stream = None
            self.running = False

    def get_status(self):
        """TAREA 1: telemetría completa del gate"""
        return {
            "samplerate": self.samplerate or 0,
            "blocksize": self.blocksize,
            "rms": self.last_rms_raw,
            "env": self.env,
            "noise": self.noise_floor_rms,
            "gate_open": self.gate_open,
            "open_ratio": self.cfg['gate_open_ratio'],
            "close_ratio": self.cfg['gate_close_ratio']
        }

    def _read_ring(self, seconds: float, raw: bool) -> np.ndarray:
        if self._len == 0 or self.samplerate is None:
            return None
        n = int(max(1, seconds * self.samplerate))
        with self._lock:
            cap = self._raw_filt.shape[0]
            n = min(n, self._len)
            start = (self._wr - n) % cap
            buf = self._raw_clean if raw else self._raw_filt
            if start + n <= cap:
                data = buf[start:start+n].copy()
            else:
                k = cap - start
                data = np.vstack((buf[start:], buf[:n-k])).copy()
        return data

    def get_recent(self, seconds: float, raw: bool=False) -> np.ndarray:
        return self._read_ring(seconds, raw)

    def read_new_for_kick(self):
        """
        FIX 1+2: Read only NEW samples since last kick read, with real block_start_ts.

        Returns:
            tuple: (block, block_start_ts, sr) — block is stereo float32 ndarray,
                   block_start_ts is monotonic time of first sample in block,
                   sr is sample rate.  Returns (None, 0.0, 0) if no new data.
        """
        if self._len == 0 or self.samplerate is None or self._last_cb_ts == 0.0:
            return None, 0.0, 0

        with self._lock:
            cap = self._raw_filt.shape[0]
            wr = self._wr
            rd = self._kick_rd

            # Compute new samples available
            new = (wr - rd) % cap if wr != rd else 0
            if new == 0:
                return None, 0.0, 0

            # Cap at 0.25s to avoid processing stale backlog
            max_new = int(0.25 * self.samplerate)
            if new > max_new:
                rd = (wr - max_new) % cap
                new = max_new

            # Read from ring buffer (_raw_filt = DC+HP filtered)
            if rd + new <= cap:
                data = self._raw_filt[rd:rd + new].copy()
            else:
                k = cap - rd
                data = np.vstack((self._raw_filt[rd:], self._raw_filt[:new - k])).copy()

            # FIX 1: block_start_ts = last callback time minus buffer duration
            block_start_ts = self._last_cb_ts - (new / self.samplerate)

            # Advance cursor
            self._kick_rd = wr

        return data, block_start_ts, self.samplerate

    def calibrate_noise(self, seconds=1.5) -> float:
        """
        TAREA 1: Recalibra SOLO si hay > 1.5s de silencio estimado.
        Usa percentil 85 y clamp a [1e-6, 0.1].
        """
        t0 = time.time()
        vals = []
        step = 0.1
        
        # Recolectar muestras
        while time.time() - t0 < float(seconds):
            blk = self.get_recent(step, raw=True)
            if blk is not None and blk.size:
                vals.append(rms(blk))
            time.sleep(0.05)
        
        if not vals:
            print("[AUDIO] Skip noise calibration (no data).")
            return self.noise_floor_rms
        
        # Verificar si tenemos suficiente silencio (>1.5s)
        if len(vals) < 10:  # ~1.5s a paso 0.1s + sleep 0.05s
            print("[AUDIO] Skip noise calibration (insufficient silence).")
            return self.noise_floor_rms
        
        # Calcular noise floor
        arr = np.array(vals, dtype=np.float64)
        floor = float(np.percentile(arr, 85))
        
        # TAREA 1: clamp a [1e-6, 0.1]
        floor = float(np.clip(floor, 1e-6, 0.1))
        self.noise_floor_rms = floor
        print(f"[AUDIO] Noise floor calibrated: {floor:.6f}")
        return floor