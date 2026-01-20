"""
CameraSource - Abstracción de fuentes de cámara para 911 Fiesta
Soporta: MJPEG (HTTP streaming) + RTSP (H.264 via OpenCV)

Phase 6.7 - IP Camera Support
Phase 6.9 - Robust stop mechanism for MJPEGSource
Phase 6.10 - USB REMOVED, MJPEG only (ip_only mode enforced)
Phase 6.11 - RTSP support + unified low-latency buffer (queue maxsize=1)
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
    """

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

        # Estado interno
        self._stop_event = threading.Event()
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

        # Detección de stall
        self._stall_detected = False

        # Contador de reconexiones para backoff
        self._reconnect_count = 0
        self._max_reconnect_backoff = 10.0

    def start(self) -> bool:
        """Inicia el thread de captura RTSP."""
        if self._thread and self._thread.is_alive():
            print(f"[RTSPSource] Ya está corriendo: {self._safe_url()}")
            return True

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
        """Detiene el thread de captura de forma robusta."""
        print(f"[RTSPSource] STOPPING: {self._safe_url()}")

        # Señalar stop
        self._stop_event.set()

        # Cerrar captura
        if self._cap:
            try:
                self._cap.release()
            except Exception as e:
                print(f"[RTSPSource] Error releasing capture: {e}")
            self._cap = None

        # Join thread
        if self._thread:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                print(f"[RTSPSource] WARNING: thread no murió en 1s")
            self._thread = None

        self._opened = False
        print(f"[RTSPSource] STOPPED: {self._safe_url()}")

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
        """Thread principal de captura RTSP."""
        print(f"[RTSPSource] Thread started: {threading.current_thread().name}")

        while not self._stop_event.is_set():
            try:
                self._connect_and_stream()
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[RTSPSource] Error en capture loop: {e}")

            # Reconectar con backoff
            if not self._stop_event.is_set():
                self._opened = False
                self._reconnect_count += 1

                backoff = min(
                    self.reconnect_s * (1.5 ** min(self._reconnect_count, 5)),
                    self._max_reconnect_backoff
                )
                print(f"[RTSPSource] Reconnecting in {backoff:.1f}s (attempt {self._reconnect_count})...")

                if self._stop_event.wait(timeout=backoff):
                    break

        self._opened = False
        print(f"[RTSPSource] Thread exiting: {threading.current_thread().name}")

    def _connect_and_stream(self):
        """Conecta al stream RTSP y captura frames."""
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
            if self._cap:
                self._cap.release()
                self._cap = None
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
        max_consecutive_errors = 30  # ~1 segundo a 30fps

        while not self._stop_event.is_set() and self._cap and self._cap.isOpened():
            try:
                # Rate limiting
                now = time.time()
                if frame_interval > 0 and (now - last_frame_time) < frame_interval:
                    # Skip frame to match target fps
                    ret = self._cap.grab()
                    if not ret:
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"[RTSPSource] Too many grab errors, reconnecting...")
                            break
                    continue

                # Leer frame con medición de tiempo
                decode_start = time.perf_counter()
                ret, frame = self._cap.read()
                decode_ms = (time.perf_counter() - decode_start) * 1000

                if not ret or frame is None:
                    consecutive_errors += 1
                    self._read_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"[RTSPSource] Too many read errors ({consecutive_errors}), reconnecting...")
                        break
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
                if not self._stop_event.is_set():
                    print(f"[RTSPSource] Read error: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        break

        # Cleanup
        if self._cap:
            try:
                self._cap.release()
            except:
                pass
            self._cap = None

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

    Returns:
        CameraSource: Instancia de MJPEGSource o RTSPSource

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
        return RTSPSource(**common_params)
    elif source_type == "mjpeg":
        return MJPEGSource(**common_params)
    else:
        raise ValueError(f"Tipo de fuente no soportado: {source_type}. Use 'mjpeg' o 'rtsp'.")
