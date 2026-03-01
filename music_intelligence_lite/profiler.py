# profiler.py — Detecta perfil musical desde analyzers (sin ML)
# ==============================================================
# Lee module.card.is_on() de cada categoria y computa un perfil
# continuo con EMA smoothing. El perfil debe ser estable 1.5s
# antes de "lockearse" como perfil activo.
# ==============================================================
import time


# Perfiles predefinidos (deterministas)
PROFILE_CALM = "CALM"          # Predomina bajada, poca actividad
PROFILE_RHYTHMIC = "RHYTHMIC"  # Predomina golpe, ritmo estable
PROFILE_INTENSE = "INTENSE"    # Predomina ataque, alta energia
PROFILE_NEUTRAL = "NEUTRAL"    # Sin predominancia clara

# EMA alpha para suavizar ratios (evita jitter)
_EMA_ALPHA = 0.15

# Tiempo minimo de estabilidad antes de cambiar perfil (segundos)
_STABILITY_SECONDS = 1.5


class MusicProfiler:
    """
    Detecta el perfil musical actual a partir de los votos de analyzers.

    No modifica analyzers — solo lee module.card.is_on().
    Produce ratios suavizados por categoria y un perfil discreto.
    """

    def __init__(self):
        # Ratios suavizados (EMA) por categoria
        self._ratios = {
            "bajada": 0.0,
            "base_golpe": 0.0,
            "ataque": 0.0,
            "brake": 0.0,
        }

        # Perfil actual (lockeado) y candidato
        self.active_profile = PROFILE_NEUTRAL
        self._candidate_profile = PROFILE_NEUTRAL
        self._candidate_since = time.monotonic()

    def update(self, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """
        Actualiza ratios y perfil. Llamar cada tick (~40ms).

        Args:
            modules_*: Listas de modulos activos (mismos que van a StateManager)
        """
        # Calcular ratio crudo por categoria
        raw = {
            "bajada": self._vote_ratio(modules_bajada),
            "base_golpe": self._vote_ratio(modules_golpe),
            "ataque": self._vote_ratio(modules_ataque),
            "brake": self._vote_ratio(modules_brake),
        }

        # Aplicar EMA smoothing
        for k in self._ratios:
            self._ratios[k] = (_EMA_ALPHA * raw[k]) + ((1.0 - _EMA_ALPHA) * self._ratios[k])

        # Determinar perfil candidato
        candidate = self._classify_profile()

        # Estabilidad: solo cambiar si candidato es estable >= 1.5s
        now = time.monotonic()
        if candidate != self._candidate_profile:
            self._candidate_profile = candidate
            self._candidate_since = now
        elif (now - self._candidate_since) >= _STABILITY_SECONDS:
            self.active_profile = candidate

    def get_ratios(self):
        """Retorna copia de ratios suavizados."""
        return self._ratios.copy()

    def get_profile(self):
        """Retorna perfil activo (lockeado)."""
        return self.active_profile

    def get_candidate(self):
        """Retorna perfil candidato (puede no estar lockeado aun)."""
        return self._candidate_profile

    def get_candidate_elapsed(self):
        """Segundos que el candidato lleva estable."""
        return time.monotonic() - self._candidate_since

    def _vote_ratio(self, modules):
        """Cuenta cuantos modulos tienen is_on() True / total."""
        if not modules:
            return 0.0
        active = 0
        for m in modules:
            try:
                if hasattr(m, 'card') and m.card and hasattr(m.card, 'is_on'):
                    if m.card.is_on():
                        active += 1
            except Exception:
                pass
        return active / len(modules)

    def _classify_profile(self):
        """Clasifica perfil basado en ratios suavizados."""
        r = self._ratios
        # Prioridad: INTENSE > RHYTHMIC > CALM > NEUTRAL
        if r["ataque"] >= 0.5:
            return PROFILE_INTENSE
        if r["base_golpe"] >= 0.4 and r["ataque"] < 0.3:
            return PROFILE_RHYTHMIC
        if r["bajada"] >= 0.4 and r["base_golpe"] < 0.25:
            return PROFILE_CALM
        return PROFILE_NEUTRAL
