import numpy as np
from base_module import BaseModule
from module_card import ModuleCard
from dsp_utils import mono

EPS = 1e-12

def _norm01(v):
    """Normaliza valor a rango 0..1, admitiendo entrada 0..100"""
    if v is None: 
        return 0.0
    try:
        v = float(v)
        if v > 1.5: 
            v *= 0.01   # convierte 0..100 a 0..1
        return float(np.clip(v, 0.0, 1.0))
    except:
        return 0.0

def _norm_match(m):
    """Normaliza match a rango 0..100"""
    try:
        m = float(50.0 if m is None else m)
    except:
        m = 50.0
    if 0.0 <= m <= 1.0:
        m *= 100.0
    return float(np.clip(m, 0.0, 100.0))

class BreakSpotter(BaseModule):
    """
    Detecta microcortes/gaps: silencio breve entre gmin..gmax ms.
    Versión robusta con mejor manejo de errores y compatibilidad.
    """
    name = "BREAK SPOTTER"

    def __init__(self):
        try:
            super().__init__()
            self.card = ModuleCard(self.name)
            self._initialize_controls()
            self._initialize_state()
        except Exception as e:
            print(f"Error inicializando BreakSpotter: {e}")
            # Estado mínimo para evitar crash
            self._initialize_minimal_state()

    def _initialize_controls(self):
        """Inicializa controles de la UI de forma segura"""
        try:
            # Parámetros básicos
            self.card.add_slider("gmin",   "Gap mín (ms)",      20.0,  800.0,  80.0)
            self.card.add_slider("gmax",   "Gap máx (ms)",      80.0, 2000.0, 240.0)
            self.card.add_slider("thdb",   "Umbral (dBFS)",    -80.0,  -20.0, -45.0)
            self.card.add_slider("env_ms", "Env RMS (ms)",       4.0,   30.0,  10.0)
            self.card.add_slider("hold",   "Hold evento (ms)",  50.0,  600.0, 200.0)
            self.card.add_slider("smooth", "Suavizado",          0.0,    0.95, 0.25)
            
            self.card.add_led("brk", "Break detectado")
        except Exception as e:
            print(f"Error inicializando controles: {e}")

    def _initialize_state(self):
        """Inicializa estado interno de forma segura"""
        # Estado básico de gap
        self._in_gap = False
        self._gap_samples = 0
        self._last_gap_ms = 0.0
        
        # Estado de VU y eventos
        self._vu = 0.0
        self._event_ms_left = 0.0
        self._event_count = 0
        
        # Estado de hysteresis simple
        self._below_threshold = True
        
        # Debug
        self._debug_counter = 0
        self._current_dbfs = -100.0
        
        # Flag de inicialización
        self._initialized = True

    def _initialize_minimal_state(self):
        """Estado mínimo en caso de error de inicialización"""
        self._in_gap = False
        self._gap_samples = 0
        self._vu = 0.0
        self._initialized = False

    def _get_param_safe(self, param_name, default_value, min_val=None, max_val=None):
        """Obtiene parámetro de forma segura con fallback"""
        try:
            if hasattr(self, 'card') and self.card:
                value = self.card.get_value(param_name)
                if value is not None:
                    value = float(value)
                    if min_val is not None and max_val is not None:
                        value = np.clip(value, min_val, max_val)
                    return value
        except:
            pass
        return default_value

    def _validate_params(self):
        """Valida parámetros con valores seguros por defecto"""
        gmin = self._get_param_safe("gmin", 80.0, 5.0, 5000.0)
        gmax = self._get_param_safe("gmax", 240.0, 20.0, 10000.0)
        
        # Asegurar orden correcto
        if gmax < gmin + 10.0:
            gmax = gmin + 10.0
            
        thdb = self._get_param_safe("thdb", -45.0, -100.0, -10.0)
        env_ms = self._get_param_safe("env_ms", 10.0, 2.0, 60.0)
        hold_ms = self._get_param_safe("hold", 200.0, 10.0, 2000.0)
        smooth = self._get_param_safe("smooth", 0.25, 0.0, 0.95)
        
        return gmin, gmax, thdb, env_ms, hold_ms, smooth

    def _rms_env_simple(self, x, sr, ms):
        """Envolvente RMS simple y robusta"""
        try:
            if len(x) == 0:
                return np.array([])
                
            n = max(3, int(sr * (ms / 1000.0)))
            n = min(n, len(x))  # No exceder longitud del array
            
            if n < 3:
                # Para arrays muy cortos, usar RMS directo
                return np.sqrt(x.astype(np.float32) ** 2 + EPS)
            
            if n % 2 == 0: 
                n += 1
                
            # Convolución simple
            x_sq = x.astype(np.float32) ** 2
            kernel = np.ones(n, dtype=np.float32) / float(n)
            
            # Usar mode="same" pero con manejo de bordes
            result = np.convolve(x_sq, kernel, mode="same")
            return np.sqrt(result + EPS)
            
        except Exception as e:
            print(f"Error en RMS: {e}")
            # Fallback: RMS directo sin filtrado
            return np.sqrt(x.astype(np.float32) ** 2 + EPS)

    def _update_gap_state(self, is_silent, sr):
        """Actualiza estado del gap de forma simple"""
        events = []
        
        if is_silent:
            if not self._in_gap:
                # Inicio de gap
                self._in_gap = True
                self._gap_samples = 1
            else:
                # Continuar gap
                self._gap_samples += 1
        else:
            if self._in_gap:
                # Fin de gap - verificar si está en rango
                gap_ms = 1000.0 * self._gap_samples / float(sr)
                self._last_gap_ms = gap_ms
                
                gmin, gmax, _, _, _, _ = self._validate_params()
                if gmin <= gap_ms <= gmax:
                    events.append(gap_ms)
                    self._event_count += 1
                
                # Resetear gap
                self._in_gap = False
                self._gap_samples = 0
                
        return events

    def _calculate_vu_simple(self, gmin, gmax):
        """Calcula VU de forma simple y robusta"""
        # Si hay evento activo
        if self._event_ms_left > 0.0:
            return 1.0
            
        # Si no hay gap activo
        if not self._in_gap or self._gap_samples == 0:
            return 0.0
            
        # Calcular gap actual (estimado, puede no ser exacto en límites de bloque)
        current_gap_ms = self._last_gap_ms  # Usar último gap conocido como aproximación
        
        if current_gap_ms <= 0:
            return 0.0
        elif current_gap_ms <= gmin:
            return current_gap_ms / gmin
        elif current_gap_ms <= gmax:
            return 1.0
        else:
            # Decay después de gmax
            excess = (current_gap_ms - gmax) / gmax
            return max(0.2, np.exp(-excess))

    def process(self, block, sr):
        """Procesamiento principal con manejo robusto de errores"""
        if not hasattr(self, '_initialized') or not self._initialized:
            return
            
        try:
            # Validaciones básicas
            if block is None or sr is None or sr <= 0:
                return
                
            x = mono(block)
            if x is None or len(x) == 0:
                return
                
            x = x.astype(np.float32, copy=False)
            N = x.size
            dt = N / float(sr)
            
            # Obtener parámetros validados
            gmin, gmax, thdb, env_ms, hold_ms, smooth = self._validate_params()
            
            # Calcular envolvente
            env = self._rms_env_simple(x, sr, env_ms)
            if len(env) == 0:
                return
                
            # Umbral con hysteresis simple
            th_base = 10.0 ** (thdb / 20.0)
            th_enter = th_base
            th_exit = th_base * 1.5  # hysteresis fija
            
            # Procesar cada muestra de la envolvente
            events = []
            for level in env:
                # Lógica de hysteresis
                if self._below_threshold:
                    if level >= th_exit:
                        self._below_threshold = False
                else:
                    if level < th_enter:
                        self._below_threshold = True
                
                # Actualizar estado del gap
                gap_events = self._update_gap_state(self._below_threshold, sr)
                events.extend(gap_events)
            
            # Procesar eventos
            for event_ms in events:
                self._event_ms_left = hold_ms
            
            # Calcular VU
            v_raw = self._calculate_vu_simple(gmin, gmax)
            
            # Decrementar hold
            self._event_ms_left = max(0.0, self._event_ms_left - dt * 1000.0)
            
            # Suavizado
            if smooth > 0.0:
                tau_ms = 80.0 + (600.0 - 80.0) * (smooth ** 2)
                alpha = min(0.99, np.exp(-dt / (tau_ms / 1000.0)))
                self._vu = (1.0 - alpha) * v_raw + alpha * self._vu
            else:
                self._vu = v_raw
                
            v = float(np.clip(self._vu, 0.0, 1.0))
            
            # Actualizar UI de forma segura
            self._update_ui_safe(v, x)
            
        except Exception as e:
            print(f"Error en process: {e}")
            # En caso de error, mantener estado básico
            try:
                if hasattr(self, 'card') and self.card:
                    self.card.set_value(0.0)
                    self.card.set_led("brk", False)
            except:
                pass

    def _update_ui_safe(self, v, x):
        """Actualiza UI de forma segura"""
        try:
            if not hasattr(self, 'card') or not self.card:
                return
                
            # Actualizar valor principal
            self.card.set_value(v)
            self.card.set_led("brk", v > 0.5)
            
            # Match y umbrales
            try:
                lo_t, hi_t = self.card.get_thresholds()
                lo_t = _norm01(lo_t)
                hi_t = _norm01(hi_t)
                if hi_t < lo_t: 
                    lo_t, hi_t = hi_t, lo_t
                mreq = _norm_match(self.card.get_match())
                
                self.card.set_on((lo_t <= v <= hi_t) and ((v * 100.0) >= mreq - 1e-6))
            except:
                # Si falla match, solo mantener valor básico
                pass
            
            # Debug periódico
            self._debug_counter += 1
            if (self._debug_counter % 90) == 0:
                try:
                    self._current_dbfs = 20.0 * np.log10(np.sqrt((x*x).mean()) + EPS)
                    current_gap_ms = 1000.0 * self._gap_samples / 48000.0  # estimado
                    
                    status = f"Lvl: {self._current_dbfs:.1f}dB | Gap: {current_gap_ms:.0f}ms | VU: {v:.2f}"
                    self.card.set_status(status)
                except:
                    self.card.set_status(f"VU: {v:.2f}")
                    
        except Exception as e:
            print(f"Error actualizando UI: {e}")

    def reset(self):
        """Reset seguro del módulo"""
        try:
            self._in_gap = False
            self._gap_samples = 0
            self._vu = 0.0
            self._event_ms_left = 0.0
            self._event_count = 0
            self._below_threshold = True
            
            if hasattr(self, 'card') and self.card:
                self.card.set_value(0.0)
                self.card.set_led("brk", False)
                self.card.set_on(False)
        except Exception as e:
            print(f"Error en reset: {e}")