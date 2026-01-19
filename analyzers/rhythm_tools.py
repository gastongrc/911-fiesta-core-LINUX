# rhythm_tools.py
import numpy as np

EPS = 1e-12

def mono(x):
    """Convierte a mono si viene (N,2). Devuelve float32."""
    x = np.asarray(x)
    if x.ndim==2 and x.shape[1]>1:
        x = x.mean(axis=1)
    return x.astype(np.float32, copy=False)

def env_onset(x, n=1024, hop=512):
    """
    Envolvente de onsets simple (abs(diff) suavizada).
    Devuelve: env (T), hop_s (muestras entre frames).
    """
    x = np.asarray(x, dtype=np.float32)
    if len(x) < n:
        x = np.pad(x, (0, n-len(x)))

    # quitar DC y respiración lenta
    x = x - np.mean(x)
    if len(x) > 1:
        x[1:] -= 0.995 * x[:-1]

    # derivada y rectificación
    d = np.abs(np.diff(x, prepend=0))

    # downsample/average por hop
    acc = []
    for s in range(0, len(d)-n+1, hop):
        acc.append(float(np.mean(d[s:s+n])))
    if not acc:
        acc = [0.0]
    env = np.array(acc, dtype=np.float32)

    # normalizado robusto 0..1
    m = np.median(env)
    s = np.median(np.abs(env - m)) + EPS
    env = np.clip((env - m) / (3.0*s), 0.0, 1.0)
    return env, hop

def find_peaks(env, thr=0.3):
    """Picos locales por umbral en la envolvente."""
    if len(env) < 3:
        return np.array([], dtype=int)
    peaks = []
    for i in range(1, len(env)-1):
        if env[i] >= thr and env[i] >= env[i-1] and env[i] >= env[i+1]:
            peaks.append(i)
    return np.array(peaks, dtype=int)

def gaps_ms(peaks, hop, sr):
    """Diferencias entre picos en milisegundos."""
    if len(peaks) < 2:
        return np.array([], dtype=np.float32)
    hop_ms = 1000.0 * hop / float(sr)
    return np.diff(peaks) * hop_ms

def bpm_from_ms(gaps):
    """BPM a partir de mediana de gaps en ms."""
    if len(gaps) == 0:
        return 0.0
    med = float(np.median(gaps))
    if med <= 1e-3:
        return 0.0
    return 60000.0 / med

def autocorr_strength(env, sr, hop, bpm_min=60, bpm_max=180):
    """Fuerza de pulso (0..1) en rango de BPM por autocorrelación simple."""
    if len(env) < 5:
        return 0.0
    env0 = env - np.mean(env)
    ac = np.correlate(env0, env0, mode="full")[len(env0)-1:]
    ac = ac / (ac[0] + EPS)

    lmin = int(round((60.0/bpm_max) * sr / hop))
    lmax = int(round((60.0/bpm_min) * sr / hop))
    lmin = max(1, lmin)
    lmax = min(lmax, len(ac)-1)
    if lmax <= lmin:
        return 0.0

    peak = float(np.max(ac[lmin:lmax+1]))
    return float(np.clip(peak, 0.0, 1.0))

def cv(values):
    """Coeficiente de variación (std/mean) con guardas."""
    v = np.asarray(values, dtype=np.float32)
    if v.size < 2:
        return 1.0
    m = float(np.mean(v))
    s = float(np.std(v)) + EPS
    if m < EPS:
        return 1.0
    return float(s/m)
