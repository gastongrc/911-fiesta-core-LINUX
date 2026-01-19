import time
import numpy as np

class AudioMonitor:
    """
    Monitor liviano de estado de audio.
    NO modifica el motor musical.
    Solo detecta condiciones anómalas.
    """

    def __init__(self, engine, config: dict):
        self.engine = engine
        self.config = config

        self.alerts = {
            "no_audio": False,
            "clipping": False,
            "noise": False,
            "stream_lost": False,
        }

        self._silence_time = 0.0
        self._last_update = time.time()
        self._clip_counter = 0
        self._noise_counter = 0


    def update(self, block, rms: float):
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        # --- 1) STREAM LOST ---
        if not getattr(self.engine, "is_running", True):
            self.alerts["stream_lost"] = True
        else:
            self.alerts["stream_lost"] = False

        # --- 2) NO AUDIO ---
        if rms < self.config["silence_rms_min"]:
            self._silence_time += dt
        else:
            self._silence_time = 0

        self.alerts["no_audio"] = (
            self._silence_time >= self.config["silence_seconds"]
        )

        # --- 3) CLIPPING ---
        peak = float(np.max(np.abs(block))) if block is not None else 0.0

        if peak > self.config["clip_threshold"]:
            self._clip_counter += 1
        else:
            self._clip_counter = 0

        self.alerts["clipping"] = (
            self._clip_counter >= self.config["clip_frames"]
        )

        # --- 4) NOISE / LOW DYNAMIC RANGE ---
        if block is not None:
            dynamic_range = float(np.max(block) - np.min(block))
        else:
            dynamic_range = 1.0

        if dynamic_range < self.config["noise_dynamic_min"]:
            self._noise_counter += 1
        else:
            self._noise_counter = 0

        self.alerts["noise"] = (
            self._noise_counter >= self.config["noise_frames"]
        )


    def get_status(self) -> dict:
        """Retorna el estado actual de alertas"""
        return {
            "alerts": self.alerts.copy(),
            "timestamp": time.time(),
        }
