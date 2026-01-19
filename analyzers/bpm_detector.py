# bpm_detector.py - Detector de BPM preciso y estabilizado para 911 Fiesta
import numpy as np
import librosa
from collections import deque
import time
import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple

@dataclass
class BPMResult:
    """Resultado del análisis de BPM"""
    bpm: float
    confidence: float
    method_used: str
    beat_times: List[float]
    stability: float
    genre_hint: Optional[str] = None

class BPMDetector:
    """
    Detector de BPM preciso con múltiples algoritmos y estabilización anti-oscilación
    Diseñado para música de boliche (Cachengue, Techengue, Techno, House)
    """
    
    def __init__(self, delay_seconds=3.0, buffer_duration=10.0):
        # Configuración principal - MÁS CONSERVADORA para estabilidad
        self.delay_seconds = delay_seconds
        self.buffer_duration = buffer_duration
        self.sample_rate = 44100
        
        # Buffer circular para audio
        buffer_samples = int(buffer_duration * self.sample_rate)
        self.audio_buffer = deque(maxlen=buffer_samples)
        
        # Historia de BPM para estabilidad - MÁS LARGA
        self.bpm_history = deque(maxlen=15)  # Era 10, ahora 15
        self.beat_history = deque(maxlen=50)
        
        # Estado interno
        self.current_bpm = 0.0
        self.confidence = 0.0
        self.is_stable = False
        self.last_analysis_time = 0
        self.analysis_interval = 0.8  # Era 0.5s, ahora 0.8s - menos frecuente
        
        # Suavizado para anti-oscilación
        self._smoothed_bpm = 0.0
        self._bpm_buffer = deque(maxlen=8)  # Buffer para promedio móvil
        
        # Ranges de BPM por género
        self.genre_bpm_ranges = {
            'CACHENGUE': (85, 115),
            'TECHENGUE': (95, 125), 
            'TECHNO': (115, 155),
            'HOUSE': (115, 135),
            'REGGAETON': (85, 105)
        }
        
        # Thread para análisis
        self.analysis_thread = None
        self.running = False
        
    def start(self):
        """Inicia el detector en thread separado"""
        if not self.running:
            self.running = True
            self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
            self.analysis_thread.start()
            
    def stop(self):
        """Detiene el detector"""
        self.running = False
        if self.analysis_thread:
            self.analysis_thread.join()
            
    def process_audio(self, audio_block: np.ndarray):
        """
        Procesa nuevo bloque de audio
        Args:
            audio_block: Array de audio mono, sample_rate 44100
        """
        # Agregar al buffer circular
        self.audio_buffer.extend(audio_block.flatten())
        
    def _analysis_loop(self):
        """Loop principal de análisis en thread separado"""
        while self.running:
            current_time = time.time()
            
            # Analizar solo si hay suficiente audio y pasó el intervalo
            if (len(self.audio_buffer) >= self.sample_rate * 6 and  # Era 4, ahora 6
                current_time - self.last_analysis_time >= self.analysis_interval):
                
                # Aplicar delay configurado
                delayed_audio = self._get_delayed_audio()
                if delayed_audio is not None:
                    result = self._analyze_bpm(delayed_audio)
                    self._update_state(result)
                    self.last_analysis_time = current_time
                    
            time.sleep(0.15)  # Era 0.1, ahora 0.15 - menos carga CPU
            
    def _get_delayed_audio(self) -> Optional[np.ndarray]:
        """Obtiene audio con delay aplicado para mayor precisión"""
        buffer_array = np.array(self.audio_buffer)
        
        # Calcular samples de delay
        delay_samples = int(self.delay_seconds * self.sample_rate)
        
        if len(buffer_array) < delay_samples + self.sample_rate * 6:  # Era 4, ahora 6
            return None
            
        # Extraer audio con delay (más viejo)
        start_idx = len(buffer_array) - delay_samples - int(self.sample_rate * 6)
        end_idx = len(buffer_array) - delay_samples
        
        return buffer_array[start_idx:end_idx]
        
    def _analyze_bpm(self, audio: np.ndarray) -> BPMResult:
        """
        Análisis principal de BPM usando múltiples métodos con consensus
        """
        # Método 1: Librosa beat tracking (muy bueno para música electrónica)
        bpm_librosa, confidence_librosa = self._librosa_bpm(audio)
        
        # Método 2: Autocorrelación (bueno para patrones repetitivos)
        bpm_autocorr, confidence_autocorr = self._autocorrelation_bpm(audio)
        
        # Método 3: Onset detection (preciso para kicks marcados)
        bpm_onset, confidence_onset = self._onset_detection_bpm(audio)
        
        # Combinar resultados con pesos
        results = [
            (bpm_librosa, confidence_librosa, "librosa"),
            (bpm_autocorr, confidence_autocorr, "autocorr"),
            (bpm_onset, confidence_onset, "onset")
        ]
        
        # Filtrar resultados válidos - MÁS ESTRICTO
        valid_results = [(bpm, conf, method) for bpm, conf, method in results 
                        if 80 <= bpm <= 180 and conf > 0.5]  # Era 0.3, ahora 0.5
        
        if not valid_results:
            return BPMResult(0.0, 0.0, "none", [], 0.0)
        
        # NUEVO: Buscar consensus entre métodos
        consensus_bpm, consensus_conf, consensus_method = self._find_consensus(valid_results)
        
        # Detectar beats para timing
        beat_times = self._detect_beat_times(audio, consensus_bpm)
        
        # Calcular estabilidad
        stability = self._calculate_stability(consensus_bpm)
        
        # Hint de género basado en BPM
        genre_hint = self._guess_genre_from_bpm(consensus_bpm)
        
        return BPMResult(
            bpm=consensus_bpm,
            confidence=consensus_conf,
            method_used=consensus_method,
            beat_times=beat_times,
            stability=stability,
            genre_hint=genre_hint
        )
    
    def _find_consensus(self, valid_results: List[Tuple[float, float, str]]) -> Tuple[float, float, str]:
        """Encuentra consensus entre múltiples métodos para mayor estabilidad"""
        if len(valid_results) == 1:
            return valid_results[0]
        
        # Buscar BPMs que estén cerca entre sí
        consensus_groups = []
        
        for i, (bpm1, conf1, method1) in enumerate(valid_results):
            group_bpms = [bpm1]
            group_confs = [conf1]
            group_methods = [method1]
            
            for j, (bpm2, conf2, method2) in enumerate(valid_results):
                if i != j and abs(bpm1 - bpm2) < 4.0:  # Tolerancia de 4 BPM
                    group_bpms.append(bpm2)
                    group_confs.append(conf2)
                    group_methods.append(method2)
            
            if len(group_bpms) >= 2:  # Al menos 2 métodos de acuerdo
                avg_bpm = np.mean(group_bpms)
                avg_conf = np.mean(group_confs) * len(group_bpms)  # Bonus por consensus
                methods_str = "+".join(group_methods)
                consensus_groups.append((avg_bpm, avg_conf, methods_str))
        
        # Usar el grupo con mayor confidence, o el mejor individual
        if consensus_groups:
            return max(consensus_groups, key=lambda x: x[1])
        else:
            return max(valid_results, key=lambda x: x[1])
            
    def _librosa_bpm(self, audio: np.ndarray) -> Tuple[float, float]:
        """BPM usando librosa beat tracking"""
        try:
            # Librosa espera audio normalizado
            audio_norm = librosa.util.normalize(audio)
            
            # Detectar tempo con parámetros más conservadores
            tempo, beats = librosa.beat.beat_track(
                y=audio_norm, 
                sr=self.sample_rate,
                hop_length=512,
                start_bpm=120.0,
                tightness=200  # Era 100, ahora 200 - más estricto
            )
            
            # Confidence basado en consistencia de beats
            if len(beats) > 6:  # Era 4, ahora 6
                beat_intervals = np.diff(beats)
                consistency = 1.0 - (np.std(beat_intervals) / np.mean(beat_intervals))
                confidence = max(0.0, min(1.0, consistency * 1.2))  # Boost confidence
            else:
                confidence = 0.0
                
            return float(tempo), confidence
            
        except Exception as e:
            print(f"[BPMDetector] Error en librosa_bpm: {e}")
            return 0.0, 0.0
            
    def _autocorrelation_bpm(self, audio: np.ndarray) -> Tuple[float, float]:
        """BPM usando autocorrelación"""
        try:
            # Enventanar y aplicar autocorrelación
            windowed = audio * np.hanning(len(audio))
            autocorr = np.correlate(windowed, windowed, mode='full')
            autocorr = autocorr[len(autocorr)//2:]
            
            # Buscar picos en rango de BPM válido
            min_samples = int(60.0 / 180.0 * self.sample_rate)  # 180 BPM max
            max_samples = int(60.0 / 80.0 * self.sample_rate)   # 80 BPM min
            
            search_range = autocorr[min_samples:max_samples]
            if len(search_range) == 0:
                return 0.0, 0.0
                
            peak_idx = np.argmax(search_range) + min_samples
            bpm = 60.0 / (peak_idx / self.sample_rate)
            
            # Confidence basado en altura del pico - MÁS ESTRICTO
            peak_height = search_range[np.argmax(search_range)]
            avg_height = np.mean(search_range)
            confidence = min(1.0, peak_height / (avg_height * 4))  # Era 3, ahora 4
            
            return bpm, confidence
            
        except Exception as e:
            print(f"[BPMDetector] Error en autocorrelation_bpm: {e}")
            return 0.0, 0.0
            
    def _onset_detection_bpm(self, audio: np.ndarray) -> Tuple[float, float]:
        """BPM usando detección de onset (ideal para kicks) - MEJORADO"""
        try:
            # Pre-procesar audio para enfatizar kicks
            # Filtro pasa-bajos para enfatizar frecuencias de kick (50-100 Hz)
            from scipy import signal
            nyquist = self.sample_rate / 2
            low_freq = 50 / nyquist
            high_freq = 150 / nyquist
            b, a = signal.butter(4, [low_freq, high_freq], btype='band')
            filtered_audio = signal.filtfilt(b, a, audio)
            
            # Detectar onsets en audio filtrado Y original
            onsets_filtered = librosa.onset.onset_detect(
                y=filtered_audio,
                sr=self.sample_rate,
                hop_length=256,  # Más precisión
                backtrack=True,
                units='time',
                delta=0.2,       # Más restrictivo para kicks
                wait=20         # Mínimo entre onsets
            )
            
            onsets_original = librosa.onset.onset_detect(
                y=audio,
                sr=self.sample_rate,
                hop_length=256,
                backtrack=True,
                units='time',
                delta=0.1
            )
            
            # Usar el que tenga más onsets pero no demasiados
            if 6 <= len(onsets_filtered) <= 50:
                onsets = onsets_filtered
                source = "filtered"
            elif 6 <= len(onsets_original) <= 50:
                onsets = onsets_original
                source = "original"
            else:
                return 0.0, 0.0
                
            # Calcular intervalos entre onsets
            intervals = np.diff(onsets)
            
            # Filtrar intervalos válidos para música de boliche (75-180 BPM)
            valid_intervals = intervals[(intervals >= 0.33) & (intervals <= 0.8)]
            
            if len(valid_intervals) < 4:
                return 0.0, 0.0
            
            # Histograma de intervalos para encontrar el más común
            hist, bin_edges = np.histogram(valid_intervals, bins=20)
            most_common_bin = np.argmax(hist)
            target_interval = (bin_edges[most_common_bin] + bin_edges[most_common_bin + 1]) / 2
            
            # BPM basado en el intervalo más común
            bpm = 60.0 / target_interval
            
            # Confidence basado en qué tan concentrados están los intervalos
            similar_intervals = valid_intervals[np.abs(valid_intervals - target_interval) < 0.1]
            concentration = len(similar_intervals) / len(valid_intervals)
            
            # Boost confidence si viene del audio filtrado (mejor para kicks)
            confidence_boost = 1.2 if source == "filtered" else 1.0
            confidence = min(1.0, concentration * 0.9 * confidence_boost)
            
            return bpm, confidence
            
        except ImportError:
            # Fallback sin scipy
            return self._onset_detection_bpm_simple(audio)
        except Exception as e:
            print(f"[BPMDetector] Error en onset_detection_bpm: {e}")
            return 0.0, 0.0
            
    def _detect_beat_times(self, audio: np.ndarray, bpm: float) -> List[float]:
        """Detecta timing exacto de beats"""
        try:
            _, beats = librosa.beat.beat_track(
                y=audio,
                sr=self.sample_rate,
                bpm=bpm,
                hop_length=512
            )
            
            # Convertir a segundos
            beat_times = librosa.frames_to_time(beats, sr=self.sample_rate, hop_length=512)
            return beat_times.tolist()
            
        except Exception:
            return []
    
    def _apply_smoothing(self, new_bpm: float) -> float:
        """Aplica suavizado anti-oscilación al BPM"""
        if new_bpm <= 0:
            return self._smoothed_bpm
        
        # Agregar al buffer
        self._bpm_buffer.append(new_bpm)
        
        if len(self._bpm_buffer) < 3:
            self._smoothed_bpm = new_bpm
            return new_bpm
        
        # Filtro de mediana para eliminar outliers
        buffer_list = list(self._bpm_buffer)
        median_bpm = np.median(buffer_list)
        
        # Filtrar valores muy alejados de la mediana (outliers)
        filtered_bpms = [bpm for bpm in buffer_list if abs(bpm - median_bpm) < 6.0]
        
        if len(filtered_bpms) < 2:
            return self._smoothed_bpm
        
        # Promedio ponderado con suavizado exponencial
        alpha = 0.25  # Factor de suavizado conservador (0.1 = muy suave, 0.9 = muy reactivo)
        target_bpm = np.mean(filtered_bpms)
        
        if self._smoothed_bpm == 0:
            self._smoothed_bpm = target_bpm
        else:
            self._smoothed_bpm = alpha * target_bpm + (1 - alpha) * self._smoothed_bpm
        
        return self._smoothed_bpm
            
    def _calculate_stability(self, current_bpm: float) -> float:
        """Calcula estabilidad del BPM basado en historia - MÁS ESTRICTA"""
        self.bpm_history.append(current_bpm)
        
        if len(self.bpm_history) < 8:  # Era 3, ahora 8
            return 0.0
            
        recent_bpms = list(self.bpm_history)[-10:]  # Últimos 10
        
        # Filtro de mediana para eliminar outliers
        median_bpm = np.median(recent_bpms)
        filtered_bpms = [bpm for bpm in recent_bpms if abs(bpm - median_bpm) < 5.0]
        
        if len(filtered_bpms) < 5:
            return 0.0
        
        std_dev = np.std(filtered_bpms)
        mean_bpm = np.mean(filtered_bpms)
        
        # Estabilidad más estricta
        if mean_bpm > 0:
            stability = max(0.0, 1.0 - (std_dev / mean_bpm * 25))  # Era 10, ahora 25
        else:
            stability = 0.0
            
        return stability
        
    def _guess_genre_from_bpm(self, bpm: float) -> Optional[str]:
        """Sugiere género basado en BPM"""
        for genre, (min_bpm, max_bpm) in self.genre_bpm_ranges.items():
            if min_bpm <= bpm <= max_bpm:
                return genre
        return None
        
    def _update_state(self, result: BPMResult):
        """Actualiza estado interno con nuevo resultado"""
        # Aplicar suavizado antes de guardar
        if result.bpm > 0:
            smoothed_bpm = self._apply_smoothing(result.bpm)
            self.current_bpm = smoothed_bpm
        
        self.confidence = result.confidence
        self.is_stable = result.stability > 0.85  # Era 0.7, ahora 0.85 - más estricto
        
        # Agregar beats a historia
        if result.beat_times:
            self.beat_history.extend(result.beat_times)
            
    # ========== API PÚBLICA ==========
    
    def get_current_bpm(self) -> float:
        """Retorna BPM actual"""
        return self.current_bpm
        
    def get_confidence(self) -> float:
        """Retorna confidence del BPM actual"""
        return self.confidence
        
    def is_bpm_stable(self) -> bool:
        """Retorna si el BPM es estable"""
        return self.is_stable
        
    def get_status_info(self) -> dict:
        """Información para mostrar en ventana MONITOR"""
        return {
            'bpm': round(self.current_bpm, 1),
            'confidence': round(self.confidence * 100, 1),
            'stable': self.is_stable,
            'buffer_size': len(self.audio_buffer),
            'delay_ms': int(self.delay_seconds * 1000),
            'history_size': len(self.bpm_history),
            'genre_hint': self._guess_genre_from_bpm(self.current_bpm) if self.current_bpm > 0 else None
        }
        
    def get_beat_sync_info(self) -> dict:
        """Información para sincronización con Titan"""
        recent_beats = list(self.beat_history)[-10:] if self.beat_history else []
        
        return {
            'bpm': self.current_bpm,
            'beat_times': recent_beats,
            'next_beat_prediction': self._predict_next_beat(),
            'sync_ready': self.is_stable and self.confidence > 0.7  # Era 0.6, ahora 0.7
        }
        
    def _predict_next_beat(self) -> Optional[float]:
        """Predice cuándo será el próximo beat"""
        if not self.beat_history or self.current_bpm == 0:
            return None
            
        last_beat = self.beat_history[-1]
        beat_interval = 60.0 / self.current_bpm
        next_beat = last_beat + beat_interval
        
        return next_beat
        
    def force_bpm(self, bpm: float):
        """Fuerza un BPM específico (para override manual)"""
        self.current_bpm = bpm
        self._smoothed_bpm = bpm
        self.confidence = 1.0
        self.bpm_history.clear()
        self._bpm_buffer.clear()
        # Llenar buffer con el BPM forzado para estabilidad
        for _ in range(5):
            self.bpm_history.append(bpm)
            self._bpm_buffer.append(bpm)
        
    def reset(self):
        """Reset completo del detector"""
        self.audio_buffer.clear()
        self.bpm_history.clear()
        self.beat_history.clear()
        self._bpm_buffer.clear()
        self.current_bpm = 0.0
        self._smoothed_bpm = 0.0
        self.confidence = 0.0
        self.is_stable = False


# ========== INTEGRACIÓN CON 911 FIESTA ==========

class BPMMonitorCard:
    """Card para mostrar BPM en ventana MONITOR"""
    
    def __init__(self, detector: BPMDetector):
        self.detector = detector
        self.name = "BPM Detector"
        
    def render_status(self) -> str:
        """Renderiza status para UI"""
        info = self.detector.get_status_info()
        
        status_lines = [
            f"BPM: {info['bpm']} {'✓' if info['stable'] else '~'}",
            f"Confidence: {info['confidence']}%",
            f"Genre: {info['genre_hint'] or 'Unknown'}",
            f"Delay: {info['delay_ms']}ms",
            f"Buffer: {info['buffer_size']} samples"
        ]
        
        return "\n".join(status_lines)
        
    def get_main_value(self) -> str:
        """Valor principal para display grande"""
        return f"{self.detector.get_current_bpm():.1f} BPM"
        
    def is_ready_for_sync(self) -> bool:
        """¿Está listo para enviar a Titan?"""
        sync_info = self.detector.get_beat_sync_info()
        return sync_info['sync_ready']