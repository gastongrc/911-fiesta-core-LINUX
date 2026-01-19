# analyzers/loop_dissolver.py — LOOP DISSOLVER (IMPROVED VERSION)
# v2025-09-05-improved — Optimizado con mejor gestión de memoria, robustez y configurabilidad
# Regla universal: VU en 0..1; ON si (VU*100) >= MATCH y opcionalmente lo<=VU<=hi

from __future__ import annotations
import numpy as np
import logging
from module_card import ModuleCard
from typing import Optional, Tuple

# Configurar logging
logger = logging.getLogger(__name__)

# Constantes configurables del algoritmo
class LoopDissolverConfig:
    """Configuración centralizada de parámetros del algoritmo"""
    
    # Procesamiento de novelty
    NOVELTY_SCALE_FACTOR = 4.0  # Escala para compresión de spectral flux
    SPECTRAL_FLUX_EPSILON = 1e-12  # Prevención de división por cero
    
    # Detección de onsets
    ONSET_THRESHOLD_BASE = 0.15  # Factor base para umbral adaptativo (mediana + factor*max)
    ONSET_REFRACTORY_MS = 80.0  # Período refractario en ms para evitar doble detección
    ONSET_RATE_SCALE = 4.0  # 4 onsets/segundo ≈ 1.0 en escala normalizada
    
    # Análisis de periodicidad
    MIN_BPM = 60.0  # BPM mínimo para búsqueda de periodicidad
    MAX_BPM = 180.0  # BPM máximo para búsqueda de periodicidad
    AUTOCORR_MIN_SAMPLES = 8  # Mínimas muestras para autocorrelación confiable
    
    # Suavizado temporal
    SMOOTH_TAU_MIN_MS = 60.0  # Constante de tiempo mínima para suavizado
    SMOOTH_TAU_MAX_MS = 700.0  # Constante de tiempo máxima para suavizado
    
    # FFT y análisis espectral
    MAX_FFT_SIZE = 4096  # Tamaño máximo de FFT para eficiencia
    MIN_WINDOW_SAMPLES = 3  # Mínimo de muestras para análisis confiable
    
    # Limpieza de señal
    NOVELTY_SUPPRESSION_FACTOR = 0.3  # Factor para suprimir valores bajo umbral


EPS = 1e-12


class AudioProcessingError(Exception):
    """Excepción personalizada para errores de procesamiento de audio"""
    pass


class ParameterValidationError(Exception):
    """Excepción para errores de validación de parámetros"""
    pass


def _norm01(v: float) -> float:
    """
    Normaliza valor a rango 0..1, manejando entrada en 0..100
    
    Args:
        v: Valor a normalizar
        
    Returns:
        Valor normalizado en rango [0, 1]
        
    Raises:
        ValueError: Si el valor no puede ser convertido a float
    """
    try:
        v = float(v)
    except (ValueError, TypeError) as e:
        raise ValueError(f"No se puede convertir {v} a float: {e}")
    
    if v > 1.5:  # Detectar si viene en escala 0..100
        v *= 0.01
    return float(np.clip(v, 0.0, 1.0))


def _norm_match(m: float) -> float:
    """
    Normaliza valor de match a rango 0..100
    
    Args:
        m: Valor de match a normalizar
        
    Returns:
        Valor normalizado en rango [0, 100]
    """
    try:
        m = float(m)
    except (ValueError, TypeError):
        logger.warning(f"Valor de match inválido {m}, usando 50.0 por defecto")
        m = 50.0
    
    if 0.0 <= m <= 1.0:
        m *= 100.0
    return float(np.clip(m, 0.0, 100.0))


def _mono(x: np.ndarray) -> np.ndarray:
    """
    Convierte audio estéreo a mono de forma robusta
    
    Args:
        x: Array de audio (mono o estéreo)
        
    Returns:
        Array de audio mono
        
    Raises:
        AudioProcessingError: Si el array no tiene las dimensiones correctas
    """
    try:
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 2:
            if x.shape[1] > 2:
                raise AudioProcessingError(f"Audio con {x.shape[1]} canales no soportado")
            x = x.mean(axis=1)
        elif x.ndim > 2:
            raise AudioProcessingError(f"Audio con {x.ndim} dimensiones no soportado")
        return x
    except Exception as e:
        raise AudioProcessingError(f"Error convirtiendo a mono: {e}")


def _validate_audio_input(x: np.ndarray) -> np.ndarray:
    """
    Valida y limpia entrada de audio
    
    Args:
        x: Array de audio a validar
        
    Returns:
        Array de audio validado y limpio
    """
    if x.size == 0:
        raise AudioProcessingError("Array de audio vacío")
    
    # Verificar y limpiar valores inválidos
    invalid_count = np.sum(np.isnan(x)) + np.sum(np.isinf(x))
    if invalid_count > 0:
        logger.warning(f"Encontrados {invalid_count} valores inválidos en audio, limpiando...")
        x = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=-1.0)
    
    # Verificar rango de valores
    if np.max(np.abs(x)) > 100.0:  # Probablemente valores no normalizados
        logger.warning("Valores de audio muy altos, normalizando...")
        max_val = np.max(np.abs(x))
        x = x / max_val
    
    return x


class LoopDissolver:
    """
    Analizador de disolución de loops basado en detección de actividad musical.
    
    Combina análisis de spectral flux, detección de onsets y periodicidad
    para determinar cuándo un loop musical se está "disolviendo" o perdiendo
    su estructura rítmica característica.
    """
    
    name = "LOOP DISSOLVER"

    def __init__(self):
        """Inicializa el analizador con configuración por defecto"""
        try:
            self.card = ModuleCard(self.name)
            self._setup_controls()
            self._init_internal_state()
            self._allocate_buffers()
            logger.info(f"Loop Dissolver inicializado correctamente")
        except Exception as e:
            logger.error(f"Error inicializando Loop Dissolver: {e}")
            raise

    def _setup_controls(self) -> None:
        """Configura los controles de la interfaz"""
        try:
            self.card.add_slider("thr_sigma", "Umbral onsets (×σ)", 0.8, 4.0, 1.6)
            self.card.add_slider("win_s",     "Ventana (s)",        1.0, 5.0, 2.5)
            self.card.add_slider("smooth",    "Suavizado",          0.0, 0.95, 0.35)
            self.card.add_slider("sil_db",    "Gate silencio (dB)", 40.0, 70.0, 55.0)
        except Exception as e:
            logger.error(f"Error configurando controles: {e}")
            raise

    def _init_internal_state(self) -> None:
        """Inicializa el estado interno del analizador"""
        # Estado FFT
        self._nfft = 0
        self._current_sr = 0.0
        
        # Estado de análisis
        self._prev_mag = None  # Para spectral flux
        self._vu = 0.0  # Valor suavizado actual
        self._nov_hist = np.zeros(1, dtype=np.float32)  # Historia de novelty
        self._dt_last = 0.05  # Último delta tiempo

    def _allocate_buffers(self) -> None:
        """Pre-aloca buffers reutilizables para evitar allocaciones costosas"""
        self._window = None
        self._freqs = None
        self._fft_buffer = None
        self._autocorr_buffer = None

    def _validate_parameters(self) -> None:
        """
        Valida que los parámetros estén en rangos correctos
        
        Raises:
            ParameterValidationError: Si algún parámetro está fuera de rango
        """
        try:
            thr_sigma = self.card.get_value("thr_sigma")
            if not (0.8 <= thr_sigma <= 4.0):
                raise ParameterValidationError(f"thr_sigma {thr_sigma} fuera de rango [0.8, 4.0]")
            
            win_s = self.card.get_value("win_s")
            if not (1.0 <= win_s <= 5.0):
                raise ParameterValidationError(f"win_s {win_s} fuera de rango [1.0, 5.0]")
            
            smooth = self.card.get_value("smooth")
            if not (0.0 <= smooth <= 0.95):
                raise ParameterValidationError(f"smooth {smooth} fuera de rango [0.0, 0.95]")
            
            sil_db = self.card.get_value("sil_db")
            if not (40.0 <= sil_db <= 70.0):
                raise ParameterValidationError(f"sil_db {sil_db} fuera de rango [40.0, 70.0]")
                
        except Exception as e:
            raise ParameterValidationError(f"Error validando parámetros: {e}")

    # ---------- Gestión FFT optimizada ----------
    
    def _update_fft_setup(self, n: int, sr: float) -> None:
        """
        Actualiza configuración FFT solo cuando es necesario.
        
        Args:
            n: Número de muestras del bloque
            sr: Sample rate
            
        Raises:
            AudioProcessingError: Si los parámetros son inválidos
        """
        if n <= 0:
            raise AudioProcessingError(f"Número de muestras inválido: {n}")
        if sr <= 0:
            raise AudioProcessingError(f"Sample rate inválido: {sr}")
        
        # Calcular tamaño FFT óptimo (potencia de 2)
        nfft = 1
        while nfft < n:
            nfft <<= 1
        nfft = min(nfft, LoopDissolverConfig.MAX_FFT_SIZE)
        
        # Solo actualizar si cambió
        if nfft != self._nfft or sr != self._current_sr:
            try:
                self._nfft = nfft
                self._current_sr = sr
                self._window = np.hanning(nfft).astype(np.float32)
                self._freqs = np.fft.rfftfreq(nfft, 1.0 / float(sr)).astype(np.float32)
                # Pre-alocar buffer FFT
                self._fft_buffer = np.zeros(nfft, dtype=np.float32)
                logger.debug(f"FFT actualizada: nfft={nfft}, sr={sr}")
            except Exception as e:
                raise AudioProcessingError(f"Error configurando FFT: {e}")

    def _compute_magnitude_spectrum(self, x: np.ndarray, sr: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calcula espectro de magnitud con gestión optimizada de memoria.
        
        Args:
            x: Señal de audio (mono)
            sr: Sample rate
            
        Returns:
            Tupla de (magnitudes, frecuencias)
            
        Raises:
            AudioProcessingError: Si hay error en el cálculo
        """
        try:
            n = len(x)
            self._update_fft_setup(n, sr)
            
            # Reutilizar buffer pre-alocado
            self._fft_buffer.fill(0.0)
            
            if n < self._nfft:
                self._fft_buffer[:n] = x
                self._fft_buffer *= self._window
            else:
                # Usar últimas muestras si el bloque es más largo que la ventana
                self._fft_buffer[:] = x[-self._nfft:] * self._window
            
            # FFT y magnitud
            spectrum = np.fft.rfft(self._fft_buffer)
            magnitudes = np.abs(spectrum).astype(np.float32) + LoopDissolverConfig.SPECTRAL_FLUX_EPSILON
            
            return magnitudes, self._freqs
            
        except Exception as e:
            raise AudioProcessingError(f"Error calculando espectro: {e}")

    # ---------- Análisis de novelty mejorado ----------
    
    def _compute_spectral_flux(self, magnitudes: np.ndarray) -> float:
        """
        Calcula spectral flux (medida de novelty) entre frames consecutivos.
        
        Args:
            magnitudes: Espectro de magnitud actual
            
        Returns:
            Valor de novelty normalizado [0, 1]
        """
        try:
            if self._prev_mag is None or len(self._prev_mag) != len(magnitudes):
                self._prev_mag = magnitudes.copy()
                return 0.0
            
            # Diferencia espectral (solo incrementos positivos)
            spectral_diff = magnitudes - self._prev_mag
            self._prev_mag = magnitudes.copy()
            
            positive_flux = np.maximum(spectral_diff, 0.0)
            
            # Normalizar por energía total para robustez
            total_energy = float(np.sum(magnitudes))
            if total_energy < LoopDissolverConfig.SPECTRAL_FLUX_EPSILON:
                return 0.0
                
            raw_flux = float(np.sum(positive_flux)) / total_energy
            
            # Compresión suave a rango [0, 1]
            compressed_flux = np.tanh(raw_flux * LoopDissolverConfig.NOVELTY_SCALE_FACTOR)
            
            return float(np.clip(compressed_flux, 0.0, 1.0))
            
        except Exception as e:
            logger.warning(f"Error calculando spectral flux: {e}")
            return 0.0

    # ---------- Detección de onsets robusta ----------
    
    def _detect_onset_rate(self, novelty_series: np.ndarray, series_sample_rate: float) -> float:
        """
        Detecta tasa de onsets usando detección de picos con período refractario.
        
        Args:
            novelty_series: Serie temporal de valores de novelty
            series_sample_rate: Sample rate de la serie (frames por segundo)
            
        Returns:
            Tasa de onsets normalizada [0, 1] donde 4 onsets/s ≈ 1.0
        """
        try:
            if (novelty_series.size < LoopDissolverConfig.MIN_WINDOW_SAMPLES or 
                series_sample_rate <= 0):
                return 0.0
            
            x = np.asarray(novelty_series, dtype=np.float32)
            
            # Umbral adaptativo robusto
            median_val = float(np.median(x))
            max_val = float(np.max(x))
            threshold = median_val + LoopDissolverConfig.ONSET_THRESHOLD_BASE * max_val
            
            # Detección de picos locales
            if x.size < 3:
                return 0.0
                
            # Comparación con vecinos para encontrar máximos locales
            is_peak = ((x[1:-1] > x[:-2]) & 
                       (x[1:-1] >= x[2:]) & 
                       (x[1:-1] > threshold))
            
            peak_indices = np.where(is_peak)[0] + 1  # Ajustar índices
            
            if peak_indices.size == 0:
                return 0.0
            
            # Aplicar período refractario para evitar detecciones múltiples
            refractory_samples = max(1, int(round(
                LoopDissolverConfig.ONSET_REFRACTORY_MS / 1000.0 * series_sample_rate
            )))
            
            # Filtrar picos muy cercanos
            filtered_peaks = [peak_indices[0]]  # Siempre incluir el primero
            last_peak = peak_indices[0]
            
            for peak_idx in peak_indices[1:]:
                if peak_idx - last_peak >= refractory_samples:
                    filtered_peaks.append(peak_idx)
                    last_peak = peak_idx
            
            # Calcular tasa
            duration_seconds = float(x.size) / float(series_sample_rate)
            if duration_seconds <= 0:
                return 0.0
                
            onsets_per_second = len(filtered_peaks) / duration_seconds
            
            # Normalizar: 4 onsets/s ≈ 1.0
            normalized_rate = onsets_per_second / LoopDissolverConfig.ONSET_RATE_SCALE
            
            return float(np.clip(normalized_rate, 0.0, 1.0))
            
        except Exception as e:
            logger.warning(f"Error detectando onsets: {e}")
            return 0.0

    # ---------- Análisis de periodicidad mejorado ----------
    
    def _analyze_periodicity(self, novelty_series: np.ndarray, series_sample_rate: float) -> Tuple[float, float]:
        """
        Analiza periodicidad usando autocorrelación optimizada.
        
        Args:
            novelty_series: Serie temporal de novelty
            series_sample_rate: Sample rate de la serie
            
        Returns:
            Tupla de (periodicidad_normalizada, bpm_estimado)
        """
        try:
            if (novelty_series.size < LoopDissolverConfig.AUTOCORR_MIN_SAMPLES or 
                series_sample_rate <= 0):
                return 0.0, 0.0
            
            x = np.asarray(novelty_series, dtype=np.float32)
            
            # Preprocesamiento: remover DC y verificar variabilidad
            x_centered = x - float(np.mean(x))
            if np.allclose(x_centered, 0.0, atol=1e-6):
                return 0.0, 0.0
            
            # Autocorrelación eficiente vía FFT
            n_fft = int(1 << (x.size - 1).bit_length())  # Siguiente potencia de 2
            
            # Reutilizar buffer si es posible
            if (self._autocorr_buffer is None or 
                self._autocorr_buffer.size != n_fft):
                self._autocorr_buffer = np.zeros(n_fft, dtype=np.complex64)
            
            # Calcular autocorrelación
            X_fft = np.fft.rfft(x_centered, n=n_fft)
            autocorr_full = np.fft.irfft(X_fft * np.conj(X_fft), n=n_fft).real
            autocorr = autocorr_full[:x.size]
            
            # Ignorar lag 0 (siempre es el máximo)
            autocorr[0] = 0.0
            
            # Limitar búsqueda a rango BPM esperado
            freq_min = LoopDissolverConfig.MIN_BPM / 60.0
            freq_max = LoopDissolverConfig.MAX_BPM / 60.0
            
            lag_min = max(1, int(np.floor(series_sample_rate / freq_max)))
            lag_max = min(autocorr.size - 1, int(np.ceil(series_sample_rate / freq_min)))
            
            if lag_min >= lag_max:
                return 0.0, 0.0
            
            # Buscar máximo en rango válido
            search_segment = autocorr[lag_min:lag_max + 1]
            best_lag_idx = int(np.argmax(search_segment))
            best_lag = best_lag_idx + lag_min
            peak_value = float(search_segment[best_lag_idx])
            
            # Normalizar contra energía de la autocorrelación
            normalization = float(np.max(np.abs(autocorr[1:]))) + EPS
            periodicity = float(np.clip(peak_value / normalization, 0.0, 1.0))
            
            # Estimar BPM
            estimated_bpm = float(series_sample_rate / max(best_lag, 1)) * 60.0
            
            return periodicity, estimated_bpm
            
        except Exception as e:
            logger.warning(f"Error analizando periodicidad: {e}")
            return 0.0, 0.0

    # ---------- Suavizado temporal optimizado ----------
    
    def _apply_temporal_smoothing(self, raw_value: float, delta_time: float) -> float:
        """
        Aplica suavizado temporal con constante de tiempo configurable.
        
        Args:
            raw_value: Valor sin suavizar
            delta_time: Tiempo transcurrido desde la última actualización
            
        Returns:
            Valor suavizado
        """
        try:
            smooth_factor = float(np.clip(self.card.get_value("smooth"), 0.0, 0.95))
            
            # Mapear factor de suavizado a constante de tiempo
            tau_range = LoopDissolverConfig.SMOOTH_TAU_MAX_MS - LoopDissolverConfig.SMOOTH_TAU_MIN_MS
            tau_ms = LoopDissolverConfig.SMOOTH_TAU_MIN_MS + tau_range * (smooth_factor ** 2)
            
            # Coeficiente de filtro exponencial
            alpha = np.exp(-delta_time / (tau_ms / 1000.0))
            
            # Actualizar valor suavizado
            self._vu = (1.0 - alpha) * float(raw_value) + alpha * self._vu
            
            return float(np.clip(self._vu, 0.0, 1.0))
            
        except Exception as e:
            logger.warning(f"Error aplicando suavizado: {e}")
            return float(raw_value)

    # ---------- Lógica principal de procesamiento ----------
    
    def _update_novelty_history(self, novelty_value: float, window_seconds: float, delta_time: float) -> None:
        """
        Actualiza la historia de valores de novelty con ventana deslizante.
        
        Args:
            novelty_value: Nuevo valor de novelty
            window_seconds: Tamaño de ventana en segundos
            delta_time: Tiempo del bloque actual
        """
        try:
            # Calcular tamaño requerido de historia
            required_length = int(max(LoopDissolverConfig.AUTOCORR_MIN_SAMPLES, 
                                     round(window_seconds / max(delta_time, 1e-3))))
            
            # Redimensionar historia si es necesario
            if self._nov_hist.size != required_length:
                old_hist = self._nov_hist.copy()
                self._nov_hist = np.zeros(required_length, dtype=np.float32)
                
                # Preservar valores anteriores si es posible
                copy_length = min(old_hist.size, required_length - 1)
                if copy_length > 0:
                    self._nov_hist[-copy_length-1:-1] = old_hist[-copy_length:]
            
            # Desplazar e insertar nuevo valor
            self._nov_hist = np.roll(self._nov_hist, -1)
            self._nov_hist[-1] = novelty_value
            
        except Exception as e:
            logger.warning(f"Error actualizando historia de novelty: {e}")

    def _check_silence_gate(self, audio_block: np.ndarray) -> Tuple[bool, float]:
        """
        Verifica si el audio está por debajo del umbral de silencio.
        
        Args:
            audio_block: Bloque de audio a analizar
            
        Returns:
            Tupla de (es_silencio, nivel_db)
        """
        try:
            rms = float(np.sqrt(np.mean(audio_block * audio_block)) + EPS)
            level_db = 20.0 * np.log10(rms + EPS)
            
            silence_threshold = float(np.clip(self.card.get_value("sil_db"), 30.0, 80.0))
            is_silent = level_db < -silence_threshold
            
            return is_silent, level_db
            
        except Exception as e:
            logger.warning(f"Error verificando gate de silencio: {e}")
            return False, -60.0

    def _apply_universal_activation_rule(self, vu_value: float) -> None:
        """
        Aplica la regla universal de activación basada en umbrales y match.
        
        Args:
            vu_value: Valor VU actual [0, 1]
        """
        try:
            # Obtener umbrales normalizados
            low_thresh, high_thresh = self.card.get_thresholds()
            low_thresh = _norm01(low_thresh)
            high_thresh = _norm01(high_thresh)
            
            # Asegurar orden correcto
            if high_thresh < low_thresh:
                low_thresh, high_thresh = high_thresh, low_thresh
            
            # Obtener requisito de match
            match_required = _norm_match(self.card.get_match())
            
            # Aplicar regla: dentro del rango Y supera el match requerido
            in_range = low_thresh <= vu_value <= high_thresh
            meets_match = (vu_value * 100.0) >= match_required
            
            self.card.set_on(in_range and meets_match)
            
        except Exception as e:
            logger.warning(f"Error aplicando regla de activación: {e}")

    def _format_status(self, level_db: float, smoothed_vu: float, combined_activity: float, 
                      periodicity: float, onset_rate: float, estimated_bpm: float) -> str:
        """
        Formatea el string de estado para display
        
        Args:
            level_db: Nivel de señal en dB
            smoothed_vu: Valor VU suavizado
            combined_activity: Actividad musical combinada
            periodicity: Valor de periodicidad
            onset_rate: Tasa de onsets
            estimated_bpm: BPM estimado
            
        Returns:
            String formateado para mostrar en interfaz
        """
        try:
            return (f"{level_db:.1f} dBFS | v={smoothed_vu:.2f} | "
                   f"act={combined_activity:.2f} (per={periodicity:.2f}, rate={onset_rate:.2f}) | "
                   f"BPM≈{estimated_bpm:.1f}")
        except Exception as e:
            logger.warning(f"Error formateando status: {e}")
            return "Status error"

    def process(self, block, sr):
        """
        Procesa un bloque de audio y actualiza el estado del analizador.
        
        Args:
            block: Bloque de audio (mono o estéreo)
            sr: Sample rate
        """
        try:
            # Validación de entrada
            if block is None or sr is None or sr <= 0:
                logger.warning(f"Entrada inválida: block={block is not None}, sr={sr}")
                return
            
            # Validar parámetros
            self._validate_parameters()
            
            # Preparar audio (mono + validación)
            audio = _mono(block)
            if audio.size == 0:
                logger.warning("Bloque de audio vacío")
                return
            
            audio = _validate_audio_input(audio)
            delta_time = audio.size / float(sr)
            self._dt_last = delta_time

            # Verificar gate de silencio
            is_silent, level_db = self._check_silence_gate(audio)
            
            if is_silent:
                # En silencio: loop completamente disuelto
                smoothed_vu = self._apply_temporal_smoothing(1.0, delta_time)
                self.card.set_value(smoothed_vu)
                self._apply_universal_activation_rule(smoothed_vu)
                
                status = self._format_status(level_db, smoothed_vu, 0.0, 0.0, 0.0, 0.0)
                self.card.set_status(status)
                return

            # Análisis espectral
            magnitudes, frequencies = self._compute_magnitude_spectrum(audio, sr)
            current_novelty = self._compute_spectral_flux(magnitudes)

            # Actualizar historia de novelty
            window_seconds = float(np.clip(self.card.get_value("win_s"), 1.0, 5.0))
            self._update_novelty_history(current_novelty, window_seconds, delta_time)

            # Análisis de actividad musical
            series_sample_rate = 1.0 / max(delta_time, 1e-3)
            
            # Preparar señal filtrada para análisis de periodicidad
            threshold_multiplier = float(np.clip(self.card.get_value("thr_sigma"), 0.8, 4.0))
            filtered_novelty = self._nov_hist.copy()
            
            # Suprimir valores bajo umbral (limpieza suave)
            mean_nov = float(np.mean(filtered_novelty))
            std_nov = float(np.std(filtered_novelty)) + 1e-6
            threshold = mean_nov + threshold_multiplier * std_nov
            
            suppression_mask = filtered_novelty < threshold
            filtered_novelty[suppression_mask] *= LoopDissolverConfig.NOVELTY_SUPPRESSION_FACTOR
            
            # Calcular métricas de actividad
            periodicity, estimated_bpm = self._analyze_periodicity(filtered_novelty, series_sample_rate)
            onset_rate = self._detect_onset_rate(self._nov_hist, series_sample_rate)
            
            # Actividad combinada (máximo de ambas métricas)
            combined_activity = max(periodicity, onset_rate)
            
            # VU = inverso de actividad (mucha actividad = loop no disuelto)
            raw_vu = float(np.clip(1.0 - combined_activity, 0.0, 1.0))
            smoothed_vu = self._apply_temporal_smoothing(raw_vu, delta_time)
            
            # Actualizar estado
            self.card.set_value(smoothed_vu)
            self._apply_universal_activation_rule(smoothed_vu)

            # Actualizar display de estado
            status = self._format_status(level_db, smoothed_vu, combined_activity, 
                                       periodicity, onset_rate, estimated_bpm)
            self.card.set_status(status)

        except ParameterValidationError as e:
            logger.error(f"Error de validación de parámetros: {e}")
            self.card.set_status("Error: Parámetros inválidos")
        except AudioProcessingError as e:
            logger.error(f"Error de procesamiento de audio: {e}")
            self.card.set_status("Error: Procesamiento de audio")
        except Exception as e:
            logger.error(f"Error inesperado en process(): {e}")
            self.card.set_status("Error: Procesamiento falló")

    def reset(self) -> None:
        """
        Reinicia el estado interno del analizador
        """
        try:
            logger.info("Reiniciando Loop Dissolver...")
            self._prev_mag = None
            self._vu = 0.0
            self._nov_hist = np.zeros(1, dtype=np.float32)
            self._nfft = 0
            self._current_sr = 0.0
            # Los buffers se reasignarán automáticamente cuando sea necesario
            logger.info("Loop Dissolver reiniciado correctamente")
        except Exception as e:
            logger.error(f"Error reiniciando: {e}")

    def get_current_vu(self) -> float:
        """
        Obtiene el valor VU actual
        
        Returns:
            Valor VU actual [0, 1]
        """
        return self._vu

    def get_analysis_info(self) -> dict:
        """
        Obtiene información detallada del análisis actual
        
        Returns:
            Diccionario con información de análisis
        """
        try:
            return {
                'vu_value': self._vu,
                'novelty_history_size': self._nov_hist.size,
                'fft_size': self._nfft,
                'sample_rate': self._current_sr,
                'last_delta_time': self._dt_last,
                'has_magnitude_history': self._prev_mag is not None
            }
        except Exception as e:
            logger.warning(f"Error obteniendo información de análisis: {e}")
            return {}

    # Alias para compatibilidad
    tick = process