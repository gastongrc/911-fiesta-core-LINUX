# logger.py — CSV logger para MIL-Lite (no bloquea hilo principal)
# ================================================================
# Escribe un CSV por sesion en logs/ con perfil, pesos y metricas.
# Logging cada 200ms maximo. Si falla, se desactiva silenciosamente.
# ================================================================
import os
import time


class MILLogger:
    """
    Logger CSV para MIL-Lite. No bloquea si falla.
    Un archivo por sesion en logs/.
    """

    # Intervalo minimo entre escrituras (segundos)
    LOG_INTERVAL = 0.200

    def __init__(self):
        self._file = None
        self._last_log_time = 0.0
        self._enabled = True
        self._init_file()

    def _init_file(self):
        """Crea carpeta logs/ y archivo CSV."""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logs_dir = os.path.join(base_dir, "logs")
            os.makedirs(logs_dir, exist_ok=True)

            ts = time.strftime("%Y%m%d_%H%M%S")
            path = os.path.join(logs_dir, f"mil_lite_{ts}.csv")
            self._file = open(path, "w", buffering=1)  # line-buffered

            # Header
            self._file.write(
                "timestamp,profile,candidate,cand_elapsed_s,"
                "ratio_bajada,ratio_golpe,ratio_ataque,ratio_brake,"
                "weight_bajada,weight_golpe,weight_ataque,weight_brake,"
                "sm_state\n"
            )
            print(f"[MIL-Lite] Log: {path}")
        except Exception as e:
            print(f"[MIL-Lite] Logger desactivado: {e}")
            self._enabled = False
            self._file = None

    def log(self, profile, candidate, cand_elapsed, ratios, weights, sm_state):
        """
        Escribe una linea si han pasado >= 200ms desde la ultima.
        No bloquea si falla.
        """
        if not self._enabled or self._file is None:
            return

        now = time.monotonic()
        if (now - self._last_log_time) < self.LOG_INTERVAL:
            return

        self._last_log_time = now

        try:
            ts = f"{time.time():.3f}"
            line = (
                f"{ts},{profile},{candidate},{cand_elapsed:.2f},"
                f"{ratios.get('bajada', 0):.3f},{ratios.get('base_golpe', 0):.3f},"
                f"{ratios.get('ataque', 0):.3f},{ratios.get('brake', 0):.3f},"
                f"{weights.get('bajada', 1):.3f},{weights.get('base_golpe', 1):.3f},"
                f"{weights.get('ataque', 1):.3f},{weights.get('brake', 1):.3f},"
                f"{sm_state}\n"
            )
            self._file.write(line)
        except Exception:
            # No bloquear el hilo principal
            self._enabled = False
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def close(self):
        """Cierra archivo de log."""
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None
