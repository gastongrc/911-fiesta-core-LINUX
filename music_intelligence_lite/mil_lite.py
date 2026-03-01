# mil_lite.py — Orquestador de Music Intelligence Lite
# ====================================================
# Conecta profiler + weigher + logger.
# Un solo metodo tick() se llama desde main.py.
# Si falla, el sistema sigue sin MIL-Lite.
# ====================================================
from .profiler import MusicProfiler
from .weigher import MusicWeigher
from .logger import MILLogger


class MILLite:
    """
    Music Intelligence Lite: ponderador global determinista.

    Cada tick:
    1. Profiler lee estados de analyzers → perfil musical
    2. Weigher traduce perfil → pesos por categoria [0.8, 1.2]
    3. Pesos se aplican al StateManager via set_mil_weights()
    4. Logger escribe CSV cada 200ms
    """

    def __init__(self, state_manager):
        self._sm = state_manager
        self._profiler = MusicProfiler()
        self._weigher = MusicWeigher()
        self._logger = MILLogger()
        self._enabled = True
        print("[MIL-Lite] Inicializado: profiler + weigher + logger")

    def tick(self, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """
        Ejecutar cada tick (~40ms), ANTES de state_manager.update().
        """
        if not self._enabled:
            return

        try:
            # 1. Actualizar perfil musical
            self._profiler.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)

            # 2. Actualizar pesos segun perfil
            profile = self._profiler.get_profile()
            self._weigher.update(profile)

            # 3. Aplicar pesos al StateManager
            weights = self._weigher.get_weights()
            if hasattr(self._sm, 'set_mil_weights'):
                self._sm.set_mil_weights(weights, profile=profile)

            # 4. Logging (max cada 200ms, no bloquea)
            self._logger.log(
                profile=profile,
                candidate=self._profiler.get_candidate(),
                cand_elapsed=self._profiler.get_candidate_elapsed(),
                ratios=self._profiler.get_ratios(),
                weights=weights,
                sm_state=self._sm.get_state(),
            )

        except Exception as e:
            print(f"[MIL-Lite] Error en tick: {e}")

    def get_status(self):
        """Retorna estado completo para UI/debug."""
        return {
            "enabled": self._enabled,
            "profile": self._profiler.get_profile(),
            "candidate": self._profiler.get_candidate(),
            "candidate_elapsed": round(self._profiler.get_candidate_elapsed(), 2),
            "ratios": self._profiler.get_ratios(),
            "weights": self._weigher.get_weights(),
        }

    def disable(self):
        """Desactiva MIL-Lite y restaura pesos a 1.0."""
        self._enabled = False
        if hasattr(self._sm, 'set_mil_weights'):
            self._sm.set_mil_weights({
                "bajada": 1.0, "base_golpe": 1.0,
                "ataque": 1.0, "brake": 1.0,
            })
        print("[MIL-Lite] DESACTIVADO — pesos restaurados a 1.0")

    def close(self):
        """Cleanup."""
        self.disable()
        self._logger.close()
