"""
VisionConfig PRO - Phase 6.11
Persistencia JSON para configuración del Vision System
Soporta: IP cameras (MJPEG Axis + RTSP H.264) - USB REMOVED

Phase 6.11: Soporte dual MJPEG + RTSP
- MJPEG: host + path -> http://host/path (Axis cameras)
- RTSP: url_main/url_sub -> rtsp://... (generic IP cameras)
- Auto-detección de protocolo basada en URL
"""
import json
import os
from typing import Any, Dict, List, Optional


class VisionConfig:
    """
    Manejo de configuración JSON para Vision System PRO.

    Estructura de vision_config.json (formato v6.8 - IP cameras):
    {
        "vision": {
            "enabled": true,
            "ip_only": true
        },
        "cameras": {
            "haze": {
                "type": "mjpeg",
                "enabled": false,
                "host": "0.0.0.0",
                "path": "/axis-cgi/mjpg/video.cgi?fps=10",
                "username": "root",
                "password": "root",
                "fps_target": 10,
                "timeout_s": 5.0,
                "reconnect_s": 2.0
            },
            "dj": {...},
            "artist": {...}
        },
        "haze": {...},
        "dj": {...},
        "tracking": {...},
        "calibration": {...}
    }

    Regla de validación:
    - "host" inválido si host == "" o host == "0.0.0.0"
    - Si inválido o enabled=false -> NO conectar
    """

    def __init__(self, path: str = "vision_config.json"):
        """
        Inicializa el manejador de configuración.

        Args:
            path: Ruta al archivo JSON de configuración
        """
        self.path = path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """
        Carga configuración desde archivo JSON.
        Si no existe, crea uno con defaults.

        Returns:
            dict: Configuración completa
        """
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                print(f"[VisionConfig] Configuración cargada desde {self.path}")
            except json.JSONDecodeError as e:
                print(f"[VisionConfig] Error JSON en {self.path}: {e}")
                self.data = self._get_defaults()
                self.save()
            except Exception as e:
                print(f"[VisionConfig] Error leyendo {self.path}: {e}")
                self.data = self._get_defaults()
        else:
            print(f"[VisionConfig] Archivo {self.path} no existe, creando defaults...")
            self.data = self._get_defaults()
            self.save()

        # Asegurar estructura cameras existe
        self._ensure_cameras_structure()

        # Log estado de cámaras
        self._log_cameras_status()

        return self.data

    def _ensure_cameras_structure(self):
        """Asegura que la estructura de cámaras existe con defaults."""
        if "vision" not in self.data:
            self.data["vision"] = {"enabled": True, "ip_only": True}

        # Force ip_only=True (USB removed)
        self.data["vision"]["ip_only"] = True

        if "cameras" not in self.data:
            self.data["cameras"] = self._get_default_cameras()
            print("[VisionConfig] Creando estructura cameras MJPEG (ip_only enforced)")

    def _log_cameras_status(self):
        """Log del estado de cada cámara al cargar."""
        if "cameras" not in self.data:
            print("[VisionConfig] WARNING: no cameras section in config")
            return

        print("[VisionConfig] === CAMERAS STATUS (MJPEG + RTSP) ===")

        # Iterar sobre todas las cámaras configuradas
        all_cameras = list(self.data["cameras"].keys())
        for cam_name in all_cameras:
            cam = self.data["cameras"].get(cam_name, {})
            cam_type = cam.get("type", "mjpeg")
            enabled = cam.get("enabled", False)

            # Determinar endpoint según tipo
            if cam_type == "rtsp" or cam.get("url_main") or cam.get("url_sub"):
                url_sub = cam.get("url_sub", "")
                url_main = cam.get("url_main", "")
                preferred = cam.get("preferred", "sub")
                endpoint = url_sub if (preferred == "sub" and url_sub) else (url_main or url_sub or "N/A")
                # Ocultar credenciales en log
                if "@" in endpoint:
                    try:
                        proto, rest = endpoint.split("://", 1)
                        if "@" in rest:
                            creds, host_part = rest.split("@", 1)
                            endpoint = f"{proto}://***@{host_part}"
                    except:
                        pass
                configured = bool(url_main or url_sub)
            else:
                # MJPEG mode
                host = cam.get("host", "0.0.0.0")
                endpoint = host
                configured = self.is_camera_configured(cam_name)
                # Validate host para posibles warnings
                self.validate_host(host, cam_name)

            status = "READY" if (configured and enabled) else ("NOT_CONFIGURED" if not configured else "DISABLED")
            print(f"[VisionConfig] camera {cam_name}: type={cam_type} endpoint={endpoint} enabled={enabled} -> {status}")

        print("[VisionConfig] === END CAMERAS STATUS ===")

    def _get_default_cameras(self) -> Dict[str, Dict[str, Any]]:
        """Retorna estructura de cámaras MJPEG vacía (no configurada)."""
        default_cam = {
            "type": "mjpeg",
            "enabled": False,
            "host": "0.0.0.0",
            "path": "/axis-cgi/mjpg/video.cgi?fps=10",
            "username": "root",
            "password": "root",
            "fps_target": 10,
            "timeout_s": 5.0,
            "reconnect_s": 2.0
        }
        return {
            "haze": default_cam.copy(),
            "dj": default_cam.copy(),
            "artist": default_cam.copy()
        }

    def is_ip_only(self) -> bool:
        """
        Verifica si el sistema está en modo IP only (sin USB).

        Returns:
            bool: True si ip_only=true en config
        """
        vision = self.data.get("vision", {})
        return vision.get("ip_only", True)  # Default True para nuevo comportamiento

    def validate_host(self, host: str, camera_name: str = "") -> tuple:
        """
        Valida un host IP y detecta posibles typos.

        Args:
            host: IP o hostname a validar
            camera_name: Nombre de cámara para logging

        Returns:
            tuple: (is_valid: bool, warning: str or None)
        """
        # Host vacío o placeholder
        if not host or host == "0.0.0.0" or host == "":
            return (False, None)

        warning = None

        # Detectar typo común: 192.160.x.x en lugar de 192.168.x.x
        if "192.160" in host:
            warning = f"TYPO? host={host} parece 192.160 (esperado 192.168)"
            print(f"[VisionConfig] WARNING {camera_name}: {warning}")

        # Detectar otros octetos sospechosos
        if host.startswith("192.") and not host.startswith("192.168."):
            octets = host.split(".")
            if len(octets) >= 2:
                second_octet = octets[1]
                if second_octet not in ["168", "160"]:
                    warning = f"UNUSUAL: host={host} no es red privada típica"
                    print(f"[VisionConfig] WARNING {camera_name}: {warning}")

        return (True, warning)

    def is_camera_configured(self, camera_name: str) -> bool:
        """
        Verifica si una cámara tiene configuración válida.
        Phase 6.11: Soporta MJPEG (host) y RTSP (url_main/url_sub).

        Args:
            camera_name: Nombre de cámara ("haze", "dj", "artist", "generic_2k", etc.)

        Returns:
            bool: True si tiene configuración válida
        """
        if "cameras" not in self.data:
            return False

        cam = self.data["cameras"].get(camera_name, {})
        cam_type = cam.get("type", "mjpeg").lower()

        # RTSP mode: verificar url_main o url_sub
        if cam_type == "rtsp" or cam.get("url_main") or cam.get("url_sub"):
            url = cam.get("url", "")
            url_main = cam.get("url_main", "")
            url_sub = cam.get("url_sub", "")
            return bool(url or url_main or url_sub)

        # MJPEG mode: verificar host válido
        host = cam.get("host", "")
        is_valid, _ = self.validate_host(host, camera_name)
        return is_valid

    def is_camera_enabled(self, camera_name: str) -> bool:
        """
        Verifica si una cámara está habilitada Y configurada.

        Args:
            camera_name: Nombre de cámara

        Returns:
            bool: True si enabled=true Y tiene host válido
        """
        if "cameras" not in self.data:
            return False

        cam = self.data["cameras"].get(camera_name, {})
        enabled = cam.get("enabled", False)

        if not enabled:
            return False

        return self.is_camera_configured(camera_name)

    def save(self) -> bool:
        """
        Guarda configuración a archivo JSON.

        Returns:
            bool: True si se guardó exitosamente
        """
        try:
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            print(f"[VisionConfig] Configuración guardada en {self.path}")
            return True
        except Exception as e:
            print(f"[VisionConfig] Error guardando {self.path}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de la configuración.

        Args:
            key: Clave a obtener (ej: "haze", "dj", "tracking")
            default: Valor por defecto si la clave no existe

        Returns:
            Valor de configuración o default
        """
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        """
        Establece un valor en la configuración.
        NO guarda automáticamente, llamar save() para persistir.

        Args:
            key: Clave a establecer
            value: Valor a guardar
        """
        self.data[key] = value

    def update(self, updates: Dict[str, Any]):
        """
        Actualiza múltiples valores de configuración.
        NO guarda automáticamente, llamar save() para persistir.

        Args:
            updates: Diccionario con actualizaciones
        """
        self.data.update(updates)

    # ===== HELPERS ESPECÍFICOS =====

    # NOTE: get_camera_index/set_camera_index REMOVED (USB removed in Phase 6.10)

    # ----- HAZE -----

    def get_haze_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de haze."""
        return self.data.get("haze", self._get_defaults()["haze"])

    def set_haze_enabled(self, enabled: bool):
        """Habilita/deshabilita haze y guarda."""
        if "haze" not in self.data:
            self.data["haze"] = self._get_defaults()["haze"]
        self.data["haze"]["enabled"] = enabled
        self.save()

    def set_haze_cooldown(self, min_seconds: int, max_seconds: int):
        """Establece rango de cooldown de haze y guarda."""
        if "haze" not in self.data:
            self.data["haze"] = self._get_defaults()["haze"]
        self.data["haze"]["cooldown_min"] = min_seconds
        self.data["haze"]["cooldown_max"] = max_seconds
        self.save()

    def set_haze_thresholds(self, low: int, med: int, high: int):
        """Establece umbrales de haze y guarda."""
        if "haze" not in self.data:
            self.data["haze"] = self._get_defaults()["haze"]
        self.data["haze"]["threshold_low"] = low
        self.data["haze"]["threshold_med"] = med
        self.data["haze"]["threshold_high"] = high
        self.save()

    # ----- DJ -----

    def get_dj_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de DJ detector."""
        return self.data.get("dj", self._get_defaults()["dj"])

    def set_dj_enabled(self, enabled: bool):
        """Habilita/deshabilita DJ detector y guarda."""
        if "dj" not in self.data:
            self.data["dj"] = self._get_defaults()["dj"]
        self.data["dj"]["enabled"] = enabled
        self.save()

    def set_dj_zones(self, zones: List[Dict[str, Any]]):
        """Establece zonas de DJ y guarda."""
        if "dj" not in self.data:
            self.data["dj"] = self._get_defaults()["dj"]
        self.data["dj"]["zones"] = zones
        self.data["dj"]["zones_count"] = len(zones)
        self.save()

    def get_dj_zones(self) -> List[Dict[str, Any]]:
        """Obtiene zonas de DJ configuradas."""
        dj_config = self.get_dj_config()
        return dj_config.get("zones", [])

    # ----- TRACKING -----

    def get_tracking_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa de artist tracker."""
        return self.data.get("tracking", self._get_defaults()["tracking"])

    def set_tracking_enabled(self, enabled: bool):
        """Habilita/deshabilita artist tracker y guarda."""
        if "tracking" not in self.data:
            self.data["tracking"] = self._get_defaults()["tracking"]
        self.data["tracking"]["enabled"] = enabled
        self.save()

    # ----- ARTIST (V9) -----

    def get_artist_config(self) -> Dict[str, Any]:
        """Obtiene configuración completa del Artist detector V9."""
        return self.data.get("artist", {
            "enabled": False,
            "zones_count": 8,
            "zones": [],
            "disappear_delay": 2.0,
            "conf_threshold": 0.35,
            "target_fps": 6.0,
        })

    def set_artist_enabled(self, enabled: bool):
        """Habilita/deshabilita Artist detector y guarda."""
        if "artist" not in self.data:
            self.data["artist"] = self.get_artist_config()
        self.data["artist"]["enabled"] = enabled
        self.save()

    def set_artist_zones(self, zones: List[Dict[str, Any]]):
        """Establece zonas de Artist y guarda."""
        if "artist" not in self.data:
            self.data["artist"] = self.get_artist_config()
        self.data["artist"]["zones"] = zones
        self.data["artist"]["zones_count"] = len(zones)
        self.save()

    def get_artist_zones(self) -> List[Dict[str, Any]]:
        """Obtiene zonas de Artist configuradas."""
        artist_config = self.get_artist_config()
        return artist_config.get("zones", [])

    # ----- CALIBRATION -----

    def get_calibration(self) -> Dict[str, Any]:
        """Obtiene datos de calibración."""
        return self.data.get("calibration", self._get_defaults()["calibration"])

    def set_haze_baseline(self, baseline: float):
        """Establece baseline de haze calibrado y guarda."""
        if "calibration" not in self.data:
            self.data["calibration"] = self._get_defaults()["calibration"]
        import time
        self.data["calibration"]["haze_baseline"] = baseline
        self.data["calibration"]["last_calibration"] = time.time()
        self.save()

    # ----- CAMERA SOURCES (v6.8 + v6.11 RTSP) -----

    def get_camera_source_config(self, camera_name: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene configuración de fuente de cámara (MJPEG o RTSP).
        Phase 6.11: Soporte dual MJPEG + RTSP con url_main/url_sub.

        Formatos soportados:
        1. MJPEG clásico: host + path -> http://host/path
        2. RTSP con url directa: url o url_main/url_sub
        3. Auto-detección de tipo basada en URL

        Args:
            camera_name: Nombre de cámara ("haze", "dj", "artist", "generic_2k", etc.)

        Returns:
            dict: Configuración de fuente lista para create_source_from_config(), o None si no configurada
        """
        # Verificar si hay estructura cameras
        if "cameras" not in self.data:
            return None

        cam = self.data["cameras"].get(camera_name, {})

        # Verificar enabled
        if not cam.get("enabled", False):
            return None

        cam_type = cam.get("type", "mjpeg").lower()

        # --- RTSP mode: usar url_main/url_sub directamente ---
        if cam_type == "rtsp" or cam.get("url_main") or cam.get("url_sub"):
            url = cam.get("url", "")
            url_main = cam.get("url_main", "")
            url_sub = cam.get("url_sub", "")

            # Si no hay URL directa, requiere al menos una de main/sub
            if not url and not url_main and not url_sub:
                print(f"[VisionConfig] {camera_name}: RTSP sin URL válida")
                return None

            return {
                "type": cam_type if cam_type in ("rtsp", "mjpeg") else "auto",
                "url": url,
                "url_main": url_main,
                "url_sub": url_sub,
                "preferred": cam.get("preferred", "sub"),
                "username": cam.get("username", ""),
                "password": cam.get("password", ""),
                "fps_target": cam.get("fps_target", 10),
                "timeout_s": cam.get("timeout_s", 5.0),
                "reconnect_s": cam.get("reconnect_s", 2.0)
            }

        # --- MJPEG mode: construir URL desde host + path ---
        host = cam.get("host", "")
        is_valid, warning = self.validate_host(host, camera_name)
        if not is_valid:
            return None

        # Construir URL desde host + path
        path = cam.get("path", "/axis-cgi/mjpg/video.cgi?fps=10")

        # Si host ya tiene http://, usarlo directo
        if host.startswith("http://") or host.startswith("https://"):
            url = f"{host}{path}"
        else:
            url = f"http://{host}{path}"

        return {
            "type": "mjpeg",
            "url": url,
            "username": cam.get("username", ""),
            "password": cam.get("password", ""),
            "fps_target": cam.get("fps_target", 10),
            "timeout_s": cam.get("timeout_s", 5.0),
            "reconnect_s": cam.get("reconnect_s", 2.0)
        }

    def set_camera_source_config(self, camera_name: str, config: Dict[str, Any]):
        """
        Establece configuración de fuente de cámara.
        Guarda en formato nuevo ("cameras").

        Args:
            camera_name: Nombre de cámara ("haze", "dj", "artist")
            config: Configuración de fuente
        """
        if "cameras" not in self.data:
            self.data["cameras"] = {}

        self.data["cameras"][camera_name] = config
        self.save()
        print(f"[VisionConfig] Camera {camera_name} config updated: type={config.get('type', 'unknown')}")

    def get_all_camera_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene configuración de todas las cámaras.

        Returns:
            dict: {camera_name: config} para haze, dj, artist
        """
        return {
            "haze": self.get_camera_source_config("haze"),
            "dj": self.get_camera_source_config("dj"),
            "artist": self.get_camera_source_config("artist")
        }

    def has_new_camera_format(self) -> bool:
        """
        Verifica si la config usa el formato nuevo ("cameras").

        Returns:
            bool: True si usa formato nuevo
        """
        return "cameras" in self.data

    def migrate_to_new_camera_format(self):
        """
        DEPRECATED: USB was removed. This creates MJPEG defaults if needed.
        """
        if "cameras" in self.data:
            print("[VisionConfig] Ya tiene formato nuevo, no se migra")
            return

        print("[VisionConfig] Creando estructura MJPEG (USB removed)...")
        self.data["cameras"] = self._get_default_cameras()
        self.save()
        print("[VisionConfig] Migración completada (MJPEG defaults)")

    # ===== DEFAULTS =====

    def _get_defaults(self) -> Dict[str, Any]:
        """
        Retorna configuración por defecto.
        Usa estructura v6.8 con vision.ip_only y cameras MJPEG.

        Returns:
            dict: Configuración inicial completa
        """
        return {
            "vision": {
                "enabled": True,
                "ip_only": True
            },
            "cameras": self._get_default_cameras(),
            "haze": {
                "enabled": True,
                "cooldown_min": 60,
                "cooldown_max": 300,
                "fire_duration": 3.0,
                "threshold_low": 30,
                "threshold_med": 50,
                "threshold_high": 70,
                "baseline_frames": 30,
                "smooth_factor": 0.2,
                "target_density": "LOW"
            },
            "dj": {
                "enabled": False,
                "zones_count": 1,
                "zones": [
                    {"id": 1, "x": 100, "y": 100, "width": 200, "height": 200}
                ],
                "disappear_delay": 2.0
            },
            "tracking": {
                "enabled": False,
                "zones_horizontal": 8,
                "cooldown": 0.5,
                "smoothing": 3
            },
            "calibration": {
                "haze_baseline": 0.0,
                "last_calibration": None
            }
        }

    def reset_to_defaults(self):
        """Resetea configuración a valores por defecto y guarda."""
        self.data = self._get_defaults()
        self.save()
        print("[VisionConfig] Configuración reseteada a defaults")
