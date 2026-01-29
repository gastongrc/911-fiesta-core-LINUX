"""
CameraLoop PRO - Phase 6.14
Loop de captura de cámara con procesamiento de todos los detectores
Soporta: MJPEG (IP cameras only) - USB REMOVED
Orquestador: HazeDetector → DJDetector → ArtistTracker

Phase 6.12: RTSP thread-safe reconnection
- No llama stop() en errores de lectura para RTSP
- Deja que RTSPSource maneje reconexión internamente
- Previene crash de FFmpeg async_lock

Phase 6.14: Deterministic restart on start() if already running
- start() now calls restart() instead of returning silently
- Prevents "ghost" camera states
"""
import time
import threading
from typing import Optional, Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .camera_source import CameraSource


class CameraLoop:
    """
    Loop PRO de captura de cámara con procesamiento en tiempo real.
    Soporta fuentes MJPEG (IP cameras via CameraSource). USB REMOVED.

    Responsabilidades:
    - Captura continua desde CameraSource (MJPEG only)
    - Control ON/OFF real
    - Llamar detectores en orden correcto:
      1. HazeDetector
      2. DJDetector
      3. ArtistTracker
    - Enviar frames al UI via callback
    - Manejo de cámara inexistente
    - Evitar lag (time.time(), sleep mínimo)
    - Sin crashes si un módulo devuelve None

    Integración:
    - Thread independiente para no bloquear main thread
    - Actualiza VisionState de manera thread-safe
    - Reconexión automática en caso de fallo
    """

    def __init__(self, config, vision_state, haze_detector=None, dj_detector=None, artist_tracker=None, camera_index=None, source: "Optional[CameraSource]" = None, ip_only: bool = True, camera_name: str = "unknown"):
        """
        Inicializa el loop de cámara.

        Args:
            config (VisionConfig): Configuración del sistema
            vision_state (VisionState): Estado compartido
            haze_detector (HazeDetector, optional): Detector de haze
            dj_detector (DJDetector, optional): Detector de DJ
            artist_tracker (ArtistTracker, optional): Tracker de artista
            camera_index (int, optional): DEPRECATED - ignored (USB removed)
            source (CameraSource, optional): Fuente de cámara MJPEG. Si None, no inicia.
            ip_only (bool): DEPRECATED - always True (USB removed)
            camera_name (str): Nombre de la cámara para logs ("haze", "dj", "artist")
        """
        self.config = config
        self.vision_state = vision_state
        self.haze_detector = haze_detector
        self.dj_detector = dj_detector
        self.artist_tracker = artist_tracker
        self.camera_name = camera_name

        # IP-only mode always enforced (USB removed)
        self.ip_only = True

        # CameraSource (MJPEG only)
        self.source: "Optional[CameraSource]" = source
        self._source_type = "mjpeg" if source else "no_source"

        # Estado interno
        self.running = False
        self.thread = None

        # FPS measurement
        self.frame_count = 0
        self.fps_start_time = None
        self.current_fps = 0.0

        # Callbacks para UI
        self.frame_callback: Optional[Callable[[Any], None]] = None

        # Reconexión automática
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 2.0

        # Flag para indicar si el loop tiene fuente válida
        self.has_valid_source = source is not None

        if source:
            source_info = self.source.get_info()
            print(f"[CameraLoop] {camera_name} inicializado -> type={source_info.get('type', 'unknown')}")
        else:
            print(f"[CameraLoop] {camera_name} inicializado -> NO SOURCE (waiting for config)")

    def start(self, force_restart: bool = False):
        """
        Arranca el thread de captura.

        Phase 6.14: If already running, performs restart instead of returning silently.
        This ensures deterministic behavior and prevents ghost states.

        Args:
            force_restart: If True, always restart even if running (default False for backwards compat)
        """
        if self.running:
            # Phase 6.14: Restart instead of silent return
            print(f"[CameraLoop] {self.camera_name} already running - performing restart for clean state")
            self.restart()
            return

        # Sin source válido, no iniciar
        if not self.has_valid_source:
            print(f"[CameraLoop] {self.camera_name} NOT STARTED (no source configured)")
            return

        self.running = True
        self.vision_state.set_system_enabled(True)
        self.thread = threading.Thread(target=self._loop, daemon=True, name=f"CameraLoop-{self.camera_name}")
        self.thread.start()
        print(f"[CameraLoop] {self.camera_name} thread iniciado")

    def stop(self):
        """Detiene el thread de manera segura."""
        if not self.running:
            return

        print(f"[CameraLoop] {self.camera_name} deteniendo...")
        self.running = False
        self.vision_state.set_system_enabled(False)

        if self.thread:
            self.thread.join(timeout=5.0)

        # Cerrar fuente MJPEG
        if self.source:
            self.source.stop()

        print(f"[CameraLoop] {self.camera_name} detenido")

    def restart(self):
        """Reinicia el loop."""
        print("[CameraLoop] Reiniciando...")
        was_running = self.running
        if was_running:
            self.stop()
            time.sleep(0.5)
        if was_running:
            self.start()

    def set_camera_index(self, index: int):
        """
        DEPRECATED: USB was removed. This method is now a no-op.

        Args:
            index: Ignored
        """
        print(f"[CameraLoop] set_camera_index DEPRECATED (USB removed) - ignored index={index}")

    def set_source(self, source: "CameraSource"):
        """
        Establece una nueva fuente de cámara MJPEG.
        Si el loop está corriendo, fuerza reconexión.

        Args:
            source: Nueva fuente MJPEGSource
        """
        # Cerrar fuente anterior
        if self.source:
            self.source.stop()

        self.source = source
        self._source_type = source.get_info().get("type", "mjpeg")
        self.has_valid_source = True
        print(f"[CameraLoop] Nueva fuente establecida: {self._source_type}")

    def set_frame_callback(self, callback: Callable[[Any], None]):
        """
        Establece callback para enviar frames al UI.

        Args:
            callback: Función que recibe frame (numpy array)
        """
        self.frame_callback = callback
        print("[CameraLoop] Frame callback establecido")

    def _loop(self):
        """
        Loop principal de captura.
        Captura frames → procesa detectores → actualiza VisionState → callback UI.
        """
        retry_count = 0

        while self.running:
            # Abrir fuente si no está abierta
            if not self._is_source_opened():
                if not self._open_camera():
                    retry_count += 1
                    if retry_count >= self.max_reconnect_attempts:
                        print(f"[CameraLoop] Error: no se pudo abrir fuente después de {self.max_reconnect_attempts} intentos")
                        # Seguir intentando en lugar de detener
                        retry_count = 0
                    print(f"[CameraLoop] Reintentando en {self.reconnect_delay}s... ({retry_count}/{self.max_reconnect_attempts})")
                    time.sleep(self.reconnect_delay)
                    continue
                else:
                    retry_count = 0

            # Leer frame (desde CameraSource o USB fallback)
            ret, frame = self._read_frame()
            frame_ts = time.time()  # V9.1: Timestamp for frame age calculation

            if not ret or frame is None:
                # Phase 6.12: Para fuentes RTSP, NO llamar stop() en errores de lectura
                # Esto causa crash de async_lock en FFmpeg
                # En su lugar, dejar que el source maneje la reconexión internamente
                if self.source and hasattr(self.source, 'supports_reconnect') and self.source.supports_reconnect():
                    # RTSP source maneja reconexión internamente
                    # Solo esperar un poco y reintentar lectura
                    time.sleep(0.1)
                    continue
                else:
                    # MJPEG u otras fuentes: comportamiento anterior
                    print("[CameraLoop] Error leyendo frame, reconectando...")
                    self._close_source()
                    time.sleep(0.5)
                    continue

            # FPS measurement
            self._update_fps()

            # Procesar frame con detectores (orden: Haze → DJ → Tracking)
            try:
                # 1. HazeDetector (siempre procesa si está habilitado)
                if self.haze_detector and self.vision_state.haze_enabled:
                    try:
                        self.haze_detector.process_frame(frame)
                    except Exception as e:
                        print(f"[CameraLoop] Error en HazeDetector: {e}")

                # 2. DJDetector (solo si está habilitado)
                # V9.1: Pass frame_ts for frame age tracking
                if self.dj_detector and self.vision_state.dj_enabled:
                    try:
                        self.dj_detector.process_frame(frame, frame_ts=frame_ts)
                    except Exception as e:
                        print(f"[CameraLoop] Error en DJDetector: {e}")

                # 3. ArtistTracker (solo si está habilitado)
                # V9.1: Pass frame_ts for frame age tracking
                if self.artist_tracker and self.vision_state.tracking_enabled:
                    try:
                        self.artist_tracker.process_frame(frame, frame_ts=frame_ts)
                    except Exception as e:
                        print(f"[CameraLoop] Error en ArtistTracker: {e}")

            except Exception as e:
                print(f"[CameraLoop] Error procesando frame: {e}")

            # Actualizar FPS en VisionState
            self.vision_state.set_fps(self.current_fps)

            # Callback para UI (enviar frame)
            if self.frame_callback:
                try:
                    self.frame_callback(frame)
                except Exception as e:
                    print(f"[CameraLoop] Error en frame callback: {e}")

            # Sleep mínimo para evitar lag (30 FPS target)
            # Usar sleep muy corto para no perder frames
            time.sleep(0.001)

        # Cleanup al salir
        self._close_source()

        print("[CameraLoop] Thread finalizado")

    def _is_source_opened(self) -> bool:
        """Verifica si la fuente de cámara está abierta."""
        if self.source:
            return self.source.is_opened()
        return False

    def _read_frame(self):
        """Lee un frame de la fuente activa."""
        if self.source:
            return self.source.read()
        return False, None

    def _close_source(self):
        """Cierra la fuente de cámara activa."""
        if self.source:
            self.source.stop()

    def _open_camera(self) -> bool:
        """
        Abre la fuente de cámara MJPEG.
        USB fue removido - solo soporta MJPEGSource.

        Returns:
            bool: True si se abrió exitosamente
        """
        try:
            # Solo MJPEGSource soportado
            if not self.source:
                print(f"[CameraLoop] {self.camera_name} ERROR: no source configured")
                return False

            source_info = self.source.get_info()
            source_type = source_info.get("type", "unknown")
            url = source_info.get("url", "N/A")
            print(f"[CameraLoop] {self.camera_name} abriendo fuente type={source_type} url={url}")

            if self.source.start():
                print(f"[CameraLoop] {self.camera_name} fuente {source_type} abierta correctamente")
                self.frame_count = 0
                self.fps_start_time = time.time()
                return True
            else:
                print(f"[CameraLoop] {self.camera_name} ERROR: no se pudo abrir fuente {source_type}")
                return False

        except Exception as e:
            print(f"[CameraLoop] {self.camera_name} EXCEPTION abriendo cámara: {e}")
            return False

    def _update_fps(self):
        """Actualiza el contador de FPS real."""
        self.frame_count += 1

        if self.fps_start_time is None:
            self.fps_start_time = time.time()

        elapsed = time.time() - self.fps_start_time

        # Calcular FPS cada segundo
        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_start_time = time.time()

    def is_running(self) -> bool:
        """Verifica si el loop está corriendo."""
        return self.running

    def get_fps(self) -> float:
        """Obtiene FPS actual."""
        return self.current_fps
