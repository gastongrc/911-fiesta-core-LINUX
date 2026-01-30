"""
CameraSource - Abstracción de fuentes de cámara para 911 Fiesta
Soporta: MJPEG (HTTP streaming) + RTSP (H.264 via PyAV/FFmpeg)

Phase 6.7 - IP Camera Support
Phase 6.9 - Robust stop mechanism for MJPEGSource
Phase 6.10 - USB REMOVED, MJPEG only (ip_only mode enforced)
Phase 6.11 - RTSP support + unified low-latency buffer (queue maxsize=1)
Phase 6.13 - PyAV-based RTSP with VMS-grade low latency
"""
import cv2
import numpy as np
import threading
import queue
import time
import requests
from requests.exceptions import ReadTimeout, ChunkedEncodingError, ConnectionError as ReqConnectionError
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any

# PyAV import with fallback
try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False
    print("[CameraSource] WARNING: PyAV not available, RTSP will use OpenCV fallback")


class CameraSource(ABC):
    """
    Clase base abstracta para fuentes de cámara.
    Todas las fuentes deben entregar frames BGR numpy array.
    """

    @abstractmethod
    def start(self) -> bool:
        """
        Inicia la captura de la fuente.

        Returns:
            bool: True si se inició correctamente
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Detiene la captura y libera recursos."""
        pass

    @abstractmethod
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Lee el siguiente frame.

        Returns:
            tuple: (success, frame) donde frame es BGR numpy array o None
        """
        pass

    @abstractmethod
    def is_opened(self) -> bool:
        """
        Verifica si la fuente está abierta y funcionando.

        Returns:
            bool: True si está abierta
        """
        pass

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """
        Obtiene información de la fuente.

        Returns:
            dict: Información de la fuente (type, resolution, fps, etc.)
        """
        pass

    def get_fps(self) -> float:
        """
        Obtiene FPS estimado/real de la fuente.

        Returns:
            float: FPS actual o 0.0 si no disponible
        """
        return 0.0


class MJPEGSource(CameraSource):
    """
    Fuente de cámara IP MJPEG usando HTTP streaming.
    Optimizado para cámaras Axis con baja latencia.

    El stream MJPEG es multipart/x-mixed-replace con frames JPEG.
    Cada frame está delimitado por markers JPEG (FFD8...FFD9).

    Phase 6.9: Robust stop mechanism
    - Uses threading.Event for clean shutdown signaling
    - Separate connect and read timeouts (read_timeout is SHORT for interruptibility)
    - Session-based requests for proper cleanup
    - Catches ReadTimeout/ChunkedEncodingError/ConnectionError for graceful exit

    Phase 6.11: Latest-frame buffer policy
    - Queue maxsize=1 with drop policy (always keep latest frame only)
    - Metrics: fps_read, drops, decode_ms

    Phase 6.14: Config-aware restart
    - get_config_signature() for config comparison
    - start() with auto-restart if config changed
    """

    # Short read timeout to ensure thread can check stop_event frequently
    READ_TIMEOUT = 1.0

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        fps_target: int = 10,
        timeout_s: float = 5.0,
        reconnect_s: float = 2.0
    ):
        """
        Inicializa fuente MJPEG.

        Args:
            url: URL del stream MJPEG (ej: http://host/axis-cgi/mjpg/video.cgi)
            username: Usuario para Basic Auth (vacío si no requiere)
            password: Password para Basic Auth
            fps_target: FPS objetivo (para info, el stream define el real)
            timeout_s: Timeout de conexión (read timeout es fijo para interruptibilidad)
            reconnect_s: Delay entre reconexiones
        """
        self.url = url
        self.username = username
        self.password = password
        self.fps_target = fps_target
        self.connect_timeout = timeout_s
        self.reconnect_s = reconnect_s

        # Estado interno - usando Event para señalización robusta
        self._stop_event = threading.Event()
        self._session: Optional[requests.Session] = None
        self._response: Optional[requests.Response] = None
        self._thread: Optional[threading.Thread] = None
        self._opened = False

        # Frame buffer - queue maxsize=1 for latest-frame-only policy
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.RLock()
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_ts: float = 0.0
        self._frame_count = 0
        self._actual_fps = 0.0
        self._fps_start_time = None

        # Metrics (Phase 6.11)
        self._drops = 0
        self._decode_ms_avg = 0.0
        self._decode_samples = 0

        # Detección de stall
        self._stall_detected = False

        # Contador de reconexiones para backoff
        self._reconnect_count = 0
        self._max_reconnect_backoff = 10.0

        # Phase 6.14: Config signature for change detection
        self._config_signature = self._compute_config_signature()

    def _compute_config_signature(self) -> str:
        """Computes a signature from config params for change detection."""
        return f"{self.url}|{self.username}|{self.password}|{self.fps_target}"

    def get_config_signature(self) -> str:
        """Returns current config signature for comparison."""
        return self._config_signature

    def start(self, new_url: str = None, new_username: str = None, new_password: str = None) -> bool:
        """
        Inicia el thread de captura MJPEG.

        Phase 6.14: If already running, checks if config changed.
        - Same config → log "Already running (same config)" and return True
        - Different config → restart with new config

        Args:
            new_url: Optional new URL (for restart detection)
            new_username: Optional new username
            new_password: Optional new password
        """
        # Build new signature if params provided
        check_url = new_url if new_url is not None else self.url
        check_user = new_username if new_username is not None else self.username
        check_pass = new_password if new_password is not None else self.password
        new_signature = f"{check_url}|{check_user}|{check_pass}|{self.fps_target}"

        if self._thread and self._thread.is_alive():
            # Check if config is the same
            if new_signature == self._config_signature:
                print(f"[MJPEGSource] Already running (same config): {self.url}")
                return True
            else:
                # Config changed - do restart
                print(f"[MJPEGSource] Config changed while running - restarting...")
                print(f"[MJPEGSource] Old: {self._config_signature[:50]}")
                print(f"[MJPEGSource] New: {new_signature[:50]}")
                self.stop()
                # Update config
                if new_url is not None:
                    self.url = new_url
                if new_username is not None:
                    self.username = new_username
                if new_password is not None:
                    self.password = new_password
                self._config_signature = new_signature

        # Validar URL antes de intentar conectar
        if not self.url or "0.0.0.0" in self.url:
            print(f"[MJPEGSource] URL inválida, no iniciando: {self.url}")
            return False

        print(f"[MJPEGSource] STARTING: {self.url}")

        # Reset state
        self._stop_event.clear()
        self._stall_detected = False
        self._reconnect_count = 0
        self._opened = False

        # Crear sesión
        self._session = requests.Session()
        if self.username:
            self._session.auth = (self.username, self.password)

        # Iniciar thread
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"MJPEGSource-{id(self)}"
        )
        self._thread.start()

        # Esperar a que conecte (max connect_timeout)
        start_wait = time.time()
        while time.time() - start_wait < self.connect_timeout:
            if self._stop_event.is_set():
                return False
            if self._opened:
                print(f"[MJPEGSource] STARTED OK: {self.url}")
                return True
            time.sleep(0.1)

        print(f"[MJPEGSource] Timeout esperando conexión inicial: {self.url}")
        return self._opened

    def stop(self) -> None:
        """
        Detiene el thread de captura de forma robusta.
        Garantiza que el thread muere en < 500ms.
        """
        print(f"[MJPEGSource] STOPPING: {self.url}")

        # 1. Señalar stop
        self._stop_event.set()

        # 2. Cerrar response para interrumpir read bloqueante
        if self._response:
            try:
                self._response.close()
            except Exception as e:
                print(f"[MJPEGSource] Error cerrando response: {e}")
            self._response = None

        # 3. Cerrar session para interrumpir cualquier operación pendiente
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                print(f"[MJPEGSource] Error cerrando session: {e}")
            self._session = None

        # 4. Join thread con timeout corto
        if self._thread:
            self._thread.join(timeout=0.5)
            if self._thread.is_alive():
                print(f"[MJPEGSource] WARNING: thread no murió en 500ms, dejando como daemon")
            self._thread = None

        self._opened = False
        print(f"[MJPEGSource] STOPPED: {self.url}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Lee el último frame disponible (NO bloqueante).

        Returns:
            tuple: (success, frame) - frame es copia del último disponible
        """
        with self._lock:
            if self._last_frame is None:
                return False, None

            # Verificar si hay stall (frame muy viejo)
            age = time.time() - self._last_frame_ts
            if age > self.connect_timeout:
                if not self._stall_detected:
                    print(f"[MJPEGSource] Stall detected: frame age={age:.1f}s")
                    self._stall_detected = True
                return False, None

            self._stall_detected = False
            return True, self._last_frame.copy()

    def is_opened(self) -> bool:
        """Verifica si la fuente está conectada."""
        return self._opened and not self._stop_event.is_set()

    def get_info(self) -> Dict[str, Any]:
        """Obtiene información de la fuente MJPEG."""
        with self._lock:
            frame_shape = self._last_frame.shape if self._last_frame is not None else None

        return {
            "type": "mjpeg",
            "url": self.url,
            "username": self.username,
            "fps_target": self.fps_target,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.READ_TIMEOUT,
            "reconnect_s": self.reconnect_s,
            "opened": self._opened,
            "fps_actual": self._actual_fps,
            "fps_read": self._actual_fps,  # Alias for unified metrics
            "frame_shape": frame_shape,
            "stall_detected": self._stall_detected,
            # Phase 6.11 metrics
            "drops": self._drops,
            "decode_ms": self._decode_ms_avg,
            "queue_len": self._frame_queue.qsize(),
        }

    def get_fps(self) -> float:
        """Obtiene FPS real medido."""
        return self._actual_fps

    def _capture_loop(self):
        """Thread principal de captura MJPEG."""
        print(f"[MJPEGSource] Thread started: {threading.current_thread().name}")

        while not self._stop_event.is_set():
            try:
                self._connect_and_stream()
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[MJPEGSource] Error en capture loop: {e}")

            # Si no se pidió stop, reconectar con backoff
            if not self._stop_event.is_set():
                self._opened = False
                self._reconnect_count += 1

                # Backoff exponencial con límite
                backoff = min(
                    self.reconnect_s * (1.5 ** min(self._reconnect_count, 5)),
                    self._max_reconnect_backoff
                )
                print(f"[MJPEGSource] Reconnecting in {backoff:.1f}s (attempt {self._reconnect_count})...")

                # Usar wait con timeout para poder ser interrumpido
                if self._stop_event.wait(timeout=backoff):
                    break  # Stop fue solicitado durante el wait

        self._opened = False
        print(f"[MJPEGSource] Thread exiting: {threading.current_thread().name}")

    def _connect_and_stream(self):
        """Conecta al stream MJPEG y procesa frames."""
        if self._stop_event.is_set():
            return

        if not self._session:
            print(f"[MJPEGSource] No session, aborting connect")
            return

        print(f"[MJPEGSource] Connecting to {self.url}...")

        try:
            # CRITICAL: Usar timeout tuple (connect_timeout, read_timeout)
            # read_timeout CORTO permite que el thread pueda verificar stop_event
            self._response = self._session.get(
                self.url,
                stream=True,
                timeout=(self.connect_timeout, self.READ_TIMEOUT)
            )
            self._response.raise_for_status()
        except (ReadTimeout, ReqConnectionError) as e:
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Connection timeout/error: {e}")
            return
        except requests.exceptions.RequestException as e:
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Connection failed: {e}")
            return

        content_type = self._response.headers.get('Content-Type', '')
        print(f"[MJPEGSource] Connected! Content-Type: {content_type}")
        self._opened = True
        self._reconnect_count = 0  # Reset backoff on successful connect

        # Buffer para acumular chunks
        buffer = b''
        jpeg_start = b'\xff\xd8'
        jpeg_end = b'\xff\xd9'

        # Reset FPS counter
        self._frame_count = 0
        self._fps_start_time = time.time()

        try:
            # iter_content puede bloquear hasta READ_TIMEOUT
            for chunk in self._response.iter_content(chunk_size=8192):
                # Check stop FIRST
                if self._stop_event.is_set():
                    break

                if not chunk:
                    continue

                buffer += chunk

                # Buscar frames JPEG completos
                while jpeg_start in buffer and jpeg_end in buffer:
                    start_idx = buffer.find(jpeg_start)
                    end_idx = buffer.find(jpeg_end, start_idx) + 2

                    if end_idx > start_idx:
                        jpeg_data = buffer[start_idx:end_idx]
                        buffer = buffer[end_idx:]

                        # Decodificar JPEG a BGR con medición de tiempo
                        decode_start = time.perf_counter()
                        img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        decode_ms = (time.perf_counter() - decode_start) * 1000

                        if frame is not None:
                            # Update decode time average (exponential moving average)
                            if self._decode_samples == 0:
                                self._decode_ms_avg = decode_ms
                            else:
                                self._decode_ms_avg = 0.9 * self._decode_ms_avg + 0.1 * decode_ms
                            self._decode_samples += 1

                            # Latest-frame-only policy: drop old frame if queue full
                            with self._lock:
                                self._last_frame = frame
                                self._last_frame_ts = time.time()

                            # Try to put in queue, drop old if full
                            try:
                                self._frame_queue.put_nowait(frame)
                            except queue.Full:
                                try:
                                    self._frame_queue.get_nowait()  # Drop old
                                    self._drops += 1
                                except queue.Empty:
                                    pass
                                try:
                                    self._frame_queue.put_nowait(frame)
                                except queue.Full:
                                    pass

                            self._update_fps()
                    else:
                        break

                # Evitar buffer overflow
                if len(buffer) > 1024 * 1024:  # 1MB max
                    last_start = buffer.rfind(jpeg_start)
                    if last_start > 0:
                        buffer = buffer[last_start:]
                    else:
                        buffer = b''

        except ReadTimeout:
            # Timeout de lectura - normal, permite verificar stop_event
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Read timeout, will retry...")

        except ChunkedEncodingError as e:
            # Conexión cerrada abruptamente (normal en stop)
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Chunked encoding error: {e}")

        except ReqConnectionError as e:
            # Error de conexión
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Connection error: {e}")

        except Exception as e:
            if not self._stop_event.is_set():
                print(f"[MJPEGSource] Stream error: {e}")

        finally:
            if self._response:
                try:
                    self._response.close()
                except:
                    pass
                self._response = None

    def _update_fps(self):
        """Actualiza el contador de FPS."""
        self._frame_count += 1

        if self._fps_start_time is None:
            self._fps_start_time = time.time()

        elapsed = time.time() - self._fps_start_time

        if elapsed >= 1.0:
            self._actual_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_start_time = time.time()


class RTSPSource(CameraSource):
    """
    Fuente de cámara RTSP usando OpenCV VideoCapture.
    Optimizado para baja latencia con H.264/H.265 streams.

    Phase 6.11: RTSP support with low-latency configuration
    - OpenCV VideoCapture with minimal buffer
    - Queue maxsize=1 with drop policy (latest frame only)
    - TCP transport for reliability
    - Automatic reconnection with exponential backoff

    Phase 6.12: Thread-safe reconnection (fixes async_lock crash)
    - stop() only signals, never touches _cap
    - _cap is released ONLY inside capture thread
    - request_reconnect() for soft reconnection without stop

    Phase 6.14: Config-aware restart
    - get_config_signature() for config comparison
    - start() with auto-restart if config changed
    """

    # Consecutive errors threshold before triggering reconnect
    RECONNECT_ERROR_THRESHOLD = 30
    # Max frame age (seconds) before considering stall
    STALL_TIMEOUT = 5.0

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        fps_target: int = 10,
        timeout_s: float = 5.0,
        reconnect_s: float = 2.0
    ):
        """
        Inicializa fuente RTSP.

        Args:
            url: URL del stream RTSP (ej: rtsp://admin:12345@192.168.1.64:554/Streaming/Channels/102)
            username: Usuario (si no está en URL)
            password: Password (si no está en URL)
            fps_target: FPS objetivo para rate limiting
            timeout_s: Timeout de conexión
            reconnect_s: Delay base entre reconexiones
        """
        # Build URL with credentials if not already present
        if username and password and "@" not in url:
            # Insert credentials into URL
            if url.startswith("rtsp://"):
                url = f"rtsp://{username}:{password}@{url[7:]}"

        self.url = url
        self.username = username
        self.password = password
        self.fps_target = fps_target
        self.connect_timeout = timeout_s
        self.reconnect_s = reconnect_s

        # Estado interno - eventos para señalización thread-safe
        self._stop_event = threading.Event()
        self._reconnect_event = threading.Event()  # Phase 6.12: soft reconnect signal
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._opened = False

        # Frame buffer - queue maxsize=1 for latest-frame-only policy
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.RLock()
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_ts: float = 0.0
        self._frame_count = 0
        self._actual_fps = 0.0
        self._fps_start_time = None

        # Metrics
        self._drops = 0
        self._decode_ms_avg = 0.0
        self._decode_samples = 0
        self._read_errors = 0
        self._reconnect_count = 0

        # Detección de stall
        self._stall_detected = False

        # Backoff config
        self._max_reconnect_backoff = 10.0

        # Phase 6.14: Config signature for change detection
        self._config_signature = self._compute_config_signature()

    def _compute_config_signature(self) -> str:
        """Computes a signature from config params for change detection."""
        return f"{self.url}|{self.fps_target}"

    def get_config_signature(self) -> str:
        """Returns current config signature for comparison."""
        return self._config_signature

    def start(self, new_url: str = None) -> bool:
        """
        Inicia el thread de captura RTSP.

        Phase 6.14: If already running, checks if config changed.
        - Same config → log "Already running (same config)" and return True
        - Different config → restart with new config
        """
        # Build new signature if params provided
        check_url = new_url if new_url is not None else self.url
        new_signature = f"{check_url}|{self.fps_target}"

        if self._thread and self._thread.is_alive():
            # Check if config is the same
            if new_signature == self._config_signature:
                print(f"[RTSPSource] Already running (same config): {self._safe_url()}")
                return True
            else:
                # Config changed - do restart
                print(f"[RTSPSource] Config changed while running - restarting...")
                self.stop()
                if new_url is not None:
                    self.url = new_url
                self._config_signature = new_signature

        # Validar URL
        if not self.url or not self.url.startswith("rtsp://"):
            print(f"[RTSPSource] URL inválida: {self._safe_url()}")
            return False

        print(f"[RTSPSource] STARTING: {self._safe_url()}")

        # Reset state
        self._stop_event.clear()
        self._stall_detected = False
        self._reconnect_count = 0
        self._opened = False
        self._drops = 0
        self._read_errors = 0

        # Iniciar thread
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"RTSPSource-{id(self)}"
        )
        self._thread.start()

        # Esperar a que conecte
        start_wait = time.time()
        while time.time() - start_wait < self.connect_timeout:
            if self._stop_event.is_set():
                return False
            if self._opened:
                print(f"[RTSPSource] STARTED OK: {self._safe_url()}")
                return True
            time.sleep(0.1)

        print(f"[RTSPSource] Timeout esperando conexión: {self._safe_url()}")
        return self._opened

    def stop(self) -> None:
        """
        Detiene el thread de captura de forma robusta.

        Phase 6.12: Thread-safe stop - NEVER touches _cap directly.
        Only signals stop and waits for thread to cleanup internally.
        This prevents FFmpeg async_lock assertion failures.
        """
        print(f"[RTSPSource] STOPPING: {self._safe_url()}")

        # Señalar stop - el thread liberará _cap internamente
        self._stop_event.set()

        # CRITICAL: NO tocar _cap aquí - causa crash async_lock
        # El thread se encarga de liberar _cap antes de terminar

        # Join thread con timeout generoso
        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                print(f"[RTSPSource] WARNING: thread no murió en 2s (will be orphaned)")
            self._thread = None

        self._opened = False
        print(f"[RTSPSource] STOPPED: {self._safe_url()}")

    def request_reconnect(self) -> None:
        """
        Solicita reconexión sin detener el source.

        Phase 6.12: Soft reconnect - solo setea evento.
        El thread de captura detectará el evento y reconectará
        liberando _cap internamente (thread-safe).

        Usar esto en lugar de stop()+start() cuando hay errores de lectura.
        """
        if not self._thread or not self._thread.is_alive():
            print(f"[RTSPSource] request_reconnect ignored (thread not running)")
            return

        print(f"[RTSPSource] Reconnect requested: {self._safe_url()}")
        self._reconnect_event.set()

    def supports_reconnect(self) -> bool:
        """
        Indica si este source soporta reconexión soft.

        Phase 6.12: CameraLoop debe usar request_reconnect() en lugar
        de stop() cuando esta función retorna True.
        """
        return True

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Lee el último frame disponible (NO bloqueante).

        Returns:
            tuple: (success, frame) - frame es copia del último disponible
        """
        with self._lock:
            if self._last_frame is None:
                return False, None

            # Verificar stall
            age = time.time() - self._last_frame_ts
            if age > self.connect_timeout:
                if not self._stall_detected:
                    print(f"[RTSPSource] Stall detected: frame age={age:.1f}s")
                    self._stall_detected = True
                return False, None

            self._stall_detected = False
            return True, self._last_frame.copy()

    def is_opened(self) -> bool:
        """Verifica si la fuente está conectada."""
        return self._opened and not self._stop_event.is_set()

    def get_info(self) -> Dict[str, Any]:
        """Obtiene información de la fuente RTSP."""
        with self._lock:
            frame_shape = self._last_frame.shape if self._last_frame is not None else None

        return {
            "type": "rtsp",
            "url": self._safe_url(),
            "fps_target": self.fps_target,
            "connect_timeout": self.connect_timeout,
            "reconnect_s": self.reconnect_s,
            "opened": self._opened,
            "fps_actual": self._actual_fps,
            "fps_read": self._actual_fps,
            "frame_shape": frame_shape,
            "stall_detected": self._stall_detected,
            # Metrics
            "drops": self._drops,
            "decode_ms": self._decode_ms_avg,
            "queue_len": self._frame_queue.qsize(),
            "read_errors": self._read_errors,
        }

    def get_fps(self) -> float:
        """Obtiene FPS real medido."""
        return self._actual_fps

    def _safe_url(self) -> str:
        """Retorna URL con password oculto para logs."""
        if "@" in self.url:
            # rtsp://user:pass@host -> rtsp://user:***@host
            try:
                prefix, rest = self.url.split("@", 1)
                if ":" in prefix:
                    proto_user = prefix.rsplit(":", 1)[0]
                    return f"{proto_user}:***@{rest}"
            except:
                pass
        return self.url

    def _capture_loop(self):
        """
        Thread principal de captura RTSP.

        Phase 6.12: Thread-safe lifecycle
        - _cap se crea y libera SOLO dentro de este thread
        - Maneja _reconnect_event para soft reconnect
        - Cleanup garantizado antes de salir
        """
        print(f"[RTSPSource] Thread started: {threading.current_thread().name}")

        while not self._stop_event.is_set():
            try:
                self._connect_and_stream()
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[RTSPSource] Error en capture loop: {e}")

            # Cleanup _cap DENTRO del thread (thread-safe)
            self._release_capture_internal()

            # Check if reconnect was requested vs natural disconnect
            reconnect_requested = self._reconnect_event.is_set()
            if reconnect_requested:
                self._reconnect_event.clear()
                print(f"[RTSPSource] Reconnect event handled")

            # Reconectar con backoff (si no estamos parando)
            if not self._stop_event.is_set():
                self._opened = False
                self._reconnect_count += 1

                # Backoff más corto si fue request_reconnect()
                if reconnect_requested:
                    backoff = 0.5  # Reconexión rápida si fue solicitada
                else:
                    backoff = min(
                        self.reconnect_s * (1.5 ** min(self._reconnect_count, 5)),
                        self._max_reconnect_backoff
                    )

                print(f"[RTSPSource] Reconnecting in {backoff:.1f}s (attempt {self._reconnect_count})...")

                if self._stop_event.wait(timeout=backoff):
                    break

        # Cleanup final DENTRO del thread
        self._release_capture_internal()
        self._opened = False
        print(f"[RTSPSource] Thread exiting: {threading.current_thread().name}")

    def _release_capture_internal(self):
        """
        Libera VideoCapture de forma segura DENTRO del thread.

        Phase 6.12: Este método SOLO debe llamarse desde el thread de captura.
        Nunca desde stop() o código externo.
        """
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as e:
                print(f"[RTSPSource] Error releasing capture (internal): {e}")
            self._cap = None

    def _connect_and_stream(self):
        """
        Conecta al stream RTSP y captura frames.

        Phase 6.12: Thread-safe streaming
        - NO libera _cap aquí (lo hace _capture_loop)
        - Verifica _reconnect_event para soft reconnect
        - Sale limpiamente si se detecta stop o reconnect
        """
        if self._stop_event.is_set():
            return

        print(f"[RTSPSource] Connecting to {self._safe_url()}...")

        # Crear VideoCapture con propiedades de baja latencia
        self._cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

        # Configurar propiedades para baja latencia
        # Nota: No todas las propiedades están soportadas en todas las plataformas
        try:
            # Buffer mínimo
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Timeout de apertura (ms)
            self._cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self.connect_timeout * 1000))
            # Timeout de lectura (ms)
            self._cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000)
        except Exception as e:
            print(f"[RTSPSource] Warning setting properties: {e}")

        if not self._cap.isOpened():
            print(f"[RTSPSource] Failed to open: {self._safe_url()}")
            # NO liberar aquí - _capture_loop lo hace con _release_capture_internal()
            return

        # Obtener info del stream
        width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        stream_fps = self._cap.get(cv2.CAP_PROP_FPS)
        print(f"[RTSPSource] Connected! Resolution: {width}x{height}, Stream FPS: {stream_fps}")

        self._opened = True
        self._reconnect_count = 0

        # Reset FPS counter
        self._frame_count = 0
        self._fps_start_time = time.time()

        # Frame interval for rate limiting
        frame_interval = 1.0 / self.fps_target if self.fps_target > 0 else 0
        last_frame_time = 0

        consecutive_errors = 0

        # Main capture loop - sale si: stop, reconnect, o errores consecutivos
        while not self._stop_event.is_set() and not self._reconnect_event.is_set():
            # Verificar que cap sigue válido
            if self._cap is None or not self._cap.isOpened():
                print(f"[RTSPSource] Capture became invalid, exiting stream loop")
                break

            try:
                # Rate limiting
                now = time.time()
                if frame_interval > 0 and (now - last_frame_time) < frame_interval:
                    # Skip frame to match target fps
                    ret = self._cap.grab()
                    if not ret:
                        consecutive_errors += 1
                        if consecutive_errors >= self.RECONNECT_ERROR_THRESHOLD:
                            print(f"[RTSPSource] Too many grab errors ({consecutive_errors}), will reconnect...")
                            break
                    continue

                # Leer frame con medición de tiempo
                decode_start = time.perf_counter()
                ret, frame = self._cap.read()
                decode_ms = (time.perf_counter() - decode_start) * 1000

                if not ret or frame is None:
                    consecutive_errors += 1
                    self._read_errors += 1
                    if consecutive_errors >= self.RECONNECT_ERROR_THRESHOLD:
                        print(f"[RTSPSource] Too many read errors ({consecutive_errors}), will reconnect...")
                        break
                    # No log por cada error individual - solo cuando umbral
                    continue

                consecutive_errors = 0
                last_frame_time = now

                # Update decode time average
                if self._decode_samples == 0:
                    self._decode_ms_avg = decode_ms
                else:
                    self._decode_ms_avg = 0.9 * self._decode_ms_avg + 0.1 * decode_ms
                self._decode_samples += 1

                # Latest-frame-only policy
                with self._lock:
                    self._last_frame = frame
                    self._last_frame_ts = time.time()

                # Queue con drop
                try:
                    self._frame_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self._frame_queue.get_nowait()
                        self._drops += 1
                    except queue.Empty:
                        pass
                    try:
                        self._frame_queue.put_nowait(frame)
                    except queue.Full:
                        pass

                self._update_fps()

            except Exception as e:
                if not self._stop_event.is_set() and not self._reconnect_event.is_set():
                    print(f"[RTSPSource] Read error: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= self.RECONNECT_ERROR_THRESHOLD:
                        break

        # NO cleanup aquí - _capture_loop lo hace con _release_capture_internal()
        # Esto es crítico para evitar el crash de async_lock
        self._opened = False

    def _update_fps(self):
        """Actualiza el contador de FPS."""
        self._frame_count += 1

        if self._fps_start_time is None:
            self._fps_start_time = time.time()

        elapsed = time.time() - self._fps_start_time

        if elapsed >= 1.0:
            self._actual_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_start_time = time.time()


class RTSPSourcePyAV(CameraSource):
    """
    Fuente de cámara RTSP usando PyAV (FFmpeg bindings).
    Optimizado para baja latencia VMS-grade con H.264/H.265 streams.

    Phase 6.13: PyAV-based RTSP with VMS-grade low latency
    - FFmpeg options: nobuffer, low_delay, minimal probesize
    - Transport selector: UDP (default) or TCP
    - Queue maxsize=1 with drop policy (latest frame only)
    - Thread-safe reconnection (maintains fix from Phase 6.12)
    - PTS-based latency estimation

    Phase 6.14: Config-aware restart
    - get_config_signature() for config comparison
    - start() with auto-restart if config changed
    """

    # Consecutive errors threshold before triggering reconnect
    RECONNECT_ERROR_THRESHOLD = 30
    # Max frame age (seconds) before considering stall
    STALL_TIMEOUT = 5.0

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        fps_target: int = 10,
        timeout_s: float = 5.0,
        reconnect_s: float = 2.0,
        transport: str = "udp",
        low_latency: bool = True
    ):
        """
        Inicializa fuente RTSP con PyAV.

        Args:
            url: URL del stream RTSP
            username: Usuario (si no está en URL)
            password: Password (si no está en URL)
            fps_target: FPS objetivo para rate limiting
            timeout_s: Timeout de conexión
            reconnect_s: Delay base entre reconexiones
            transport: "udp" (default, lower latency) o "tcp" (more reliable)
            low_latency: True para modo baja latencia (default)
        """
        # Build URL with credentials if not already present
        if username and password and "@" not in url:
            if url.startswith("rtsp://"):
                url = f"rtsp://{username}:{password}@{url[7:]}"

        self.url = url
        self.username = username
        self.password = password
        self.fps_target = fps_target
        self.connect_timeout = timeout_s
        self.reconnect_s = reconnect_s
        self.transport = transport.lower()
        self.low_latency = low_latency

        # Estado interno - eventos thread-safe
        self._stop_event = threading.Event()
        self._reconnect_event = threading.Event()
        self._container = None
        self._thread: Optional[threading.Thread] = None
        self._opened = False

        # Frame buffer - queue maxsize=1 for latest-frame-only policy
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.RLock()
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_ts: float = 0.0
        self._last_pts: Optional[float] = None
        self._frame_count = 0
        self._actual_fps = 0.0
        self._fps_start_time = None

        # Metrics
        self._drops = 0
        self._decode_ms_avg = 0.0
        self._decode_samples = 0
        self._read_errors = 0
        self._reconnect_count = 0
        self._latency_est_ms = 0.0

        # Stall detection
        self._stall_detected = False
        self._max_reconnect_backoff = 10.0

        # Phase 6.14: Config signature for change detection
        self._config_signature = self._compute_config_signature()

    def _compute_config_signature(self) -> str:
        """Computes a signature from config params for change detection."""
        return f"{self.url}|{self.transport}|{self.low_latency}|{self.fps_target}"

    def get_config_signature(self) -> str:
        """Returns current config signature for comparison."""
        return self._config_signature

    def start(self, new_url: str = None, new_transport: str = None, new_low_latency: bool = None) -> bool:
        """
        Inicia el thread de captura RTSP PyAV.

        Phase 6.14: If already running, checks if config changed.
        - Same config → log "Already running (same config)" and return True
        - Different config → restart with new config

        Args:
            new_url: Optional new URL (for restart detection)
            new_transport: Optional new transport ("udp" or "tcp")
            new_low_latency: Optional new low_latency flag
        """
        # Build new signature if params provided
        check_url = new_url if new_url is not None else self.url
        check_transport = new_transport if new_transport is not None else self.transport
        check_low_latency = new_low_latency if new_low_latency is not None else self.low_latency
        new_signature = f"{check_url}|{check_transport}|{check_low_latency}|{self.fps_target}"

        if self._thread and self._thread.is_alive():
            # Check if config is the same
            if new_signature == self._config_signature:
                print(f"[RTSPSourcePyAV] Already running (same config): {self._safe_url()}")
                return True
            else:
                # Config changed - do restart
                print(f"[RTSPSourcePyAV] Config changed while running - restarting...")
                print(f"[RTSPSourcePyAV] Old config: {self._config_signature[:60]}")
                print(f"[RTSPSourcePyAV] New config: {new_signature[:60]}")
                self.stop()
                # Update config
                if new_url is not None:
                    self.url = new_url
                if new_transport is not None:
                    self.transport = new_transport.lower()
                if new_low_latency is not None:
                    self.low_latency = new_low_latency
                self._config_signature = new_signature

        if not self.url or not self.url.startswith("rtsp://"):
            print(f"[RTSPSourcePyAV] Invalid URL: {self._safe_url()}")
            return False

        print(f"[RTSPSourcePyAV] STARTING: {self._safe_url()} transport={self.transport} low_latency={self.low_latency}")

        # Reset state
        self._stop_event.clear()
        self._reconnect_event.clear()
        self._stall_detected = False
        self._reconnect_count = 0
        self._opened = False
        self._drops = 0
        self._read_errors = 0

        # Start capture thread
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"RTSPSourcePyAV-{id(self)}"
        )
        self._thread.start()

        # Wait for connection
        start_wait = time.time()
        while time.time() - start_wait < self.connect_timeout:
            if self._stop_event.is_set():
                return False
            if self._opened:
                print(f"[RTSPSourcePyAV] STARTED OK: {self._safe_url()}")
                return True
            time.sleep(0.1)

        print(f"[RTSPSourcePyAV] Connection timeout: {self._safe_url()}")
        return self._opened

    def stop(self) -> None:
        """
        Detiene el thread de captura de forma thread-safe.
        NUNCA toca _container directamente - el thread lo libera.
        """
        print(f"[RTSPSourcePyAV] STOPPING: {self._safe_url()}")
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                print(f"[RTSPSourcePyAV] WARNING: thread didn't stop in 2s")
            self._thread = None

        self._opened = False
        print(f"[RTSPSourcePyAV] STOPPED: {self._safe_url()}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Lee el último frame disponible (NO bloqueante)."""
        with self._lock:
            if self._last_frame is None:
                return False, None

            age = time.time() - self._last_frame_ts
            if age > self.STALL_TIMEOUT:
                if not self._stall_detected:
                    print(f"[RTSPSourcePyAV] Stall detected: frame age={age:.1f}s")
                    self._stall_detected = True
                return False, None

            self._stall_detected = False
            return True, self._last_frame.copy()

    def is_opened(self) -> bool:
        """Verifica si la fuente está conectada."""
        return self._opened and not self._stop_event.is_set()

    def get_info(self) -> Dict[str, Any]:
        """Obtiene información de la fuente."""
        with self._lock:
            frame_shape = self._last_frame.shape if self._last_frame is not None else None

        return {
            "type": "rtsp-pyav",
            "url": self._safe_url(),
            "transport": self.transport,
            "low_latency": self.low_latency,
            "fps_target": self.fps_target,
            "opened": self._opened,
            "fps_actual": self._actual_fps,
            "fps_read": self._actual_fps,
            "frame_shape": frame_shape,
            "stall_detected": self._stall_detected,
            "drops": self._drops,
            "decode_ms": self._decode_ms_avg,
            "queue_len": self._frame_queue.qsize(),
            "read_errors": self._read_errors,
            "latency_est_ms": self._latency_est_ms,
        }

    def get_fps(self) -> float:
        """Obtiene FPS real medido."""
        return self._actual_fps

    def request_reconnect(self) -> None:
        """Solicita reconexión sin detener el source."""
        if not self._thread or not self._thread.is_alive():
            return
        print(f"[RTSPSourcePyAV] Reconnect requested")
        self._reconnect_event.set()

    def supports_reconnect(self) -> bool:
        """Indica soporte para reconexión soft."""
        return True

    def _safe_url(self) -> str:
        """Retorna URL con password oculto."""
        if "@" in self.url:
            try:
                prefix, rest = self.url.split("@", 1)
                if ":" in prefix:
                    proto_user = prefix.rsplit(":", 1)[0]
                    return f"{proto_user}:***@{rest}"
            except:
                pass
        return self.url

    def _get_ffmpeg_options(self) -> Dict[str, str]:
        """Construye opciones FFmpeg para baja latencia."""
        options = {
            "rtsp_transport": self.transport,
            "stimeout": str(int(self.connect_timeout * 1000000)),  # microseconds
        }

        if self.low_latency:
            options.update({
                "fflags": "nobuffer",
                "flags": "low_delay",
                "analyzeduration": "0",
                "probesize": "32768",  # 32KB - minimal but safe
                "max_delay": "0",
                "reorder_queue_size": "0",
            })

        return options

    def _capture_loop(self):
        """Thread principal de captura RTSP PyAV."""
        print(f"[RTSPSourcePyAV] Thread started: {threading.current_thread().name}")

        while not self._stop_event.is_set():
            try:
                self._connect_and_stream()
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[RTSPSourcePyAV] Capture loop error: {e}")

            # Cleanup container INSIDE thread (thread-safe)
            self._release_container_internal()

            reconnect_requested = self._reconnect_event.is_set()
            if reconnect_requested:
                self._reconnect_event.clear()

            if not self._stop_event.is_set():
                self._opened = False
                self._reconnect_count += 1

                backoff = 0.5 if reconnect_requested else min(
                    self.reconnect_s * (1.5 ** min(self._reconnect_count, 5)),
                    self._max_reconnect_backoff
                )
                print(f"[RTSPSourcePyAV] Reconnecting in {backoff:.1f}s (attempt {self._reconnect_count})...")

                if self._stop_event.wait(timeout=backoff):
                    break

        self._release_container_internal()
        self._opened = False
        print(f"[RTSPSourcePyAV] Thread exiting")

    def _release_container_internal(self):
        """Libera container PyAV de forma segura DENTRO del thread."""
        if self._container is not None:
            try:
                self._container.close()
            except Exception as e:
                print(f"[RTSPSourcePyAV] Error closing container: {e}")
            self._container = None

    def _connect_and_stream(self):
        """Conecta al stream RTSP y captura frames."""
        if self._stop_event.is_set():
            return

        print(f"[RTSPSourcePyAV] Connecting to {self._safe_url()}...")

        options = self._get_ffmpeg_options()
        print(f"[RTSPSourcePyAV] FFmpeg options: {options}")

        try:
            self._container = av.open(
                self.url,
                options=options,
                timeout=(self.connect_timeout, None)
            )
        except Exception as e:
            print(f"[RTSPSourcePyAV] Failed to open: {e}")
            return

        # Find video stream
        video_stream = None
        for stream in self._container.streams:
            if stream.type == 'video':
                video_stream = stream
                break

        if not video_stream:
            print(f"[RTSPSourcePyAV] No video stream found")
            return

        # Configure for low latency decoding
        video_stream.thread_type = "AUTO"

        width = video_stream.codec_context.width
        height = video_stream.codec_context.height
        codec_name = video_stream.codec_context.name
        print(f"[RTSPSourcePyAV] Connected! {width}x{height} codec={codec_name}")

        self._opened = True
        self._reconnect_count = 0
        self._frame_count = 0
        self._fps_start_time = time.time()

        # Frame interval for rate limiting
        frame_interval = 1.0 / self.fps_target if self.fps_target > 0 else 0
        last_frame_time = 0
        consecutive_errors = 0

        try:
            for packet in self._container.demux(video_stream):
                if self._stop_event.is_set() or self._reconnect_event.is_set():
                    break

                try:
                    for frame in packet.decode():
                        if self._stop_event.is_set() or self._reconnect_event.is_set():
                            break

                        now = time.time()

                        # Rate limiting
                        if frame_interval > 0 and (now - last_frame_time) < frame_interval:
                            continue

                        # Convert to numpy BGR
                        decode_start = time.perf_counter()
                        img = frame.to_ndarray(format='bgr24')
                        decode_ms = (time.perf_counter() - decode_start) * 1000

                        # Update metrics
                        if self._decode_samples == 0:
                            self._decode_ms_avg = decode_ms
                        else:
                            self._decode_ms_avg = 0.9 * self._decode_ms_avg + 0.1 * decode_ms
                        self._decode_samples += 1

                        # Estimate latency from PTS
                        if frame.pts is not None and video_stream.time_base:
                            pts_seconds = float(frame.pts * video_stream.time_base)
                            # Simple latency estimation (stream time vs wall clock)
                            # This is approximate since we don't have NTP sync
                            self._last_pts = pts_seconds

                        # Store frame
                        with self._lock:
                            self._last_frame = img
                            self._last_frame_ts = now

                        # Queue with drop
                        try:
                            self._frame_queue.put_nowait(img)
                        except queue.Full:
                            try:
                                self._frame_queue.get_nowait()
                                self._drops += 1
                            except queue.Empty:
                                pass
                            try:
                                self._frame_queue.put_nowait(img)
                            except queue.Full:
                                pass

                        last_frame_time = now
                        self._update_fps()
                        consecutive_errors = 0

                except av.error.EOFError:
                    print(f"[RTSPSourcePyAV] EOF reached")
                    break
                except Exception as e:
                    if not self._stop_event.is_set():
                        consecutive_errors += 1
                        self._read_errors += 1
                        if consecutive_errors >= self.RECONNECT_ERROR_THRESHOLD:
                            print(f"[RTSPSourcePyAV] Too many errors ({consecutive_errors}), will reconnect")
                            break

        except av.error.ExitError:
            if not self._stop_event.is_set():
                print(f"[RTSPSourcePyAV] Stream terminated")
        except Exception as e:
            if not self._stop_event.is_set():
                print(f"[RTSPSourcePyAV] Stream error: {e}")

        self._opened = False

    def _update_fps(self):
        """Actualiza el contador de FPS."""
        self._frame_count += 1
        if self._fps_start_time is None:
            self._fps_start_time = time.time()

        elapsed = time.time() - self._fps_start_time
        if elapsed >= 1.0:
            self._actual_fps = self._frame_count / elapsed
            self._frame_count = 0
            self._fps_start_time = time.time()


def validate_camera_url(url: str) -> Tuple[bool, str]:
    """
    Valida que una URL de cámara no tenga protocolos mixtos u otros errores.
    Phase 6.11: Prevenir errores comunes de configuración.

    Args:
        url: URL a validar

    Returns:
        tuple: (is_valid, error_message)
    """
    if not url:
        return False, "URL vacía"

    url_lower = url.lower()

    # Check for mixed protocols (most common user error)
    if url_lower.startswith("http://") or url_lower.startswith("https://"):
        if "rtsp://" in url_lower:
            return False, "INVALID URL: mixed protocols (http + rtsp). Use RTSP protocol selector."

    if url_lower.startswith("rtsp://"):
        if "http://" in url_lower or "https://" in url_lower:
            return False, "INVALID URL: mixed protocols (rtsp + http). Check URL format."

    # Check for common typos in IP
    if "192.160." in url:
        print(f"[CameraSource] WARNING: URL contains 192.160 - possible typo for 192.168?")

    return True, ""


def detect_source_type(url: str, explicit_type: Optional[str] = None) -> str:
    """
    Auto-detecta el tipo de fuente basado en URL.

    Args:
        url: URL del stream
        explicit_type: Tipo explícito para override (opcional)

    Returns:
        str: "rtsp" o "mjpeg"
    """
    if explicit_type and explicit_type.lower() in ("rtsp", "mjpeg"):
        return explicit_type.lower()

    url_lower = url.lower()

    # RTSP detection
    if url_lower.startswith("rtsp://"):
        return "rtsp"

    # MJPEG detection
    if url_lower.startswith("http://") or url_lower.startswith("https://"):
        if any(kw in url_lower for kw in ["mjpg", "mjpeg", "video.cgi", "axis-cgi"]):
            return "mjpeg"

    # Default to MJPEG for HTTP
    if url_lower.startswith("http"):
        return "mjpeg"

    # Default based on port patterns
    if ":554" in url or ":8554" in url:
        return "rtsp"

    return "mjpeg"


def create_source_from_config(config: Dict[str, Any]) -> CameraSource:
    """
    Factory function para crear CameraSource desde configuración.
    Soporta MJPEG (HTTP) y RTSP (H.264) con auto-detección.

    Phase 6.11: Soporte dual MJPEG + RTSP
    Phase 6.13: PyAV-based RTSP con baja latencia VMS-grade

    Args:
        config: Dict con parámetros de cámara:
            - type: "mjpeg" | "rtsp" | "auto" (opcional, auto-detecta si no se especifica)
            - url: URL del stream (requerido)
            - url_main: URL del stream principal (opcional, para RTSP)
            - url_sub: URL del substream (opcional, para RTSP)
            - preferred: "main" | "sub" (default "sub" para RTSP)
            - username: Usuario para auth
            - password: Password para auth
            - fps_target: FPS objetivo
            - timeout_s: Timeout de conexión
            - reconnect_s: Delay entre reconexiones
            - transport: "udp" | "tcp" (default "udp", solo RTSP)
            - low_latency: bool (default True, solo RTSP)

    Returns:
        CameraSource: Instancia de MJPEGSource, RTSPSourcePyAV o RTSPSource

    Raises:
        ValueError: Si no hay URL válida o tipo no soportado
    """
    # Determinar URL a usar
    url = config.get("url", "")
    url_main = config.get("url_main", "")
    url_sub = config.get("url_sub", "")
    preferred = config.get("preferred", "sub").lower()

    # Para RTSP con main/sub, elegir según preferencia
    if url_main or url_sub:
        if preferred == "sub" and url_sub:
            url = url_sub
        elif preferred == "main" and url_main:
            url = url_main
        elif url_sub:
            url = url_sub
        elif url_main:
            url = url_main

    if not url:
        raise ValueError("No URL provided in config")

    # Phase 6.11: Validar URL antes de crear source
    is_valid, error_msg = validate_camera_url(url)
    if not is_valid:
        print(f"[CameraSource] URL VALIDATION FAILED: {error_msg}")
        raise ValueError(error_msg)

    # Auto-detectar o usar tipo explícito
    explicit_type = config.get("type", "auto")
    source_type = detect_source_type(url, explicit_type if explicit_type != "auto" else None)

    print(f"[CameraSource] Creating {source_type.upper()} source for URL: {url[:50]}...")

    common_params = {
        "url": url,
        "username": config.get("username", ""),
        "password": config.get("password", ""),
        "fps_target": config.get("fps_target", 10),
        "timeout_s": config.get("timeout_s", 5.0),
        "reconnect_s": config.get("reconnect_s", 2.0),
    }

    if source_type == "rtsp":
        # Phase 6.13: Usar PyAV si está disponible para baja latencia
        transport = config.get("transport", "udp").lower()
        low_latency = config.get("low_latency", True)

        if PYAV_AVAILABLE:
            print(f"[CameraSource] Using PyAV (low-latency mode) transport={transport} low_latency={low_latency}")
            return RTSPSourcePyAV(
                **common_params,
                transport=transport,
                low_latency=low_latency
            )
        else:
            print(f"[CameraSource] PyAV not available, using OpenCV fallback")
            return RTSPSource(**common_params)
    elif source_type == "mjpeg":
        return MJPEGSource(**common_params)
    else:
        raise ValueError(f"Tipo de fuente no soportado: {source_type}. Use 'mjpeg' o 'rtsp'.")
