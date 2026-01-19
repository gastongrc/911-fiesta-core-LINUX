# analyzers/mid_range_finder.py
# BAJADA – Actividad melódica en medios (~250 Hz–3 kHz)
# v2025-09-05: Versión corregida con mejoras en estructura, eficiencia y documentación

import numpy as np
import logging
from typing import Optional, Tuple, Union

# Configuración de logging
logger = logging.getLogger(__name__)

# Constantes
EPS = 1e-12
MIN_SAMPLE_RATE = 8000
MAX_SAMPLE_RATE = 192000
DEFAULT_REFERENCE_LOW = 80.0
DEFAULT_REFERENCE_HIGH = 8000.0

def _mono(x: np.ndarray) -> np.ndarray:
    """Convierte audio a mono de forma eficiente."""
    if x is None:
        return np.array([], dtype=np.float32)
    
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        return x
    elif x.ndim == 2:
        return np.mean(x, axis=1, dtype=np.float32)
    else:
        raise ValueError(f"Audio debe ser 1D o 2D, recibido: {x.ndim}D")

def _normalize_0_1(value: Union[float, int, None]) -> float:
    """Normaliza valor a rango [0, 1], admite porcentajes 0-100."""
    if value is None:
        return 0.0
    
    try:
        v = float(value)
        # Detecta si es porcentaje (>1.5 asume 0-100)
        if v > 1.5:
            v *= 0.01
        return float(np.clip(v, 0.0, 1.0))
    except (TypeError, ValueError):
        logger.warning(f"Valor inválido para normalización: {value}, usando 0.0")
        return 0.0

def _normalize_match(match: Union[float, int, None]) -> float:
    """Normaliza valor de match a rango [0, 100]."""
    try:
        m = float(50.0 if match is None else match)
    except (TypeError, ValueError):
        logger.warning(f"Valor de match inválido: {match}, usando 50.0")
        m = 50.0
    
    # Convierte 0-1 a 0-100 si es necesario
    if 0.0 <= m <= 1.0:
        m *= 100.0
    
    return float(np.clip(m, 0.0, 100.0))

class MidRangeFinder:
    """
    Analizador de actividad en frecuencias medias con lógica invertida.
    Detecta momentos con menos actividad en medios (útil para "bajadas").
    """
    
    name = "MID RANGE FINDER"
    
    # Rangos válidos para parámetros
    FREQ_LIMITS = {
        'flo': (100.0, 1000.0),
        'fhi': (1000.0, 8000.0)
    }
    SENS_LIMITS = (-12.0, +12.0)
    SLOPE_LIMITS = (2.0, 24.0)
    SILENCE_LIMITS = (30.0, 80.0)
    SMOOTH_LIMITS = (0.0, 0.98)
    
    def __init__(self):
        """Inicializa el analizador con configuración por defecto."""
        try:
            from module_card import ModuleCard
            self.card = ModuleCard(self.name)
            self._setup_controls()
        except ImportError as e:
            logger.error(f"No se pudo importar ModuleCard: {e}")
            self.card = None
        
        # Estado interno
        self._vu_internal = 0.0  # VU antes de inversión [0, 1]
        self._is_initialized = True
        
        # Caché FFT para optimización
        self._fft_cache = {
            'sr': None,
            'n': None,
            'window': None,
            'freqs': None
        }
        
        logger.info(f"{self.name} inicializado correctamente")
    
    def _setup_controls(self) -> None:
        """Configura los controles de la interfaz de usuario."""
        if not self.card:
            return
            
        try:
            # Parámetros de banda
            self.card.add_slider("flo", "F baja (Hz)", 
                               self.FREQ_LIMITS['flo'][0], 
                               self.FREQ_LIMITS['flo'][1], 250.0)
            
            self.card.add_slider("fhi", "F alta (Hz)", 
                               self.FREQ_LIMITS['fhi'][0], 
                               self.FREQ_LIMITS['fhi'][1], 3000.0)
            
            # Configuración de sensibilidad
            self.card.add_slider("sensdb", "Centro (dB)", 
                               self.SENS_LIMITS[0], 
                               self.SENS_LIMITS[1], 0.0)
            
            self.card.add_slider("slope", "Pendiente (dB)", 
                               self.SLOPE_LIMITS[0], 
                               self.SLOPE_LIMITS[1], 12.0)
            
            # Control de ruido y suavizado
            self.card.add_slider("sil_db", "Gate silencio (dB)", 
                               self.SILENCE_LIMITS[0], 
                               self.SILENCE_LIMITS[1], 55.0)
            
            self.card.add_slider("smooth", "Suavizado", 
                               self.SMOOTH_LIMITS[0], 
                               self.SMOOTH_LIMITS[1], 0.25)
            
            # Indicador LED
            self.card.add_led("mid", "Medios activos (invertido)")
            
        except Exception as e:
            logger.error(f"Error configurando controles: {e}")
    
    def _ensure_fft_cache(self, n: int, sr: int) -> None:
        """Mantiene caché de FFT para optimizar cálculos repetitivos."""
        cache = self._fft_cache
        
        if (cache['n'] == n and cache['sr'] == sr and 
            cache['window'] is not None and cache['freqs'] is not None):
            return
        
        try:
            cache['n'] = n
            cache['sr'] = sr
            cache['window'] = np.hanning(n).astype(np.float32)
            cache['freqs'] = np.fft.rfftfreq(n, 1.0/float(sr)).astype(np.float32)
            
        except Exception as e:
            logger.error(f"Error creando caché FFT: {e}")
            # Caché de emergencia con valores mínimos
            cache['window'] = np.ones(n, dtype=np.float32)
            cache['freqs'] = np.linspace(0, sr//2, n//2 + 1, dtype=np.float32)
    
    def _calculate_band_energy(self, x: np.ndarray, sr: int, 
                              f_lo: float, f_hi: float,
                              f_ref_lo: float = DEFAULT_REFERENCE_LOW,
                              f_ref_hi: float = DEFAULT_REFERENCE_HIGH) -> Tuple[float, float]:
        """
        Calcula energía en banda específica vs energía de referencia.
        
        Returns:
            Tuple[float, float]: (energía_banda, energía_resto)
        """
        n = len(x)
        
        try:
            self._ensure_fft_cache(n, sr)
            
            # FFT con ventana para reducir leakage espectral
            windowed = x * self._fft_cache['window']
            X = np.fft.rfft(windowed.astype(np.float32))
            power_spectrum = np.abs(X) ** 2 + EPS
            
            # Máscaras para seleccionar frecuencias
            freqs = self._fft_cache['freqs']
            mask_band = (freqs >= f_lo) & (freqs <= f_hi)
            mask_ref = (freqs >= f_ref_lo) & (freqs <= f_ref_hi)
            
            # Energías
            e_band = float(np.sum(power_spectrum[mask_band]))
            e_ref_total = float(np.sum(power_spectrum[mask_ref]))
            
            # Energía del resto (referencia - banda)
            e_rest = max(e_ref_total - e_band, EPS)
            
            return e_band, e_rest
            
        except Exception as e:
            logger.error(f"Error en cálculo de energía: {e}")
            return EPS, EPS
    
    def _get_safe_parameter(self, param: str, default: float, 
                           limits: Optional[Tuple[float, float]] = None) -> float:
        """Obtiene parámetro de forma segura con validación."""
        if not self.card:
            return default
            
        try:
            value = float(self.card.get_value(param))
            if limits:
                value = np.clip(value, limits[0], limits[1])
            return value
        except Exception as e:
            logger.warning(f"Error obteniendo parámetro {param}: {e}, usando default: {default}")
            return default
    
    def _calculate_silence_gate(self, x: np.ndarray, sr: int) -> Tuple[bool, float]:
        """
        Determina si la señal está en silencio basado en dBFS.
        
        Returns:
            Tuple[bool, float]: (es_silencio, dbfs)
        """
        try:
            rms = np.sqrt(np.mean(x * x) + EPS)
            dbfs = 20.0 * np.log10(rms + EPS)
            
            silence_threshold = self._get_safe_parameter("sil_db", 55.0, self.SILENCE_LIMITS)
            is_silence = dbfs < -silence_threshold
            
            return is_silence, float(dbfs)
            
        except Exception as e:
            logger.error(f"Error en gate de silencio: {e}")
            return False, -60.0
    
    def _update_vu_with_smoothing(self, target_value: float, dt: float) -> None:
        """Actualiza VU interno con suavizado temporal."""
        try:
            smooth_param = self._get_safe_parameter("smooth", 0.25, self.SMOOTH_LIMITS)
            
            # Mapeo no-lineal: más suavizado hacia valores altos
            tau_ms = 80.0 + (600.0 - 80.0) * (smooth_param ** 2)
            alpha = np.exp(-dt / (tau_ms / 1000.0))
            
            # Filtro exponencial
            self._vu_internal = (1.0 - alpha) * target_value + alpha * self._vu_internal
            self._vu_internal = np.clip(self._vu_internal, 0.0, 1.0)
            
        except Exception as e:
            logger.error(f"Error en suavizado: {e}")
            self._vu_internal = np.clip(target_value, 0.0, 1.0)
    
    def _update_ui_and_status(self, inverted_vu: float, dbfs: float, 
                             f_lo: float, f_hi: float, 
                             dominance_db: float, ratio: float) -> None:
        """Actualiza interfaz de usuario y estado."""
        if not self.card:
            return
            
        try:
            # Actualizar VU invertido
            self.card.set_value(inverted_vu)
            
            # LED: encendido si VU invertido >= 50%
            self.card.set_led("mid", inverted_vu >= 0.5)
            
            # Lógica ON/OFF con thresholds y match
            lo, hi = self.card.get_thresholds()
            lo, hi = _normalize_0_1(lo), _normalize_0_1(hi)
            if hi < lo:
                lo, hi = hi, lo
            
            match_req = _normalize_match(self.card.get_match())
            
            in_range = lo <= inverted_vu <= hi
            meets_match = (inverted_vu * 100.0) >= (match_req - EPS)
            
            self.card.set_on(in_range and meets_match)
            
            # Status informativo
            status = (f"{dbfs:.1f} dBFS | "
                     f"banda={f_lo:.0f}-{f_hi:.0f} Hz | "
                     f"dominancia={dominance_db:+.1f} dB (×{ratio:.2f}) | "
                     f"VU_inv={inverted_vu:.2f}")
            
            self.card.set_status(status)
            
        except Exception as e:
            logger.error(f"Error actualizando UI: {e}")
    
    def process(self, block: Optional[np.ndarray], sr: Optional[int]) -> None:
        """
        Procesa un bloque de audio y actualiza el analizador.
        
        Args:
            block: Bloque de audio (mono o estéreo)
            sr: Sample rate en Hz
        """
        # Validación de entrada
        if block is None or sr is None or sr <= 0:
            logger.warning("Bloque o sample rate inválido")
            return
        
        if not (MIN_SAMPLE_RATE <= sr <= MAX_SAMPLE_RATE):
            logger.warning(f"Sample rate fuera de rango válido: {sr}")
            return
        
        try:
            # Conversión a mono
            x = _mono(block)
            if x.size == 0:
                logger.warning("Bloque de audio vacío")
                return
            
            # Tiempo del bloque
            dt = x.size / float(sr)
            
            # Gate de silencio
            is_silence, dbfs = self._calculate_silence_gate(x, sr)
            
            if is_silence:
                # Decaimiento rápido durante silencio
                fast_decay = np.exp(-dt / 0.12)
                self._vu_internal *= fast_decay
                
                inverted_vu = 1.0 - self._vu_internal
                
                if self.card:
                    self._update_ui_and_status(inverted_vu, dbfs, 0, 0, 0, 0)
                    
                return
            
            # Parámetros de banda
            f_lo = self._get_safe_parameter("flo", 250.0, self.FREQ_LIMITS['flo'])
            f_hi = self._get_safe_parameter("fhi", 3000.0, self.FREQ_LIMITS['fhi'])
            
            # Validar orden de frecuencias
            if f_hi <= f_lo:
                f_hi = f_lo + 100.0
                logger.warning(f"f_hi <= f_lo, ajustando f_hi a {f_hi}")
            
            # Análisis espectral
            e_mid, e_rest = self._calculate_band_energy(x, sr, f_lo, f_hi)
            
            # Dominancia en dB
            ratio = (e_mid + EPS) / (e_rest + EPS)
            dominance_db = 10.0 * np.log10(ratio)
            
            # Mapeo a VU usando rampa lineal en dB
            center_db = self._get_safe_parameter("sensdb", 0.0, self.SENS_LIMITS)
            slope_db = self._get_safe_parameter("slope", 12.0, self.SLOPE_LIMITS)
            
            lo_db = center_db - slope_db / 2.0
            hi_db = center_db + slope_db / 2.0
            
            # VU crudo [0, 1]
            vu_raw = np.clip((dominance_db - lo_db) / max(EPS, hi_db - lo_db), 0.0, 1.0)
            
            # Suavizado temporal
            self._update_vu_with_smoothing(vu_raw, dt)
            
            # Inversión para lógica de "bajada"
            inverted_vu = 1.0 - self._vu_internal
            
            # Actualizar interfaz
            self._update_ui_and_status(inverted_vu, dbfs, f_lo, f_hi, 
                                     dominance_db, ratio)
            
        except Exception as e:
            logger.error(f"Error en procesamiento de audio: {e}")
            # Estado de emergencia
            if self.card:
                self.card.set_value(0.0)
                self.card.set_status(f"Error: {str(e)[:50]}...")
    
    def reset(self) -> None:
        """Reinicia el estado interno del analizador."""
        try:
            self._vu_internal = 0.0
            self._fft_cache = {
                'sr': None,
                'n': None,
                'window': None,
                'freqs': None
            }
            
            if self.card:
                self.card.set_value(1.0)  # VU invertido inicial
                self.card.set_on(False)
                self.card.set_status("Reiniciado")
                
            logger.info("Analizador reiniciado")
            
        except Exception as e:
            logger.error(f"Error en reinicio: {e}")
    
    @property
    def current_vu_inverted(self) -> float:
        """Retorna el valor actual del VU invertido [0, 1]."""
        return 1.0 - self._vu_internal
    
    @property
    def is_active(self) -> bool:
        """Retorna True si el analizador está activo (VU invertido >= 50%)."""
        return self.current_vu_inverted >= 0.5