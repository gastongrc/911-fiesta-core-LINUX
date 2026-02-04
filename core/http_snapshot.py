"""
HTTP Snapshot Server - Expone estado REAL del CORE via HTTP.

Corre en el MISMO proceso que main.py (GUI).
La API web (proceso separado) hace requests a este server.

Puerto: 8010 (127.0.0.1 - solo local)
Endpoint: GET /core/snapshot

Este es el ÚNICO punto de verdad. La web solo refleja lo que este server dice.
"""
import time
import threading
from datetime import datetime
from typing import Any, Dict, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class SnapshotServer:
    """
    Microserver HTTP que expone el estado del CORE.
    Thread-safe, no bloquea el GUI.
    """

    def __init__(self, port: int = 8010):
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Referencias a managers del CORE (se setean desde main.py)
        self.state_manager = None
        self.audio_engine = None
        self.avolites = None
        self.cue_engine = None
        self.vision_manager = None
        self.calendar_manager = None
        self.energy_detector = None
        self.audio_monitor = None

    def set_managers(
        self,
        state_manager=None,
        audio_engine=None,
        avolites=None,
        cue_engine=None,
        vision_manager=None,
        calendar_manager=None,
        energy_detector=None,
        audio_monitor=None,
    ):
        """Setea referencias a los managers del CORE."""
        self.state_manager = state_manager
        self.audio_engine = audio_engine
        self.avolites = avolites
        self.cue_engine = cue_engine
        self.vision_manager = vision_manager
        self.calendar_manager = calendar_manager
        self.energy_detector = energy_detector
        self.audio_monitor = audio_monitor

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Genera snapshot del estado REAL del CORE.
        Si algo no está disponible → null, NUNCA inventar.
        """
        now = datetime.now()
        ts = int(time.time())

        # ====== STATE & ENERGY ======
        state = None
        energy = None

        if self.state_manager:
            try:
                state = self.state_manager.get_state()
                energy = self.state_manager.get_energy()
            except Exception as e:
                print(f"[HTTP_SNAPSHOT] StateManager error: {e}")

        # ====== AUDIO ======
        audio = {
            "running": False,
            "device": None,
            "level": 0.0,
            "silence": True,
            "clipping": False,
        }

        if self.audio_engine:
            try:
                audio["running"] = getattr(self.audio_engine, 'is_running', False)
                audio["device"] = getattr(self.audio_engine, 'device_name', None)

                # Nivel desde audio_monitor
                if self.audio_monitor:
                    level = getattr(self.audio_monitor, 'current_level', 0.0)
                    if level:
                        audio["level"] = round(level, 3)
                        audio["silence"] = level < 0.001
                        audio["clipping"] = level > 0.95
                else:
                    # Desde engine.get_status()
                    try:
                        status = self.audio_engine.get_status()
                        rms = status.get("rms_db", -60)
                        if rms > -60:
                            level = 10 ** (rms / 20)
                            audio["level"] = round(level, 3)
                            audio["silence"] = rms < -50
                            audio["clipping"] = rms > -3
                    except:
                        pass
            except Exception as e:
                print(f"[HTTP_SNAPSHOT] AudioEngine error: {e}")

        # ====== AVOLITES ======
        avolites = {
            "connected": False,
            "ip": "",
            "port": 4430,
            "latency_ms": None,
            "last_error": None,
        }

        if self.avolites:
            try:
                status = self.avolites.get_status()
                avolites["connected"] = status.get("is_connected", False)
                avolites["ip"] = status.get("console_ip", "")
                avolites["port"] = status.get("console_port", 4430)
                avolites["last_error"] = status.get("last_error")

                latency = status.get("latency_ms")
                if latency is not None:
                    avolites["latency_ms"] = int(latency)
            except Exception as e:
                print(f"[HTTP_SNAPSHOT] Avolites error: {e}")

        # ====== CAMERAS (VISION) ======
        cameras = {
            "haze": {"online": False, "fps": 0, "ip": ""},
            "people": {"online": False, "fps": 0, "ip": ""},
            "tracking": {"online": False, "fps": 0, "ip": ""},
        }

        if self.vision_manager:
            try:
                vm = self.vision_manager
                for cam_type in ["haze", "people", "tracking"]:
                    handler = getattr(vm, f"{cam_type}_handler", None)
                    if not handler:
                        # Intentar con otro naming
                        handler = getattr(vm, f"cam_{cam_type}", None)
                    if handler:
                        cameras[cam_type]["online"] = getattr(handler, 'is_running', False)
                        cameras[cam_type]["ip"] = getattr(handler, 'camera_ip', "") or ""
                        cameras[cam_type]["fps"] = getattr(handler, 'current_fps', 0) or 0
            except Exception as e:
                print(f"[HTTP_SNAPSHOT] Vision error: {e}")

        # ====== CALENDAR ======
        days_es = {
            "monday": "lunes", "tuesday": "martes", "wednesday": "miércoles",
            "thursday": "jueves", "friday": "viernes", "saturday": "sábado", "sunday": "domingo"
        }

        calendar = {
            "day": days_es.get(now.strftime("%A").lower(), now.strftime("%A").lower()),
            "time": now.strftime("%H:%M:%S"),
            "current_mode": None,
            "next_mode": None,
            "time_remaining_s": -1,
            "time_to_next_s": -1,
            "override_active": False,
            "auto": True,
            "source": None,
        }

        if self.calendar_manager:
            try:
                state_data = self.calendar_manager.get_state()
                calendar["current_mode"] = state_data.get("current_mode")
                calendar["next_mode"] = state_data.get("next_mode")
                calendar["override_active"] = state_data.get("is_override", False)
                calendar["auto"] = state_data.get("auto_mode_enabled", True)
                calendar["source"] = state_data.get("source")

                if state_data.get("time_remaining_s"):
                    calendar["time_remaining_s"] = state_data["time_remaining_s"]
                if state_data.get("time_to_next_s"):
                    calendar["time_to_next_s"] = state_data["time_to_next_s"]

                # next_change_at
                if state_data.get("next_change_at"):
                    try:
                        next_dt = datetime.fromisoformat(state_data["next_change_at"])
                        calendar["time_to_next_s"] = max(0, int((next_dt - now).total_seconds()))
                    except:
                        pass
            except Exception as e:
                print(f"[HTTP_SNAPSHOT] Calendar error: {e}")

        # ====== SYSTEM ======
        system = {"cpu": 0, "ram": 0, "gpu": 0, "temp": 0}
        try:
            import psutil
            system["cpu"] = int(psutil.cpu_percent(interval=None))
            system["ram"] = int(psutil.virtual_memory().percent)
        except:
            pass

        # ====== SNAPSHOT ======
        return {
            "ts": ts,
            "state": state,
            "energy": energy,
            "audio": audio,
            "avolites": avolites,
            "cameras": cameras,
            "calendar": calendar,
            "system": system,
        }

    def start(self):
        """Inicia el server HTTP en un thread separado."""
        if self._running:
            return

        server_instance = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silenciar logs HTTP

            def do_GET(self):
                if self.path == "/core/snapshot":
                    snapshot = server_instance.get_snapshot()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(snapshot).encode())
                elif self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok"}')
                else:
                    self.send_response(404)
                    self.end_headers()

        try:
            self._server = HTTPServer(("127.0.0.1", self.port), Handler)
            self._running = True

            def run():
                print(f"[HTTP_SNAPSHOT] Server started on 127.0.0.1:{self.port}")
                self._server.serve_forever()

            self._thread = threading.Thread(target=run, daemon=True)
            self._thread.start()

        except Exception as e:
            print(f"[HTTP_SNAPSHOT] Failed to start: {e}")
            self._running = False

    def stop(self):
        """Detiene el server HTTP."""
        if self._server:
            self._server.shutdown()
            self._running = False
            print("[HTTP_SNAPSHOT] Server stopped")


# Singleton global
_snapshot_server: Optional[SnapshotServer] = None


def get_snapshot_server() -> SnapshotServer:
    """Obtiene el singleton del SnapshotServer."""
    global _snapshot_server
    if _snapshot_server is None:
        _snapshot_server = SnapshotServer()
    return _snapshot_server


def start_snapshot_server(
    state_manager=None,
    audio_engine=None,
    avolites=None,
    cue_engine=None,
    vision_manager=None,
    calendar_manager=None,
    energy_detector=None,
    audio_monitor=None,
    port: int = 8010,
):
    """
    Función helper para iniciar el SnapshotServer con todos los managers.
    Llamar desde main.py después de inicializar todo.
    """
    server = get_snapshot_server()
    server.port = port
    server.set_managers(
        state_manager=state_manager,
        audio_engine=audio_engine,
        avolites=avolites,
        cue_engine=cue_engine,
        vision_manager=vision_manager,
        calendar_manager=calendar_manager,
        energy_detector=energy_detector,
        audio_monitor=audio_monitor,
    )
    server.start()
    return server
