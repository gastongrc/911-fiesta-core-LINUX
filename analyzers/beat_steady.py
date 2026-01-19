# analyzers/beat_steady.py — BEAT STEADY v2025-09-06 WORKING VERSION
# Detector de cadencia percutiva - FUNCIONAL Y SIMPLE
import numpy as np
from collections import deque

try:
    from module_card import ModuleCard
except Exception:
    class ModuleCard:
        def __init__(self, *a, **k): pass
        def add_slider(self, *a, **k): pass
        def add_led(self, *a, **k): pass
        def get_value(self, *a, **k): return 0
        def get_match(self): return 50
        def get_thresholds(self): return (0.0, 1.0)
        def set_value(self, *a, **k): pass
        def set_led(self, *a, **k): pass
        def set_on(self, *a, **k): pass
        def set_status(self, *a, **k): pass

EPS = 1e-12

def _safe_clip(val, min_val, max_val, default):
    """Safe clipping with fallback"""
    try:
        v = float(val) if val is not None else default
        return max(min_val, min(max_val, v))
    except:
        return default

class BeatSteady:
    name = "BEAT STEADY"

    def __init__(self):
        self.card = ModuleCard(self.name)
        
        # Setup sliders with working defaults
        self.card.add_slider("tol_pct", "Tolerancia IOI %", 5.0, 40.0, 15.0)
        self.card.add_slider("refrac", "Refractario (ms)", 40.0, 200.0, 80.0)
        self.card.add_slider("win_s", "Ventana (s)", 1.0, 4.0, 2.0)
        self.card.add_slider("thr_x", "Umbral onsets", 0.5, 3.0, 1.2)
        self.card.add_slider("dens_min", "Densidad mín", 0.5, 4.0, 1.5)
        self.card.add_slider("perc_w", "Peso percutivo", 0.0, 1.0, 0.6)
        self.card.add_slider("smooth", "Suavizado", 0.0, 0.8, 0.3)
        self.card.add_slider("kick_weight", "Peso kick", 0.3, 0.9, 0.7)
        self.card.add_slider("hat_weight", "Peso hats", 0.1, 0.7, 0.3)
        
        self.card.add_led("steady", "Estable")
        
        # State variables
        self.reset()

    def reset(self):
        """Reset all state"""
        self._time = 0.0
        self._vu = 0.0
        self._events = deque(maxlen=200)
        self._bpm = 0.0
        self._led_on = False
        
        # Filter states
        self._low_state = 0.0
        self._high_state = 0.0
        
        # Debug
        self._strength = 0.0
        self._consistency = 0.0
        self._density = 0.0
        self._perc_bias = 0.5

    def _get_param(self, name, default=0.0):
        """Get parameter with fallback"""
        try:
            val = self.card.get_value(name)
            return float(val) if val is not None else default
        except:
            return default

    def process(self, block, sr):
        """Main processing - simplified and working"""
        try:
            # Basic validation
            if block is None or sr <= 0:
                return
                
            x = np.asarray(block, dtype=np.float32)
            if x.size == 0:
                return
                
            # Convert to mono
            if x.ndim > 1:
                x = x.mean(axis=1)
                
            # Update time
            dt = len(x) / sr
            self._time += dt
            
            # Basic RMS check
            rms = np.sqrt(np.mean(x * x))
            
            # Silence gate
            if rms < 1e-4:
                self._vu *= 0.95  # Decay
                self._update_ui()
                return
                
            # Get parameters (with working defaults)
            threshold = _safe_clip(self._get_param("thr_x"), 0.5, 3.0, 1.2)
            refrac_ms = _safe_clip(self._get_param("refrac"), 40.0, 200.0, 80.0)
            window_s = _safe_clip(self._get_param("win_s"), 1.0, 4.0, 2.0)
            min_density = _safe_clip(self._get_param("dens_min"), 0.5, 4.0, 1.5)
            smooth = _safe_clip(self._get_param("smooth"), 0.0, 0.8, 0.3)
            
            # SIMPLE onset detection on full signal
            # Envelope
            env = np.abs(x)
            
            # Smooth envelope
            win_len = max(1, int(0.01 * sr))  # 10ms
            if win_len > 1 and len(env) > win_len:
                kernel = np.ones(win_len) / win_len
                env = np.convolve(env, kernel, mode='same')
            
            # Onset strength = positive differences
            onset = np.diff(env, prepend=env[0])
            onset = np.maximum(onset, 0.0)
            
            # Adaptive threshold
            if len(onset) > 10:
                med = np.median(onset)
                mad = np.median(np.abs(onset - med))
                thr = med + threshold * 1.4826 * mad
            else:
                thr = 0.0
                
            # Find peaks
            peaks = []
            refrac_samp = int(refrac_ms * sr / 1000.0)
            last_peak = -refrac_samp
            
            for i in range(len(onset)):
                if onset[i] > thr and i - last_peak >= refrac_samp:
                    # Simple peak check
                    is_peak = True
                    for j in range(max(0, i-1), min(len(onset), i+2)):
                        if j != i and onset[j] > onset[i]:
                            is_peak = False
                            break
                    
                    if is_peak:
                        peak_time = self._time - dt + i / sr
                        peaks.append(peak_time)
                        last_peak = i
            
            # Add new events
            for t in peaks:
                self._events.append(t)
                
            # Remove old events
            cutoff = self._time - window_s
            while self._events and self._events[0] < cutoff:
                self._events.popleft()
                
            # Analysis
            event_list = list(self._events)
            n_events = len(event_list)
            
            # Density
            self._density = n_events / window_s
            
            # BPM estimation
            if n_events >= 3:
                intervals = []
                for i in range(1, min(n_events, 10)):  # Last 9 intervals
                    dt_interval = event_list[-i] - event_list[-i-1]
                    if 0.2 <= dt_interval <= 2.0:  # 30-300 BPM
                        intervals.append(dt_interval)
                        
                if intervals:
                    avg_interval = np.median(intervals)
                    self._bpm = 60.0 / avg_interval
                    
                    # Consistency
                    if len(intervals) >= 2:
                        std_interval = np.std(intervals)
                        self._consistency = max(0.0, 1.0 - std_interval / avg_interval)
                    else:
                        self._consistency = 0.0
                        
                    # Strength - how many intervals are consistent
                    tolerance = _safe_clip(self._get_param("tol_pct"), 5.0, 40.0, 15.0) / 100.0
                    good = 0
                    for interval in intervals:
                        error = abs(interval - avg_interval) / avg_interval
                        if error <= tolerance:
                            good += 1
                    self._strength = good / len(intervals)
                else:
                    self._bpm = 0.0
                    self._strength = 0.0
                    self._consistency = 0.0
            else:
                self._bpm = 0.0
                self._strength = 0.0
                self._consistency = 0.0
                
            # Simple percussive bias (energy ratio)
            try:
                if len(x) >= 64:
                    X = np.fft.rfft(x)
                    mag = np.abs(X) ** 2
                    freqs = np.fft.rfftfreq(len(X), 1.0/sr)
                    
                    low_energy = np.sum(mag[(freqs >= 40) & (freqs <= 200)])
                    high_energy = np.sum(mag[(freqs >= 2000) & (freqs <= 8000)])
                    total_energy = np.sum(mag)
                    
                    if total_energy > 0:
                        self._perc_bias = (low_energy + high_energy) / total_energy
                    else:
                        self._perc_bias = 0.5
                else:
                    self._perc_bias = 0.5
            except:
                self._perc_bias = 0.5
                
            # Compute VU
            if self._density < min_density * 0.8:
                vu_raw = 0.0
            else:
                # Base quality
                base = 0.4 * self._strength + 0.6 * self._consistency
                
                # Density bonus
                density_factor = min(1.0, self._density / min_density)
                
                # Percussive factor
                perc_weight = _safe_clip(self._get_param("perc_w"), 0.0, 1.0, 0.6)
                perc_factor = 0.5 + 0.5 * self._perc_bias
                perc_contrib = (perc_factor - 0.75) * perc_weight * 0.3
                
                vu_raw = base * density_factor + perc_contrib
                vu_raw = max(0.0, min(1.0, vu_raw))
                
            # Smooth VU
            tau = 0.05 + 0.2 * smooth  # 50-250ms
            alpha = np.exp(-dt / tau)
            self._vu = (1.0 - alpha) * vu_raw + alpha * self._vu
            
            # Update UI
            self._update_ui()
            
        except Exception as e:
            # Fallback - at least show some activity
            try:
                x = np.asarray(block, dtype=np.float32)
                if x.ndim > 1:
                    x = x.mean(axis=1)
                rms = np.sqrt(np.mean(x * x))
                # Simple VU based on RMS
                self._vu = min(1.0, rms * 50.0)  # Rough scaling
                self._update_ui()
            except:
                pass

    def _update_ui(self):
        """Update all UI elements"""
        try:
            # Set VU meter value
            self.card.set_value(self._vu)
            
            # Status line
            if self._bpm > 0:
                status = f"BPM≈{self._bpm:.1f} | str={self._strength:.2f} cons={self._consistency:.2f} | dens={self._density:.1f}/s | perc={self._perc_bias:.2f} | v={self._vu:.2f}"
            else:
                status = f"str={self._strength:.2f} cons={self._consistency:.2f} | dens={self._density:.1f}/s | perc={self._perc_bias:.2f} | v={self._vu:.2f}"
            
            self.card.set_status(status)
            
            # LED
            if self._vu >= 0.4:
                self._led_on = True
            elif self._vu <= 0.2:
                self._led_on = False
            # Hysteresis between 0.2-0.4
            
            self.card.set_led("steady", self._led_on)
            
            # Universal ON
            try:
                lo, hi = self.card.get_thresholds()
                match_pct = self.card.get_match()
                
                lo = max(0.0, min(1.0, float(lo) if lo is not None else 0.0))
                hi = max(0.0, min(1.0, float(hi) if hi is not None else 1.0))
                match_val = max(0.0, min(1.0, float(match_pct)/100.0 if match_pct is not None else 0.5))
                
                if hi < lo:
                    lo, hi = hi, lo
                    
                in_range = lo <= self._vu <= hi
                above_match = self._vu >= match_val
                
                self.card.set_on(in_range and above_match)
            except:
                self.card.set_on(self._vu >= 0.5)
                
        except Exception:
            pass