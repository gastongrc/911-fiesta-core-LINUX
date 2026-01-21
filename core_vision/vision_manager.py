"""
VisionManager PRO - Phase 6.11 + V9 Artist
Manager centralizado del Vision System PRO
Coordina: VisionConfig, VisionState, HazeDetector, DJDetector, ArtistDetector, CameraLoop
Soporta: IP cameras (MJPEG Axis + RTSP H.264) - USB REMOVED
Integración con CueEngine para disparar cues

V9 Artist: ArtistTracker replaced with ArtistDetector (YOLO-based, 8 zones, non-blocking)
Phase 6.11: Soporte dual MJPEG + RTSP con baja latencia (queue maxsize=1, frame drops)
"""
import threading
import hashlib
import json
from typing import Optional, Callable, Any, Dict
from .vision_config import VisionConfig
from .vision_state import VisionState
from .camera_haze import HazeDetector
from .dj_detector import DJDetector  # V9 DJ detector
from .artist_detector import ArtistDetector  # V9 Artist detector (replaces ArtistTracker)
from .camera_loop import CameraLoop
from .camera_source import CameraSource, create_source_from_config


class VisionManager:
    """
    Manager PRO centralizado del Vision System.

    Responsabilidades:
    - Inicializar todos los componentes
    - Gestionar ciclo de vida (start/stop/restart)
    - Proporcionar interfaz unificada para main.py
    - Coordinar VisionConfig, VisionState, detectores, CameraLoop
    - Integración con CueEngine para haze fire

    Funciones obligatorias:
    - start()
    - stop()
    - restart()
    - restart_camera()
    - set_camera_index(int)
    - enable_module(name, bool)
    - get_state()
    - load_config()
    - save_config()
    - set_ui_callback(callback)
    """

    def __init__(self, cue_engine=None, calendar_manager=None):
        """
        Inicializa el VisionManager y todos sus componentes.

        Args:
            cue_engine (CueEngine, optional): Motor de cues para integración
            calendar_manager (CalendarManager, optional): Calendario para permisos
        """
        print("[VisionManager] Inicializando Vision System PRO...")

        # Lock para evitar llamadas reentrantes a apply_camera_config
        self._apply_lock = threading.Lock()
        self._last_config_hash: Optional[str] = None

        # Componentes del sistema
        self.config = VisionConfig()
        self.vision_state = VisionState()

        # ✅ VISION PRO v2: Cargar zonas desde config
        self.zones = self.config.data.get("zones", {
            "dshotkey_center": [0.42, 0.28, 0.58, 0.70],
            "dancer_left": [0.10, 0.28, 0.38, 0.70],
            "dancer_right": [0.62, 0.28, 0.90, 0.70]
        })

        # Detectores (sin CueEngine inicialmente)
        self.haze_detector = HazeDetector(self.config, self.vision_state, cue_engine=None)
        self.dj_detector = DJDetector(self.config, self.vision_state, cue_engine=None)
        # V9: ArtistDetector replaces ArtistTracker (YOLO-based, 8 zones, non-blocking)
        self.artist_detector = ArtistDetector(self.config, self.vision_state, cue_engine=None)
        # Legacy alias for backward compatibility
        self.artist_tracker = self.artist_detector

        # MULTICÁMARA v6.10: 3 CameraLoops con MJPEGSource (IP only, USB removed)
        self._ip_only = True  # Always true (USB removed)
        print("[VisionManager] Modo: MJPEG only (USB removed)")

        # Crear sources desde configuración
        source_haze = self._create_camera_source("haze")
        source_dj = self._create_camera_source("dj")
        source_artist = self._create_camera_source("artist")

        self.camera_loop_haze = CameraLoop(
            self.config,
            self.vision_state,
            haze_detector=self.haze_detector,
            dj_detector=None,
            artist_tracker=None,
            source=source_haze,
            camera_name="haze"
        )

        self.camera_loop_dj = CameraLoop(
            self.config,
            self.vision_state,
            haze_detector=None,
            dj_detector=self.dj_detector,
            artist_tracker=None,
            source=source_dj,
            camera_name="dj"
        )

        self.camera_loop_artist = CameraLoop(
            self.config,
            self.vision_state,
            haze_detector=None,
            dj_detector=None,
            artist_tracker=self.artist_detector,  # V9: Using ArtistDetector
            source=source_artist,
            camera_name="artist"
        )

        # Mantener referencia a camera_loop para compatibilidad (apunta a haze)
        self.camera_loop = self.camera_loop_haze

        # CueEngine (puede ser None al inicio)
        self.cue_engine = cue_engine
        if cue_engine:
            self._connect_cue_engine(cue_engine)

        # Estado del manager
        self.running = False

        # FIX 4: Modo calendario - control de Artist Tracker
        # Solo disponible si calendario habilita SHOW/ARTISTA
        # Valores: "ARTISTA", "TEATRO", "BOLICHE", "OFF"
        self.mode_calendar = "OFF"  # Default OFF hasta integración con calendario
        self.mode_show_artist = False  # True solo si mode_calendar == "ARTISTA"

        # Calendar integration (passive permission gating)
        self._calendar = calendar_manager

        print("[VisionManager] Inicializado correctamente")

    def _connect_cue_engine(self, cue_engine):
        """
        Conecta el CueEngine a todos los detectores (legacy).

        Args:
            cue_engine: Instancia de CueEngine
        """
        self.cue_engine = cue_engine
        self.haze_detector.set_cue_engine(cue_engine)
        self.dj_detector.set_cue_engine(cue_engine)
        self.artist_detector.set_cue_engine(cue_engine)
        print("[VisionManager] CueEngine conectado a todos los detectores (legacy)")

    def set_family_manager(self, family_manager):
        """
        Conecta el FamilyManager a todos los detectores.
        Permite que cada detector dispare cues via el mapa canónico.

        Args:
            family_manager: Instancia de FamilyManager (desde SystemBridge)
        """
        self.haze_detector.set_family_manager(family_manager)
        self.dj_detector.set_family_manager(family_manager)
        self.artist_detector.set_family_manager(family_manager)
        print("[VisionManager] FamilyManager conectado a todos los detectores (canonical cues)")

    def _create_camera_source(self, camera_name: str) -> Optional[CameraSource]:
        """
        Crea CameraSource (MJPEGSource) desde configuración.

        Args:
            camera_name: Nombre de cámara ("haze", "dj", "artist")

        Returns:
            CameraSource: Instancia de MJPEGSource, o None si no configurada
        """
        try:
            # Obtener datos crudos de config para logging
            cam_data = self.config.data.get("cameras", {}).get(camera_name, {})
            host = cam_data.get("host", "0.0.0.0")
            enabled = cam_data.get("enabled", False)
            configured = self.config.is_camera_configured(camera_name)

            # Intentar obtener config para crear source
            source_config = self.config.get_camera_source_config(camera_name)

            # Si config es None, la cámara no está configurada o habilitada
            if source_config is None:
                reason = "not configured" if not configured else "disabled"
                print(f"[Vision] camera {camera_name} -> {reason} (host={host} enabled={enabled} configured={configured})")
                return None

            source = create_source_from_config(source_config)
            url = source_config.get("url", "")
            print(f"[Vision] camera {camera_name} -> type=mjpeg url={url} enabled={enabled} configured={configured}")

            return source

        except Exception as e:
            print(f"[Vision] camera {camera_name} -> ERROR: {e}")
            return None

    def _get_cameras_config_hash(self, camera_names: list) -> str:
        """Calcula hash de la config de cámaras para detectar cambios."""
        config_data = {}
        for cam_name in camera_names:
            cam_config = self.config.data.get("cameras", {}).get(cam_name, {})
            config_data[cam_name] = cam_config
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    def apply_camera_config(self, camera_name: str = None, force: bool = False):
        """
        Aplica configuración de cámara(s) en runtime.
        Recrea sources y reconecta loops según config actual.

        LIFECYCLE: STOP_OLD -> CREATE_NEW -> START_NEW (nunca al revés)

        Args:
            camera_name: Nombre de cámara específica, o None para todas
            force: Si True, forzar recreación aunque config no haya cambiado
        """
        # Intentar adquirir lock (no bloqueante para evitar deadlock)
        if not self._apply_lock.acquire(blocking=False):
            print("[VisionManager] apply_camera_config SKIPPED (already running)")
            return

        try:
            print(f"[VisionManager] === APPLY_CAMERA_CONFIG START ===")
            print(f"[VisionManager] Active threads before: {threading.active_count()}")

            cameras_to_update = [camera_name] if camera_name else ["haze", "dj", "artist"]

            # Check if config actually changed
            new_hash = self._get_cameras_config_hash(cameras_to_update)
            if not force and self._last_config_hash == new_hash:
                print(f"[VisionManager] Config unchanged (hash={new_hash[:8]}), skipping recreate")
                print(f"[VisionManager] === APPLY_CAMERA_CONFIG END (no-op) ===")
                return

            self._last_config_hash = new_hash
            print(f"[VisionManager] Config hash: {new_hash[:8]}")

            self._do_apply_camera_config(cameras_to_update)

        finally:
            self._apply_lock.release()

    def _do_apply_camera_config(self, cameras_to_update: list):
        """Internal implementation of apply_camera_config."""
        # Refrescar flag ip_only desde config
        self._ip_only = self.config.is_ip_only()
        print(f"[VisionManager] ip_only={self._ip_only}")

        # Obtener mapa de loops
        loop_map = {
            "haze": self.camera_loop_haze,
            "dj": self.camera_loop_dj,
            "artist": self.camera_loop_artist
        }

        # FASE 1: STOP todas las sources existentes PRIMERO
        print(f"[VisionManager] PHASE 1: STOPPING existing sources...")
        for cam_name in cameras_to_update:
            loop = loop_map.get(cam_name)
            if loop and loop.source:
                print(f"[VisionManager] {cam_name} STOPPING source...")
                loop.source.stop()
                loop.source = None
                loop.has_valid_source = False
                print(f"[VisionManager] {cam_name} STOPPED")

        print(f"[VisionManager] Active threads after stop: {threading.active_count()}")

        # FASE 2: CREATE nuevas sources
        print(f"[VisionManager] PHASE 2: CREATING new sources...")
        for cam_name in cameras_to_update:
            cam_config = self.config.data.get("cameras", {}).get(cam_name, {})
            cam_type = cam_config.get("type", "mjpeg")
            enabled = cam_config.get("enabled", False)
            host = cam_config.get("host", "0.0.0.0")
            configured = self.config.is_camera_configured(cam_name)

            print(f"[VisionManager] {cam_name}: type={cam_type} host={host} enabled={enabled} configured={configured}")

            loop = loop_map.get(cam_name)
            if not loop:
                continue

            # Actualizar flag ip_only en el loop
            loop.ip_only = self._ip_only

            # Solo crear source si está configurada Y habilitada
            if not configured or not enabled:
                print(f"[VisionManager] {cam_name} -> SKIPPED (not configured or disabled)")
                continue

            # Crear nueva source
            new_source = self._create_camera_source(cam_name)

            if new_source:
                # Asignar nueva source al loop (set_source ya no necesita stop porque lo hicimos arriba)
                loop.source = new_source
                loop._source_type = new_source.get_info().get("type", "custom")
                loop.has_valid_source = True
                print(f"[VisionManager] {cam_name} -> source CREATED")
            else:
                print(f"[VisionManager] {cam_name} -> source creation FAILED")

        print(f"[VisionManager] Active threads after create: {threading.active_count()}")
        print(f"[VisionManager] === APPLY_CAMERA_CONFIG END ===")

    def get_camera_status(self, camera_name: str) -> Dict[str, Any]:
        """
        Obtiene estado actual de una cámara con métricas.
        Phase 6.11: Incluye métricas de latencia (drops, decode_ms, queue_len).

        Args:
            camera_name: Nombre de cámara

        Returns:
            dict: Estado con configured, enabled, connected, fps, metrics, etc.
        """
        cam_config = self.config.data.get("cameras", {}).get(camera_name, {})

        loop_map = {
            "haze": self.camera_loop_haze,
            "dj": self.camera_loop_dj,
            "artist": self.camera_loop_artist
        }
        loop = loop_map.get(camera_name)

        configured = self.config.is_camera_configured(camera_name)
        enabled = cam_config.get("enabled", False)
        connected = False
        fps = 0.0
        source_info = {}

        if loop and loop.source:
            connected = loop.source.is_opened()
            fps = loop.source.get_fps()
            source_info = loop.source.get_info()

        # Determinar endpoint según tipo
        cam_type = cam_config.get("type", "mjpeg")
        if cam_type == "rtsp" or cam_config.get("url_main") or cam_config.get("url_sub"):
            endpoint = cam_config.get("url_sub") or cam_config.get("url_main") or "N/A"
        else:
            endpoint = cam_config.get("host", "0.0.0.0")

        return {
            "name": camera_name,
            "type": source_info.get("type", cam_type),
            "endpoint": endpoint,
            "configured": configured,
            "enabled": enabled,
            "connected": connected,
            "fps": fps,
            # Phase 6.11 metrics
            "fps_read": source_info.get("fps_read", 0.0),
            "drops": source_info.get("drops", 0),
            "decode_ms": source_info.get("decode_ms", 0.0),
            "queue_len": source_info.get("queue_len", 0),
            "stall_detected": source_info.get("stall_detected", False),
        }

    def get_all_cameras_metrics(self) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene métricas de todas las cámaras configuradas.
        Phase 6.11: Endpoint unificado para monitoreo de latencia.

        Returns:
            dict: {camera_name: metrics_dict} para todas las cámaras
        """
        metrics = {}
        for cam_name in ["haze", "dj", "artist"]:
            metrics[cam_name] = self.get_camera_status(cam_name)

        # Log resumen si hay cámaras activas
        active = [m for m in metrics.values() if m.get("connected")]
        if active:
            total_drops = sum(m.get("drops", 0) for m in active)
            avg_fps = sum(m.get("fps_read", 0) for m in active) / len(active) if active else 0
            print(f"[VisionManager] Cameras active={len(active)} avg_fps={avg_fps:.1f} total_drops={total_drops}")

        return metrics

    def _is_permitted(self, key: str) -> bool:
        """
        Consulta si una acción está permitida por el calendario.
        Si no hay calendario conectado, retorna True (fail-safe).

        Args:
            key: Nombre del permiso (cameras, haze_detection, artist_tracking, etc.)

        Returns:
            bool: True si está permitido, False si está bloqueado
        """
        if self._calendar is None:
            return True  # Sin calendario = todo permitido
        try:
            permissions = self._calendar.get_permissions()
            return permissions.get(key, True)  # Default True = fail-safe
        except Exception:
            return True  # Error = permitir (fail-safe)

    def set_calendar_manager(self, calendar_manager) -> None:
        """
        Conecta un CalendarManager para control de permisos.

        Args:
            calendar_manager: Instancia de CalendarManager
        """
        self._calendar = calendar_manager
        print("[VisionManager] CalendarManager conectado para gating de permisos")

    def _point_in_zone(self, x, y, zone):
        """
        ✅ VISION PRO v2: Verifica si un punto está dentro de una zona.

        Args:
            x: Coordenada X normalizada (0-1)
            y: Coordenada Y normalizada (0-1)
            zone: Lista [x1, y1, x2, y2]

        Returns:
            bool: True si el punto está dentro de la zona
        """
        x1, y1, x2, y2 = zone
        return x1 <= x <= x2 and y1 <= y <= y2

    # ===== LIFECYCLE MANAGEMENT =====

    # NOTE: validate_camera_indices/_fix_camera_index_collision REMOVED (USB removed in Phase 6.10)

    def start(self):
        """Arranca el sistema de visión (todos los CameraLoops)."""
        if self.running:
            print("[VisionManager] Ya está corriendo")
            return

        # GATING: Verificar permiso de cámaras
        if not self._is_permitted("cameras"):
            print("[VisionManager] Cámaras deshabilitadas por calendario - no iniciando")
            return

        try:
            print("[VisionManager] Iniciando 3 CameraLoops (MJPEG only)...")
            self.camera_loop_haze.start()
            self.camera_loop_dj.start()
            self.camera_loop_artist.start()
            self.running = True
            print("[VisionManager] Iniciado correctamente (3 cámaras MJPEG)")
        except Exception as e:
            print(f"[VisionManager] Error iniciando: {e}")
            self.running = False

    def stop(self):
        """Detiene el sistema de visión de manera segura (todos los loops y sources)."""
        import threading

        if not self.running:
            return

        print(f"[VisionManager] === STOP START ===")
        print(f"[VisionManager] Active threads before stop: {threading.active_count()}")

        try:
            # FASE 1: Detener todos los sources PRIMERO (para interrumpir threads MJPEG)
            print("[VisionManager] PHASE 1: Stopping sources...")
            for cam_name, loop in [("haze", self.camera_loop_haze), ("dj", self.camera_loop_dj), ("artist", self.camera_loop_artist)]:
                if loop and loop.source:
                    print(f"[VisionManager] {cam_name} stopping source...")
                    loop.source.stop()
                    loop.source = None
                    loop.has_valid_source = False

            # FASE 2: Detener los CameraLoops
            print("[VisionManager] PHASE 2: Stopping CameraLoops...")
            self.camera_loop_haze.stop()
            self.camera_loop_dj.stop()
            self.camera_loop_artist.stop()

            self.running = False
            print(f"[VisionManager] Active threads after stop: {threading.active_count()}")
            print("[VisionManager] === STOP COMPLETE ===")

        except Exception as e:
            print(f"[VisionManager] Error deteniendo: {e}")
            self.running = False

    def restart(self):
        """Reinicia el sistema completo."""
        print("[VisionManager] Reiniciando sistema...")
        was_running = self.running
        if was_running:
            self.stop()
        if was_running:
            self.start()

    def restart_camera(self):
        """Reinicia todas las cámaras."""
        print("[VisionManager] Reiniciando cámaras...")
        self.camera_loop_haze.restart()
        self.camera_loop_dj.restart()
        self.camera_loop_artist.restart()

    # ===== CONFIGURATION =====

    # NOTE: set_camera_index/set_camera_*_index REMOVED (USB removed in Phase 6.10)
    # Use apply_camera_config() with config changes instead

    def enable_module(self, name: str, enabled: bool):
        """
        Habilita/deshabilita un módulo específico.

        V9.1 FIX: Soporta nombres canónicos del SystemBridge (calendar integration).

        Args:
            name: Nombre del módulo
                  - "haze" o "vision_haze" -> HazeDetector
                  - "dj" o "dj_cues" o "dj_detection" -> DJDetector
                  - "tracking" o "artista_cues" -> ArtistTracker
            enabled: True para habilitar, False para deshabilitar
        """
        # V9.1 FIX: Mapeo de nombres alternativos del calendario
        name_aliases = {
            "vision_haze": "haze",
            "dj_cues": "dj",
            "dj_detection": "dj",
            "artista_cues": "tracking",
            "vision_artista": "tracking",
            "tracking_cam": "tracking",
        }
        canonical_name = name_aliases.get(name, name)

        module_map = {
            "haze": (self.haze_detector, self.vision_state.set_haze_enabled),
            "dj": (self.dj_detector, self.vision_state.set_dj_enabled),
            "tracking": (self.artist_detector, self.vision_state.set_tracking_enabled),
            "artist": (self.artist_detector, self.vision_state.set_tracking_enabled),
        }

        if canonical_name not in module_map:
            print(f"[VisionManager] Módulo '{name}' (canonical='{canonical_name}') no reconocido")
            return

        detector, state_setter = module_map[canonical_name]

        try:
            if hasattr(detector, 'set_enabled'):
                detector.set_enabled(enabled)
            else:
                state_setter(enabled)

            print(f"[VisionManager] Módulo '{canonical_name}' {'habilitado' if enabled else 'deshabilitado'} (via {name})")
        except Exception as e:
            print(f"[VisionManager] Error habilitando módulo '{canonical_name}': {e}")

    def load_config(self) -> Dict[str, Any]:
        """
        Carga configuración desde archivo JSON.

        Returns:
            dict: Configuración completa
        """
        return self.config.load()

    def save_config(self):
        """Guarda configuración a archivo JSON."""
        self.config.save()

    # ===== STATE ACCESS =====

    def get_state(self) -> Dict[str, Any]:
        """
        Obtiene el estado completo del sistema.

        ✅ VISION PRO v2 FIX: Respeta calendario + detección robusta de bailarinas

        Returns:
            dict: Estado completo desde VisionState con dancers + respeto a calendario
        """
        try:
            state = self.vision_state.to_dict()

            # ✅ VISION PRO v2 FIX: Respeto absoluto al calendario
            if self.mode_calendar in ["ESCENA", "CLIMA", "TEATRO"]:
                # Desactivar detector de haze (guard para evitar errores)
                if hasattr(self.haze_detector, 'disable_by_mode'):
                    self.haze_detector.disable_by_mode()

                # Forzar estado deshabilitado
                if "haze" in state:
                    state["haze"]["haze_state"] = "DISABLED_BY_MODE"
                    state["haze"]["level"] = 0.0
                    state["haze"]["smooth_value"] = 0.0

                state["dancers"] = {
                    "left": False,
                    "right": False,
                    "count": 0
                }
                return state

            # ✅ VISION PRO v2 FIX: Detección robusta de bailarinas en modos normales
            # Obtener detecciones de personas del DJ detector
            detections = state.get("dj", {}).get("detections", [])

            # ✅ FIX: Filtrar solo personas con .lower() para robustez
            persons = [d for d in detections if d.get("label", "").lower() == "person"]

            dancer_left = False
            dancer_right = False

            for p in persons:
                # Calcular centro de la detección (coordenadas normalizadas 0-1)
                cx = (p.get("x1", 0) + p.get("x2", 0)) / 2
                cy = (p.get("y1", 0) + p.get("y2", 0)) / 2

                # Verificar si está en zona bailarina izquierda
                if "dancer_left" in self.zones:
                    if self._point_in_zone(cx, cy, self.zones["dancer_left"]):
                        dancer_left = True

                # Verificar si está en zona bailarina derecha
                if "dancer_right" in self.zones:
                    if self._point_in_zone(cx, cy, self.zones["dancer_right"]):
                        dancer_right = True

            # Agregar información de bailarinas al estado
            state["dancers"] = {
                "left": dancer_left,
                "right": dancer_right,
                "count": int(dancer_left) + int(dancer_right)
            }

            return state

        except Exception as e:
            print(f"[VisionManager] Error obteniendo estado: {e}")
            return {
                "system": {"enabled": False, "fps": 0.0},
                "haze": {"enabled": False, "level": 0.0, "haze_state": "HAZE_LOW", "smooth_value": 0.0},
                "dj": {"enabled": False, "active_zone": None, "detections": []},
                "tracking": {"enabled": False, "zone": None},
                "dancers": {"left": False, "right": False, "count": 0}
            }

    def is_running(self) -> bool:
        """
        Verifica si el sistema está corriendo.

        Returns:
            bool: True si está corriendo
        """
        return self.running

    # ===== UI INTEGRATION =====

    def set_ui_callback(self, callback: Callable[[Any], None]):
        """
        Establece callback para enviar frames al UI (legacy).
        Por compatibilidad, establece callback solo en Haze.

        Args:
            callback: Función que recibe frame (numpy array)
        """
        self.set_ui_callback_haze(callback)
        print("[VisionManager] UI callback establecido (Haze camera - legacy)")

    def set_ui_callback_haze(self, callback: Callable[[Any], None]):
        """
        Establece callback para enviar frames de la cámara Haze al UI.

        Args:
            callback: Función que recibe frame (numpy array)
        """
        self.camera_loop_haze.set_frame_callback(callback)
        print("[VisionManager] UI callback Haze establecido")

    def set_ui_callback_dj(self, callback: Callable[[Any], None]):
        """
        Establece callback para enviar frames de la cámara DJ al UI.

        Args:
            callback: Función que recibe frame (numpy array)
        """
        self.camera_loop_dj.set_frame_callback(callback)
        print("[VisionManager] UI callback DJ establecido")

    def set_ui_callback_artist(self, callback: Callable[[Any], None]):
        """
        Establece callback para enviar frames de la cámara Artist al UI.

        Args:
            callback: Función que recibe frame (numpy array)
        """
        self.camera_loop_artist.set_frame_callback(callback)
        print("[VisionManager] UI callback Artist establecido")

    # ===== MODULE ACCESS =====

    def get_haze_detector(self) -> HazeDetector:
        """Obtiene referencia al HazeDetector."""
        return self.haze_detector

    def get_dj_detector(self) -> DJDetector:
        """Obtiene referencia al DJDetector."""
        return self.dj_detector

    def get_artist_tracker(self) -> ArtistDetector:
        """Obtiene referencia al ArtistDetector (legacy alias)."""
        return self.artist_detector

    def get_artist_detector(self) -> ArtistDetector:
        """Obtiene referencia al ArtistDetector V9."""
        return self.artist_detector

    def get_camera_loop(self) -> CameraLoop:
        """Obtiene referencia al CameraLoop."""
        return self.camera_loop

    def get_config(self) -> VisionConfig:
        """Obtiene referencia a VisionConfig."""
        return self.config

    def get_vision_state(self) -> VisionState:
        """Obtiene referencia a VisionState."""
        return self.vision_state

    # ===== ADVANCED FEATURES =====

    def calibrate_haze_baseline(self):
        """Recalibra el baseline de haze."""
        print("[VisionManager] Recalibrando baseline de haze...")
        self.haze_detector.reset_baseline()

    def set_dj_zones(self, zones):
        """
        Establece zonas de DJ.

        Args:
            zones: Lista de zonas [{id, x, y, width, height}]
        """
        self.dj_detector.set_zones(zones)

    def get_fps(self) -> float:
        """Obtiene FPS actual del sistema."""
        return self.vision_state.get_fps()

    def get_camera_index(self) -> int:
        """Obtiene índice de cámara actual."""
        return self.vision_state.get_camera_index()

    # ===== CALENDAR MODE (FIX 4) =====

    def set_calendar_mode(self, mode: str):
        """
        Establece el modo de calendario para control de Artist Detector.
        NOTE: V9 ArtistDetector no usa calendar gating, pero mantenemos API.

        Args:
            mode: Modo del calendario ("ARTISTA", "TEATRO", "BOLICHE", "OFF")
        """
        self.mode_calendar = mode
        self.mode_show_artist = (mode == "ARTISTA")

        # V9: ArtistDetector no necesita calendar gating, pero llamamos por compatibilidad
        if hasattr(self.artist_detector, 'set_mode_show_artist'):
            self.artist_detector.set_mode_show_artist(self.mode_show_artist)

        print(f"[VisionManager] Modo calendario: {mode}, mode_show_artist={self.mode_show_artist}")

    def get_calendar_mode(self) -> str:
        """Obtiene el modo de calendario actual."""
        return self.mode_calendar

    # ===== DIAGNOSTICS =====

    def get_diagnostics(self) -> Dict[str, Any]:
        """
        Obtiene diagnóstico completo del sistema.

        Returns:
            dict: Información de diagnóstico
        """
        return {
            "manager": {
                "running": self.running,
            },
            "camera": {
                "index": self.get_camera_index(),
                "fps": self.get_fps(),
                "running": self.camera_loop.is_running(),
            },
            "modules": {
                "haze": self.haze_detector.get_state(),
                "dj": self.dj_detector.get_state(),
                "artist": self.artist_detector.get_state(),
            },
            "state": self.get_state(),
        }

    # ===== ARTIST ZONES MANAGEMENT =====

    def set_artist_zones(self, zones):
        """
        Establece zonas de Artist.

        Args:
            zones: Lista de zonas [{id, x, y, width, height}]
        """
        self.artist_detector.set_zones(zones)
