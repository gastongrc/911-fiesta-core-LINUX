# weigher.py — Traduce perfil musical a pesos por categoria
# ==========================================================
# Pesos siempre en rango [0.8, 1.2] (clamp duro).
# Cambios suavizados con EMA para evitar oscilacion.
# Con perfil NEUTRAL todos los pesos son 1.0 (sin efecto).
# ==========================================================

# Pesos objetivo por perfil. Cada valor es un multiplicador de score.
# NEUTRAL = sin efecto (todo 1.0)
PROFILE_WEIGHTS = {
    "NEUTRAL": {
        "bajada": 1.0,
        "base_golpe": 1.0,
        "ataque": 1.0,
        "brake": 1.0,
    },
    "CALM": {
        "bajada": 1.10,      # Favorecer bajada en contexto calmado
        "base_golpe": 0.92,
        "ataque": 0.85,      # Dificultar ataque falso
        "brake": 1.05,
    },
    "RHYTHMIC": {
        "bajada": 0.90,
        "base_golpe": 1.12,  # Favorecer golpe en ritmo estable
        "ataque": 1.05,
        "brake": 0.95,
    },
    "INTENSE": {
        "bajada": 0.85,      # Dificultar bajada prematura
        "base_golpe": 0.95,
        "ataque": 1.15,      # Favorecer ataque en contexto intenso
        "brake": 1.0,
    },
}

# Limites absolutos de peso
WEIGHT_MIN = 0.8
WEIGHT_MAX = 1.2

# EMA alpha para suavizar transicion de pesos
_WEIGHT_EMA_ALPHA = 0.10


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class MusicWeigher:
    """
    Produce pesos por categoria segun el perfil musical activo.
    Pesos siempre en [0.8, 1.2], suavizados con EMA.
    """

    def __init__(self):
        self._weights = {
            "bajada": 1.0,
            "base_golpe": 1.0,
            "ataque": 1.0,
            "brake": 1.0,
        }

    def update(self, profile_name):
        """
        Actualiza pesos segun perfil. Llamar cada tick.

        Args:
            profile_name: Nombre de perfil activo ("CALM", "RHYTHMIC", "INTENSE", "NEUTRAL")
        """
        target = PROFILE_WEIGHTS.get(profile_name, PROFILE_WEIGHTS["NEUTRAL"])

        for k in self._weights:
            t = _clamp(target.get(k, 1.0), WEIGHT_MIN, WEIGHT_MAX)
            # EMA smoothing hacia el target
            self._weights[k] = (_WEIGHT_EMA_ALPHA * t) + ((1.0 - _WEIGHT_EMA_ALPHA) * self._weights[k])
            # Clamp final de seguridad
            self._weights[k] = _clamp(self._weights[k], WEIGHT_MIN, WEIGHT_MAX)

    def get_weights(self):
        """Retorna copia de pesos actuales."""
        return self._weights.copy()
