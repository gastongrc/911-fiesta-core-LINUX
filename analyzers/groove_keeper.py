# analyzers/groove_keeper.py – GROOVE KEEPER (fix: protecciones mínimas contra cuelgues)
import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from rhythm_tools import mono, env_onset, find_peaks, gaps_ms

EPS = 1e-9

def _norm01(v):
    if v is None: return 0.0
    v = float(v)
    if v > 1.5: v *= 0.01  # 0..100 → 0..1
    return float(np.clip(v, 0.0, 1.0))

def _norm_match(m):
    try: m = float(50.0 if m is None else m)
    except: m = 50.0
    if 0.0 <= m < 1.0: m *= 100.0
    elif m == 1.0:     m = 100.0
    return float(np.clip(m, 0.0, 100.0))

def _robust_med(v):
    if v.size == 0: return 0.0
    lo, hi = np.percentile(v, [10, 90])
    vv = v[(v >= lo) & (v <= hi)]
    return float(np.median(vv if vv.size else v))

class GrooveKeeper(BaseModule):
    name = "GROOVE KEEPER"
    flag_name = "GROOVE_KEEPER"  # V11: Flag para votación en BaseGolpe

    def __init__(self):
        super().__init__()
        self.card = ModuleCard(self.name)
        # OPTIMIZADO: smooth default
        self.card.add_slider("thr",   "Umbral pico", 0.10, 0.90, 0.35)
        self.card.add_slider("swing", "Swing ratio", 0.50, 0.70, 0.60)
        self.card.add_slider("tol",   "Tolerancia",  0.02, 0.20, 0.08)
        self.card.add_slider("smooth","Suavizado",   0.10, 0.60, 0.22)
        
        # NUEVO: slider de hold
        self.card.add_slider("hold", "Hold (ms)", 50, 400, 120)
        
        self._ema_v = 0.0
        self._r_est = 0.0
        self.detected = False  # V11: Flag para votación en BaseGolpe

        # Contadores para detectar cuelgues
        self._process_count = 0
        self._failure_count = 0
        self._last_reset = 0

    def process(self, block, sr):
        # Incrementar contador SIEMPRE al inicio
        self._process_count += 1
        
        # Auto-reset cada ~12 segundos para limpiar estado corrupto - OPTIMIZADO
        if self._process_count - self._last_reset > 600:  # ~12s a 50Hz
            self._cleanup_state()
            self._last_reset = self._process_count
        
        if block is None or sr is None or sr <= 0: 
            self._failure_count += 1
            return self._render(self._ema_v)
            
        # Protección contra rhythm_tools.mono()
        try:
            x = mono(block).astype(np.float32, copy=False)
        except Exception:
            self._failure_count += 1
            # Fallback: conversión manual a mono
            try:
                if len(block.shape) == 1:
                    x = block.astype(np.float32, copy=False)
                else:
                    x = np.mean(block, axis=1).astype(np.float32, copy=False)
            except Exception:
                return self._render(self._ema_v)
        
        n = len(x)
        if n == 0: return self._render(self._ema_v)
        dt = n / float(sr)

        # Verificar que x no tiene valores anómalos
        if not np.isfinite(x).all():
            self._failure_count += 1
            return self._render(self._ema_v)

        # Gate de silencio (~ -74 dBFS): en pausa baja suave
        rms = float(np.sqrt(np.mean(x*x)) + 1e-12)
        if rms < 2e-4:
            a = np.exp(-dt / 0.18)
            self._ema_v = float(a * self._ema_v)
            self._r_est *= 0.90
            return self._render(float(np.clip(self._ema_v, 0.0, 1.0)))

        # CRÍTICO: Proteger las llamadas a rhythm_tools que pueden colgarse
        try:
            # Onsets → picos → gaps en ms
            env, hop = env_onset(x)
            
            # Verificar que env_onset retornó algo válido
            if env is None or hop is None or len(env) == 0:
                raise Exception("env_onset retornó datos inválidos")
                
            thr = float(np.clip(self.card.get_value("thr"), 0.0, 1.0))
            pk = find_peaks(env, thr)
            
            # Verificar que find_peaks retornó algo válido
            if pk is None or len(pk) == 0:
                raise Exception("find_peaks no encontró picos")
                
            g = gaps_ms(pk, hop, sr)  # array de gaps en ms
            
            # Verificar que gaps_ms retornó algo válido
            if g is None:
                raise Exception("gaps_ms retornó None")
                
        except Exception as e:
            # Si rhythm_tools falla, aplicar decay y continuar
            self._failure_count += 1
            self._ema_v *= 0.98  # Decay suave
            self._r_est *= 0.95
            
            # Si hay demasiados fallos consecutivos, reset más agresivo
            if self._failure_count > 50:
                self._emergency_recovery()
                
            return self._render(float(np.clip(self._ema_v, 0.0, 1.0)))

        # Reset contador de fallos si llegamos aquí (rhythm_tools funcionó)
        self._failure_count = max(0, self._failure_count - 1)

        v_raw = 0.0
        r_est = None
        if g.size >= 4:
            a = g[0::2]
            b = g[1::2]
            if a.size > 0 and b.size > 0:
                ma = _robust_med(a)
                mb = _robust_med(b)
                denom = ma + mb
                if denom > EPS:
                    r = ma / denom  # 0..1 (0.5 recto, ~0.66 shuffle 2:1)
                    r_est = r
                    target = float(np.clip(self.card.get_value("swing"), 0.0, 1.0))
                    tol = float(np.clip(self.card.get_value("tol"), 0.005, 0.50))
                    err = abs(r - target)
                    v_raw = float(np.clip(1.0 - err/tol, 0.0, 1.0))

        # Track del swing estimado (suave)
        if r_est is None:
            self._r_est *= 0.92
        else:
            self._r_est = 0.85*self._r_est + 0.15*r_est

        # Suavizado visual (α↑ = responde más)
        alpha = float(np.clip(self.card.get_value("smooth"), 0.05, 0.95))
        self._ema_v = (1.0 - alpha) * self._ema_v + alpha * v_raw
        v = float(np.clip(self._ema_v, 0.0, 1.0))

        self._render(v)
    
    def _cleanup_state(self):
        """Limpieza periódica del estado interno"""
        try:
            # Verificar y corregir valores que pueden haberse corrompido
            if not np.isfinite(self._ema_v):
                self._ema_v = 0.0
            if not np.isfinite(self._r_est):
                self._r_est = 0.0
                
            # Clampear valores
            self._ema_v = float(np.clip(self._ema_v, 0.0, 1.0))
            self._r_est = float(np.clip(self._r_est, 0.0, 1.0))
            
            # Reducir contador de fallos gradualmente
            self._failure_count = max(0, self._failure_count - 10)
            
        except Exception:
            # Si la limpieza falla, reset completo
            self._ema_v = 0.0
            self._r_est = 0.0
            self._failure_count = 0
    
    def _emergency_recovery(self):
        """Recuperación de emergencia tras muchos fallos"""
        try:
            # Reset suave del estado
            self._ema_v *= 0.5
            self._r_est *= 0.5
            self._failure_count = 0
            
            # Forzar garbage collection si está disponible
            try:
                import gc
                gc.collect()
            except:
                pass
                
        except Exception:
            # Reset total si todo falla
            self._ema_v = 0.0
            self._r_est = 0.0
            self._failure_count = 0

    def _render(self, v):
        # Proteger _render también
        try:
            self.card.set_value(v)
            
            # Status informativo
            try:
                txt_r = f"{self._r_est:.2f}" if self._r_est > 0 else "–"
                # Mostrar contador de fallos si hay problemas
                status = f"Swing est: {txt_r} – Obj: {float(self.card.get_value('swing')):.2f}"
                if self._failure_count > 5:
                    status += f" (Err: {self._failure_count})"
                self.card.set_status(status)
            except Exception:
                # Status de emergencia
                try:
                    self.card.set_status(f"Proc: {self._process_count} | Fallos: {self._failure_count}")
                except Exception:
                    pass

            # ON universal (MATCH/Min/Max normalizados)
            lo, hi = self.card.get_thresholds()
            lo = _norm01(lo); hi = _norm01(hi)
            if hi < lo: lo, hi = hi, lo
            mreq = _norm_match(self.card.get_match())
            is_on = (lo <= v <= hi) and ((v*100.0) >= mreq - 1e-6)
            self.card.set_on(is_on)
            self.detected = is_on  # V11: Flag para votación

        except Exception:
            # Si render falla completamente, al menos intentar set_value
            try:
                self.card.set_value(0.0)
            except Exception:
                pass