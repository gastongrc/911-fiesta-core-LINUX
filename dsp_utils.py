import numpy as np

def mono(x):
    return x if x.ndim==1 else x.mean(axis=1)

def rms(x):
    return float(np.sqrt(np.mean(x**2)) + 1e-12)

def db(x):
    import math
    return 20.0*np.log10(max(x,1e-12))

def band_energy(x, sr, lo, hi, nfft=2048):
    x = mono(x).astype(np.float32)
    if len(x) < nfft:
        x = np.pad(x, (0, nfft-len(x)))
    win = np.hanning(nfft).astype(np.float32)
    X = np.fft.rfft(x[:nfft]*win)
    mag = np.abs(X)
    freqs = np.fft.rfftfreq(nfft, 1.0/sr)
    m = (freqs>=lo)&(freqs<=hi)
    be = float(np.sum(mag[m]))
    te = float(np.sum(mag)+1e-9)
    return be, te, be/te
