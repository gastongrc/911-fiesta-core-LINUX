# analyzers/dynamic_pulse.py – DYNAMIC PULSE (BASE GOLPE) v2025-09-06
"""
Dynamic Pulse Analyzer - Detects intensity variations within rhythmic loops.

This module analyzes the dynamic variation of beat intensities using robust 
statistical methods (MAD - Median Absolute Deviation). High VU values indicate 
significant intensity changes between beats within the analyzed window.

Algorithm:
1. Converts audio to mono and calculates onset envelope
2. Finds peaks using configurable threshold
3. Filters peaks within temporal window
4. Calculates MAD/median ratio for robust variation measurement
5. Applies exponential smoothing for visual stability
6. Implements LED with hysteresis and configurable hold time

Author: Audio Analysis Team
Version: 2025-09-06
"""

import logging
import numpy as np
from typing import Optional, Tuple

try:
    from base_module import BaseModule
    from module_card import ModuleCard
    from rhythm_tools import mono, env_onset, find_peaks
except ImportError as e:
    logging.error(f"Failed to import required dependencies: {e}")
    raise

# Configure logging
logger = logging.getLogger(__name__)

class DynamicPulse(BaseModule):
    """
    Dynamic Pulse Analyzer for detecting beat intensity variations.
    
    Uses MAD (Median Absolute Deviation) to robustly measure the variation
    in beat amplitudes within a sliding temporal window.
    """
    
    name = "DYNAMIC PULSE"
    flag_name = "DYNAMIC_PULSE"  # V10: Flag para votación en BaseGolpe

    # Constants - Audio Analysis
    EPS = 1e-12
    SILENCE_THRESHOLD_DBFS = -74.0  # dBFS threshold for silence gate
    SILENCE_RMS_THRESHOLD = 2e-4    # Linear RMS equivalent to -74 dBFS
    SILENCE_DECAY_TIME = 0.18       # seconds for VU decay during silence
    
    # Constants - Peak Detection
    MIN_PEAKS_FOR_ANALYSIS = 3      # Minimum peaks needed for variation calc
    MIN_WINDOW_SECONDS = 0.6        # Minimum analysis window
    MAX_WINDOW_SECONDS = 6.0        # Maximum analysis window
    
    # Constants - LED Control
    LED_THRESHOLD_ON = 0.60         # VU threshold to turn LED on
    LED_THRESHOLD_OFF = 0.50        # VU threshold to turn LED off
    LED_HOLD_MULTIPLIER = 1.5       # hold_off = hold_on * multiplier
    
    # Constants - Smoothing - OPTIMIZADO
    MIN_SMOOTH_TIME_MS = 80.0       # Minimum smoothing time
    MAX_SMOOTH_TIME_MS = 600.0      # Maximum smoothing time
    SMOOTH_CURVE_POWER = 2.0        # Power for smoothing curve
    
    # Constants - Normalization
    PERCENTAGE_THRESHOLD = 1.5      # Values > 1.5 treated as percentages
    PERCENTAGE_SCALE = 0.01         # Scale factor for percentage conversion
    MATCH_TOLERANCE = 1e-6          # Tolerance for match comparison

    def __init__(self):
        """Initialize the Dynamic Pulse analyzer."""
        super().__init__()
        
        try:
            self.card = ModuleCard(self.name)
            self._setup_controls()
            self._init_state()
            logger.info(f"Initialized {self.name} module successfully")
        except Exception as e:
            logger.error(f"Failed to initialize {self.name}: {e}")
            raise

    def _setup_controls(self) -> None:
        """Setup the module's control interface."""
        # Peak detection threshold (accepts 0..1 or 0..100)
        self.card.add_slider("thr", "Peak Threshold", 0.10, 0.90, 0.35)
        
        # Target variation (MAD/median) for VU≈1
        self.card.add_slider("var_ok", "Target Variation", 0.05, 0.60, 0.25)
        
        # Analysis window (seconds) for variation calculation
        self.card.add_slider("win_s", "Window (s)", 1.0, 4.0, 2.0)
        
        # Visual smoothing - OPTIMIZADO
        self.card.add_slider("smooth", "Smoothing", 0.0, 0.85, 0.45)
        
        # LED hold time - OPTIMIZADO
        self.card.add_slider("hold", "Hold ON (ms)", 50.0, 400.0, 120.0)
        
        # Dynamic indicator LED
        self.card.add_led("dyn", "Dynamic")

    def _init_state(self) -> None:
        """Initialize internal state variables."""
        self._vu = 0.0          # Current VU meter value
        self._on = False        # LED state
        self._ton = 0.0         # Time LED has been above threshold
        self._toff = 0.0        # Time LED has been below threshold
        
        # NUEVO: Variables de cache
        self._mad_cache_hash = None
        self._mad_cache_value = 0.0

    def process(self, block: Optional[np.ndarray], sr: Optional[float]) -> None:
        """
        Process audio block and update dynamic pulse analysis.
        
        Args:
            block: Audio block as numpy array or None
            sr: Sample rate in Hz or None
        """
        # Validate inputs
        if not self._validate_inputs(block, sr):
            return
            
        try:
            x = mono(block).astype(np.float32, copy=False)
            n = len(x)
            if n == 0:
                logger.debug("Empty audio block received")
                return
                
            dt = n / float(sr)
            
            # Apply silence gate
            if self._apply_silence_gate(x, dt):
                return
                
            # Get current control values
            params = self._get_control_parameters()
            
            # Analyze dynamic variation
            variation_data = self._analyze_variation(x, sr, params)
            
            # Apply smoothing and render
            self._apply_smoothing_and_render(variation_data, dt, params)
            
        except Exception as e:
            logger.error(f"Error processing audio block: {e}")
            # Graceful degradation - maintain current state
            self._render(self._vu, 0.02)

    def _validate_inputs(self, block: Optional[np.ndarray], sr: Optional[float]) -> bool:
        """
        Validate input parameters.
        
        Args:
            block: Audio block
            sr: Sample rate
            
        Returns:
            True if inputs are valid, False otherwise
        """
        if block is None:
            logger.debug("Received None audio block")
            return False
            
        if sr is None or sr <= 0:
            logger.debug(f"Invalid sample rate: {sr}")
            return False
            
        return True

    def _apply_silence_gate(self, x: np.ndarray, dt: float) -> bool:
        """
        Apply silence gate with exponential decay.
        
        Args:
            x: Audio samples
            dt: Time delta in seconds
            
        Returns:
            True if silence detected (processing should stop), False otherwise
        """
        rms = float(np.sqrt(np.mean(x * x)) + self.EPS)
        
        if rms < self.SILENCE_RMS_THRESHOLD:
            # Exponential decay during silence
            decay_factor = np.exp(-dt / self.SILENCE_DECAY_TIME)
            self._vu = float(decay_factor * self._vu)
            self._render(float(np.clip(self._vu, 0.0, 1.0)), dt)
            return True
            
        return False

    def _get_control_parameters(self) -> dict:
        """
        Get and validate current control parameter values.
        
        Returns:
            Dictionary of validated parameters
        """
        return {
            'thr': self._normalize_01(self.card.get_value("thr")),
            'var_ok': float(np.clip(self.card.get_value("var_ok"), 0.02, 1.00)),
            'win_s': float(np.clip(self.card.get_value("win_s"), 
                                 self.MIN_WINDOW_SECONDS, self.MAX_WINDOW_SECONDS)),
            'smooth': float(np.clip(self.card.get_value("smooth"), 0.0, 0.85)),
            'hold': float(np.clip(self.card.get_value("hold"), 50.0, 400.0))
        }

    def _analyze_variation(self, x: np.ndarray, sr: float, params: dict) -> dict:
        """
        Analyze dynamic variation in the audio signal.
        
        Args:
            x: Audio samples
            sr: Sample rate
            params: Control parameters
            
        Returns:
            Dictionary containing analysis results
        """
        # Calculate onset envelope and find peaks
        env, hop = env_onset(x)
        if env.size < 3:
            logger.debug("Insufficient envelope data for analysis")
            return {'v_raw': 0.0, 'med': 0.0, 'rcv': 0.0, 'pk_count': 0}
        
        # Find peaks with threshold
        pk = find_peaks(env, float(np.clip(params['thr'], 0.0, 1.0)))
        
        # Filter peaks within temporal window
        pk_filtered = self._filter_peaks_by_window(pk, env, hop, sr, params['win_s'])
        
        # Calculate robust variation
        return self._calculate_robust_variation(env, pk_filtered, params['var_ok'])

    def _filter_peaks_by_window(self, pk: np.ndarray, env: np.ndarray, 
                               hop: int, sr: float, win_s: float) -> np.ndarray:
        """
        Filter peaks to only include those within the analysis window.
        
        Args:
            pk: Peak indices
            env: Envelope array
            hop: Hop size in samples
            sr: Sample rate
            win_s: Window size in seconds
            
        Returns:
            Filtered peak indices
        """
        if pk.size == 0:
            return pk
            
        hop_s = hop / float(sr)
        take = int(max(1, round(win_s / max(hop_s, self.EPS))))
        i0 = max(0, env.size - take)
        
        return pk[pk >= i0]

    def _calculate_robust_variation(self, env: np.ndarray, pk: np.ndarray, 
                                  var_ok: float) -> dict:
        """
        Calculate robust variation using MAD (Median Absolute Deviation).
        
        Args:
            env: Envelope array
            pk: Peak indices
            var_ok: Target variation for normalization
            
        Returns:
            Dictionary with variation analysis results
        """
        if pk.size < self.MIN_PEAKS_FOR_ANALYSIS:
            return {'v_raw': 0.0, 'med': 0.0, 'rcv': 0.0, 'pk_count': pk.size}
        
        amps = env[pk]
        med = float(np.median(amps))
        mad = self._calculate_mad(amps)
        
        # Robust coefficient of variation
        rcv = float(mad / max(med, self.EPS))
        
        # Normalize to target variation
        v_raw = float(np.clip(rcv / var_ok, 0.0, 1.0))
        
        return {
            'v_raw': v_raw,
            'med': med,
            'rcv': rcv,
            'pk_count': pk.size
        }

    def _calculate_mad(self, a: np.ndarray) -> float:
        """
        Calcula MAD con cache para evitar recálculos - OPTIMIZADO.
        
        Args:
            a: Input array
            
        Returns:
            MAD value
        """
        if len(a) == 0:
            return 0.0
        
        # ✅ Cache si el array no cambió
        array_hash = hash(a.tobytes())
        if hasattr(self, '_mad_cache_hash') and self._mad_cache_hash == array_hash:
            return self._mad_cache_value
        
        med = np.median(a)
        mad_val = float(np.median(np.abs(a - med)) + self.EPS)
        
        self._mad_cache_hash = array_hash
        self._mad_cache_value = mad_val
        return mad_val

    def _apply_smoothing_and_render(self, variation_data: dict, dt: float, 
                                  params: dict) -> None:
        """
        Apply exponential smoothing and render the result.
        
        Args:
            variation_data: Results from variation analysis
            dt: Time delta
            params: Control parameters
        """
        v_raw = variation_data['v_raw']
        
        # Calculate smoothing time constant
        tau_ms = (self.MIN_SMOOTH_TIME_MS + 
                 (self.MAX_SMOOTH_TIME_MS - self.MIN_SMOOTH_TIME_MS) * 
                 (params['smooth'] ** self.SMOOTH_CURVE_POWER))
        
        # Apply exponential smoothing
        alpha = np.exp(-dt / (tau_ms / 1000.0))
        self._vu = (1.0 - alpha) * v_raw + alpha * self._vu
        v = float(np.clip(self._vu, 0.0, 1.0))
        
        # Update status display
        self._update_status_display(variation_data, v)
        
        # Render final result
        self._render(v, dt)

    def _update_status_display(self, variation_data: dict, v: float) -> None:
        """
        Update the status display with current analysis data.
        
        Args:
            variation_data: Analysis results
            v: Final smoothed value
        """
        try:
            status = (f"N={variation_data['pk_count']} | "
                     f"med={variation_data['med']:.2f} | "
                     f"rCV={variation_data['rcv']:.2f} | "
                     f"v={v:.2f}")
            self.card.set_status(status)
        except Exception as e:
            logger.debug(f"Failed to update status display: {e}")

    def _render(self, v: float, dt: float = 0.02) -> None:
        """
        Render the final output value and update LED state.
        
        Args:
            v: Current VU value (0.0 to 1.0)
            dt: Time delta in seconds
        """
        # Update main VU meter
        self.card.set_value(v)
        
        # Update LED with hysteresis and hold
        self._update_led_with_hysteresis(v, dt)
        
        # Update universal ON state
        self._update_universal_on_state(v)

    def _update_led_with_hysteresis(self, v: float, dt: float) -> None:
        """
        Update LED state with hysteresis and hold timing.
        
        Args:
            v: Current VU value
            dt: Time delta in seconds
        """
        hold_on = float(np.clip(self.card.get_value("hold"), 50.0, 400.0)) / 1000.0
        hold_off = self.LED_HOLD_MULTIPLIER * hold_on
        
        if v >= self.LED_THRESHOLD_ON:
            self._ton += dt
            self._toff = 0.0
            if self._ton >= hold_on:
                self._on = True
        elif v <= self.LED_THRESHOLD_OFF:
            self._toff += dt
            self._ton = 0.0
            if self._toff >= hold_off:
                self._on = False
                
        self.card.set_led("dyn", self._on)

    def _update_universal_on_state(self, v: float) -> None:
        """
        Update the universal ON state based on thresholds and match criteria.
        
        Args:
            v: Current VU value
        """
        try:
            lo, hi = self.card.get_thresholds()
            lo = self._normalize_01(lo)
            hi = self._normalize_01(hi)
            
            if hi < lo:
                lo, hi = hi, lo
                
            mreq = self._normalize_match(self.card.get_match())
            
            # Check if value is within range and meets match requirement
            in_range = lo <= v <= hi
            meets_match = (v * 100.0) >= mreq - self.MATCH_TOLERANCE
            
            self.card.set_on(in_range and meets_match)
            
        except Exception as e:
            logger.debug(f"Failed to update universal ON state: {e}")

    @staticmethod
    def _normalize_01(v) -> float:
        """
        Normalize value to 0..1 range, handling percentage values.
        
        Args:
            v: Input value (can be None, 0..1, or 0..100)
            
        Returns:
            Normalized value in 0..1 range
        """
        if v is None:
            return 0.0
        v = float(v)
        if v > DynamicPulse.PERCENTAGE_THRESHOLD:
            v *= DynamicPulse.PERCENTAGE_SCALE  # 0..100 → 0..1
        return float(np.clip(v, 0.0, 1.0))

    @staticmethod
    def _normalize_match(m) -> float:
        """
        Normalize match value to 0..100 range.
        
        Args:
            m: Input match value
            
        Returns:
            Normalized match value in 0..100 range
        """
        try:
            m = float(50.0 if m is None else m)
        except (TypeError, ValueError):
            m = 50.0
            
        if 0.0 <= m < 1.0:
            m *= 100.0
        elif m == 1.0:
            m = 1.0
            
        return float(np.clip(m, 0.0, 100.0))


# Module information for introspection
__version__ = "2025-09-06"
__author__ = "Audio Analysis Team"
__description__ = "Dynamic pulse analyzer using robust statistical variation detection"

if __name__ == "__main__":
    # Basic module test
    logging.basicConfig(level=logging.INFO)
    try:
        module = DynamicPulse()
        logger.info(f"Module {module.name} created successfully")
        logger.info(f"Version: {__version__}")
    except Exception as e:
        logger.error(f"Failed to create module: {e}")