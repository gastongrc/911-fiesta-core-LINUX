# analyzers/texture_cleaner.py — TEXTURE CLEANER
# v2025-09-02: match OK, smoothing por tau, gate dB calibrable, LED por densidad real, status
# v2025-09-05: CORRECCIONES MÍNIMAS - mantener funcionalidad original

import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import mono

EPS = 1e-12

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01  # 0..100 → 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    """0..1 o 0..100 → 0..100 (incluye m==1.0 ⇒ 100%)."""
    try:
        m = float(50.0 if m is None else m)
    except:
        m = 50.0
    if 0.0 <= m <= 1.0:
        m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class TextureCleaner(BaseModule):
    name = "TEXTURE CLEANER"

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)

        # Densidad máxima "aceptable" (0..1) — cuanto menor, más "limpio"
        self.card.add_slider("dens",    "Densidad máx",        0.10, 0.90, 0.60)
        # Suavizado unificado: 0..0.95 → τ 80..600 ms (↑ = más suave)
        self.card.add_slider("smooth",  "Suavizado",           0.00, 0.95, 0.25)
        # Gate de silencio (dBFS): por debajo consideramos limpio (v=1) con caída suave
        self.card.add_slider("sil_db",  "Gate silencio (dB)",  40.0, 70.0, 60.0)
        # Peso al anti-onsets (0..1): cuánto castiga la actividad espectral
        self.card.add_slider("wflux",   "Peso flux",            0.0,  1.0,  0.9)

        self.card.add_led("ok", "Limpio")

        # Estado
        self._vu = 0.0
        self._prev_mag = None
        self._dbg = 0
        
        # MEJORA: Cache para ventanas Hann (optimización de memoria)
        self._hann_cache = {}

    # ---- helpers ----
    def _get_hann_window(self, N):
        """Cache de ventanas Hann para evitar recrearlas constantemente."""
        if N not in self._hann_cache:
            # Limitar cache para no consumir demasiada memoria
            if len(self._hann_cache) > 8:
                self._hann_cache.clear()
            self._hann_cache[N] = np.hanning(N).astype(np.float32)
        return self._hann_cache[N]

    def _fft_mag(self, x: np.ndarray, max_n: int = 4096):
        """Magnitud de FFT (últimos N, ventana Hann)."""
        n = len(x)
        N = min(n, max_n)
        N = 1 << (N - 1).bit_length()  # potencia de 2
        
        # MEJORA: Usar ventana cacheada
        window = self._get_hann_window(N)
        xw = x[-N:] * window
        
        X = np.fft.rfft(xw)
        mag = np.abs(X).astype(np.float32) + EPS  # CORRECCIÓN: cambié 1e-12 por EPS
        return mag

    def _entropy(self, mag: np.ndarray) -> float:
        """Entropía espectral normalizada 0..1 (densidad de "capas")."""
        P = (mag ** 2)
        p = P / float(P.sum() + EPS)  # CORRECCIÓN: cambié 1e-12 por EPS
        ent = float(-np.sum(p * np.log(p + 1e-30)) / np.log(len(p) + EPS))  # CORRECCIÓN: EPS
        return float(np.clip(ent, 0.0, 1.0))

    def _specflux(self, mag: np.ndarray) -> float:
        """Flux espectral normalizado 0..1 (anti-onsets / actividad)."""
        if self._prev_mag is None or len(self._prev_mag) != len(mag):
            self._prev_mag = mag.copy()  # CORRECCIÓN: usar .copy() explícito
            return 0.0
        diff = mag - self._prev_mag
        pos = float(np.maximum(diff, 0.0).sum())
        base = float((mag + self._prev_mag).sum()) * 0.5 + EPS  # CORRECCIÓN: EPS
        self._prev_mag = mag.copy()  # CORRECCIÓN: usar .copy() explícito
        return float(np.clip(pos / base, 0.0, 1.0))

    def process(self, block, sr):
        if block is None or sr is None or sr <= 0: return
        x = mono(block).astype(np.float32, copy=False)
        n = len(x)
        if n == 0: return
        dt = n / float(sr)

        # Nivel global (dBFS)
        rms = float(np.sqrt(np.mean(x*x)) + EPS)
        dbfs = 20.0 * np.log10(rms + EPS)

        # Gate de silencio: en Bajada, silencio = limpio (v alto)
        sil_db = float(np.clip(self.card.get_value("sil_db"), 30.0, 80.0))
        if dbfs < -sil_db:
            a_fast = np.exp(-dt / 0.12)          # caída rápida hacia 1
            self._vu = (1.0 - a_fast) * 1.0 + a_fast * self._vu
            v = float(np.clip(self._vu, 0.0, 1.0))
            try: 
                self.card.set_status(f"silencio: {dbfs:.1f} dBFS | v={v:.2f}")
            except AttributeError:  # CORRECCIÓN: excepción específica
                pass
            return self._render(v, dens_est=0.0)

        # FFT → entropía (densidad) + flux (actividad)
        mag = self._fft_mag(x)
        ent = self._entropy(mag)                 # 0..1 (↑ = más denso/"sucio")
        flux = self._specflux(mag)               # 0..1 (↑ = más actividad)
        wflux = float(np.clip(self.card.get_value("wflux"), 0.0, 1.0))

        # Limpieza "cruda": poca densidad y poca actividad
        # (castigo de actividad: clean_core * (1 - wflux*flux))
        clean_core = (1.0 - ent) * (1.0 - wflux * flux)
        clean_core = float(np.clip(clean_core, 0.0, 1.0))

        # Suavizado por τ 80..600 ms
        smooth = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
        tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
        a = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - a) * clean_core + a * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))

        # Status liviano
        self._dbg += 1
        if (self._dbg % 90) == 0:
            try:
                self.card.set_status(f"{dbfs:.1f} dBFS | ent={ent:.2f} flux={flux:.2f} | v={v:.2f}")
            except AttributeError:  # CORRECCIÓN: excepción específica
                pass

        self._render(v, dens_est=ent)

    def _render(self, v, dens_est: float):
        # VU
        self.card.set_value(v)

        # LED "Limpio": usa DENSIDAD real (no 1−v tras suavizado)
        dens_max = float(np.clip(self.card.get_value("dens"), 0.10, 0.90))
        self.card.set_led("ok", float(dens_est) <= dens_max)

        # ON universal: thresholds y MATCH normalizados
        lo, hi = self.card.get_thresholds()
        lo = _norm01(lo); hi = _norm01(hi)
        if hi < lo: lo, hi = hi, lo
        mreq = _norm_match(self.card.get_match())
        self.card.set_on((lo <= v <= hi) and ((v * 100.0) >= mreq - 1e-6))