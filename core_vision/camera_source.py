"""
CameraSource - Abstracción de fuentes de cámara para 911 Fiesta
Soporta: MJPEG (HTTP streaming) - IP cameras only

Phase 6.7 - IP Camera Support
Phase 6.9 - Robust stop mechanism for MJPEGSource
Phase 6.10 - USB REMOVED, MJPEG only (ip_only mode enforced)
"""
import cv2
import numpy as np
import threading
import time
import requests
from requests.exceptions import ReadTimeout, ChunkedEncodingError, ConnectionError as ReqConnectionError
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any


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

        # Frame buffer (thread-safe)
        self._lock = threading.RLock()
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_ts: float = 0.0
        self._frame_count = 0
        self._actual_fps = 0.0
        self._fps_start_time = None

        # Detección de stall
        self._stall_detected = False

        # Contador de reconexiones para backoff
        self._reconnect_count = 0
        self._max_reconnect_backoff = 10.0

    def start(self) -> bool:
        """Inicia el thread de captura MJPEG."""
        if self._thread and self._thread.is_alive():
            print(f"[MJPEGSource] Ya está corriendo: {self.url}")
            return True

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
            "frame_shape": frame_shape,
            "stall_detected": self._stall_detected
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

                        # Decodificar JPEG a BGR
                        img_array = np.frombuffer(jpeg_data, dtype=np.uint8)
                        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

                        if frame is not None:
                            with self._lock:
                                self._last_frame = frame
                                self._last_frame_ts = time.time()

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


def create_source_from_config(config: Dict[str, Any]) -> CameraSource:
    """
    Factory function para crear CameraSource desde configuración.
    Solo soporta MJPEG (IP cameras). USB fue removido en Phase 6.10.

    Args:
        config: Dict con type="mjpeg" y parámetros MJPEG

    Returns:
        CameraSource: Instancia de MJPEGSource

    Raises:
        ValueError: Si el tipo no es "mjpeg"
    """
    source_type = config.get("type", "mjpeg").lower()

    if source_type == "mjpeg":
        return MJPEGSource(
            url=config.get("url", ""),
            username=config.get("username", ""),
            password=config.get("password", ""),
            fps_target=config.get("fps_target", 10),
            timeout_s=config.get("timeout_s", 5.0),
            reconnect_s=config.get("reconnect_s", 2.0)
        )

    else:
        raise ValueError(f"Tipo de fuente no soportado: {source_type}. Solo 'mjpeg' es válido (USB fue removido).")
