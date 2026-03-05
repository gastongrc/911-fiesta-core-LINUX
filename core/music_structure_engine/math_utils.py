# math_utils.py — Shared DSP functions for Music Structure Engine
import numpy as np


def rms(x: np.ndarray) -> float:
    if x is None or x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def spectral_flux(prev_mag: np.ndarray, curr_mag: np.ndarray) -> float:
    """Half-wave rectified spectral flux (only positive changes)."""
    diff = curr_mag - prev_mag
    return float(np.sum(np.maximum(diff, 0.0)))


def onset_envelope_frame(block: np.ndarray, sr: int, hop: int = 512) -> np.ndarray:
    """Compute onset envelope via spectral flux for a block of audio.

    Returns one flux value per hop.
    """
    n_fft = 1024
    if block.size < n_fft:
        return np.zeros(1, dtype=np.float64)

    window = np.hanning(n_fft).astype(np.float64)
    n_hops = max(1, (block.size - n_fft) // hop + 1)
    envelope = np.zeros(n_hops, dtype=np.float64)
    prev_mag = None

    for i in range(n_hops):
        start = i * hop
        frame = block[start:start + n_fft].astype(np.float64) * window
        mag = np.abs(np.fft.rfft(frame))
        if prev_mag is not None:
            envelope[i] = spectral_flux(prev_mag, mag)
        prev_mag = mag

    return envelope


def autocorrelate(x: np.ndarray, max_lag: int = 0) -> np.ndarray:
    """Normalized autocorrelation via FFT."""
    n = x.size
    if n < 2:
        return np.zeros(1, dtype=np.float64)
    if max_lag <= 0:
        max_lag = n
    # zero-pad to next power of 2
    fft_size = 1
    while fft_size < 2 * n:
        fft_size <<= 1
    X = np.fft.rfft(x, fft_size)
    acf = np.fft.irfft(X * np.conj(X), fft_size)[:max_lag]
    if acf[0] > 0:
        acf /= acf[0]
    return acf


def bandpass_energy(block: np.ndarray, sr: int, lo_hz: float, hi_hz: float) -> float:
    """Energy in a frequency band using FFT magnitude."""
    n = block.size
    if n < 64:
        return 0.0
    mag = np.abs(np.fft.rfft(block.astype(np.float64)))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    if not np.any(mask):
        return 0.0
    return float(np.sqrt(np.mean(np.square(mag[mask]))))


def ema(prev: float, curr: float, alpha: float) -> float:
    """Exponential moving average single step."""
    return alpha * curr + (1.0 - alpha) * prev
