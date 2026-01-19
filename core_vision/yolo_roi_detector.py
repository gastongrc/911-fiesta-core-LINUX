"""
YoloRoiDetector V9 - YOLO-based ROI-only Person Detection
Phase 9: Detection only within ROI of each zone (not full frame)

GOLDEN RULES:
1. Never freeze core/UI - drop frames, lower FPS, backoff if heavy
2. Detection ONLY on ROI crop (not full frame)
3. YOLO direct (ultralytics YOLOv8n)
4. Rate-limited processing (default 6 FPS)
5. Backoff if inference > 250ms
6. Queue size=1 (latest frame only, drop rest)

Performance Controls:
- downscale: Resize large ROIs before inference
- conf_threshold: YOLO confidence threshold (default 0.35)
- rate_limit_fps: Max processing rate (default 6 FPS)
- max_infer_ms: Backoff threshold (default 250ms)
- queue_size: Frame queue size (default 1, latest only)
"""
import time
import threading
import queue
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

# YOLO import with graceful fallback
try:
    from ultralytics import YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False
    YOLO = None


@dataclass
class DetectorConfig:
    """Configuration for YoloRoiDetector."""
    conf_threshold: float = 0.35  # YOLO confidence threshold
    rate_limit_fps: float = 6.0  # Max processing FPS
    max_infer_ms: float = 250.0  # Backoff threshold
    max_roi_size: int = 320  # Max ROI dimension before downscale
    model_path: str = "yolov8n.pt"  # YOLO model path
    device: str = "cpu"  # Device (cpu, cuda, mps)
    classes: List[int] = field(default_factory=lambda: [0])  # Person class only


@dataclass
class DetectionResult:
    """Result from detection on a single zone."""
    zone_id: int
    detected: bool
    conf_max: float
    infer_ms: float
    roi_size: Tuple[int, int]
    detections_count: int


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring."""
    infer_ms_avg: float = 0.0
    fps_real: float = 0.0
    dropped_frames: int = 0
    total_frames: int = 0
    zones_processed: int = 0
    last_log_ts: float = 0.0


class YoloRoiDetector:
    """
    YOLO-based ROI-only Person Detector.

    Architecture:
    - Frame queue (size=1, latest only)
    - Worker thread for inference
    - Rate-limited processing
    - Automatic backoff on slow inference

    Integration:
    - Called by DJDetector.process_frame()
    - Updates VisionDJEngine via callback
    """

    def __init__(
        self,
        config: Optional[DetectorConfig] = None,
        on_detection: Optional[Callable[[int, bool, float], None]] = None,
    ):
        """
        Initialize YOLO ROI detector.

        Args:
            config: Detector configuration
            on_detection: Callback(zone_id, detected, conf) for detection results
        """
        self._config = config or DetectorConfig()
        self._on_detection = on_detection

        # Model state
        self._model: Optional["YOLO"] = None
        self._model_loaded = False
        self._model_error: Optional[str] = None

        # Frame queue (size=1, latest only)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)

        # Worker thread
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()

        # Rate limiting
        self._last_process_ts: float = 0.0
        self._min_interval: float = 1.0 / self._config.rate_limit_fps

        # Backoff state
        self._backoff_active = False
        self._backoff_factor = 1.0

        # Performance metrics
        self._metrics = PerformanceMetrics()
        self._infer_times: List[float] = []

        # Zone configurations (set by set_zones)
        self._zones: Dict[int, Dict[str, Any]] = {}

        # Degraded mode flag
        self._degraded = False

        print(f"[YoloRoiDetector] V9 initialized (YOLO available: {HAS_YOLO})")

    # ==================== MODEL MANAGEMENT ====================

    def load_model(self) -> bool:
        """
        Load YOLO model.

        Returns:
            True if model loaded successfully
        """
        if not HAS_YOLO:
            self._model_error = "ultralytics not installed"
            print(f"[YoloRoiDetector] ERROR: {self._model_error}")
            return False

        try:
            print(f"[YoloRoiDetector] Loading model: {self._config.model_path}")
            self._model = YOLO(self._config.model_path)
            self._model_loaded = True
            print(f"[YoloRoiDetector] Model loaded on {self._config.device}")
            return True
        except Exception as e:
            self._model_error = str(e)
            print(f"[YoloRoiDetector] Model load ERROR: {e}")
            return False

    def is_available(self) -> bool:
        """Check if detector is available (model loaded)."""
        return self._model_loaded and self._model is not None

    # ==================== ZONE MANAGEMENT ====================

    def set_zones(self, zones: List[Dict[str, Any]]) -> None:
        """
        Set detection zones.

        Args:
            zones: List of zone dicts with {id, x, y, width, height, visible}
        """
        with self._lock:
            self._zones.clear()
            for zone in zones:
                zone_id = zone.get("id")
                if zone_id and 1 <= zone_id <= 5:
                    self._zones[zone_id] = zone
            print(f"[YoloRoiDetector] {len(self._zones)} zones configured")

    def get_visible_zones(self) -> List[int]:
        """Get list of visible zone IDs."""
        with self._lock:
            return [z["id"] for z in self._zones.values() if z.get("visible", True)]

    # ==================== FRAME PROCESSING ====================

    def submit_frame(self, frame, zones: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Submit a frame for processing.
        Uses queue size=1, drops old frames if new one arrives.

        Args:
            frame: OpenCV frame (numpy array BGR)
            zones: Optional zone list (uses cached if None)

        Returns:
            True if frame was queued
        """
        if frame is None or not HAS_NUMPY:
            return False

        # Rate limiting check
        now = time.time()
        effective_interval = self._min_interval * self._backoff_factor
        if now - self._last_process_ts < effective_interval:
            self._metrics.dropped_frames += 1
            return False

        # Update zones if provided
        if zones:
            self.set_zones(zones)

        # Queue frame (drop old if queue full)
        try:
            # Try to remove old frame first
            try:
                self._frame_queue.get_nowait()
                self._metrics.dropped_frames += 1
            except queue.Empty:
                pass

            self._frame_queue.put_nowait(frame)
            return True
        except queue.Full:
            self._metrics.dropped_frames += 1
            return False

    def process_frame_sync(self, frame, zones: Optional[List[Dict[str, Any]]] = None) -> List[DetectionResult]:
        """
        Process a frame synchronously (blocking).
        For use when worker thread is not running.

        Args:
            frame: OpenCV frame
            zones: Zone configurations

        Returns:
            List of DetectionResult per zone
        """
        if frame is None or not self._model_loaded:
            return []

        if zones:
            self.set_zones(zones)

        results = []
        visible_zones = self.get_visible_zones()

        for zone_id in visible_zones:
            zone = self._zones.get(zone_id)
            if not zone:
                continue

            result = self._process_zone_roi(frame, zone)
            results.append(result)

            # Callback if set
            if self._on_detection and result:
                self._on_detection(result.zone_id, result.detected, result.conf_max)

        self._metrics.total_frames += 1
        self._metrics.zones_processed = len(results)
        self._last_process_ts = time.time()

        return results

    def _process_zone_roi(self, frame, zone: Dict[str, Any]) -> DetectionResult:
        """
        Process a single zone ROI.

        Args:
            frame: Full frame
            zone: Zone configuration

        Returns:
            DetectionResult for this zone
        """
        zone_id = zone.get("id", 0)
        x = zone.get("x", 0)
        y = zone.get("y", 0)
        w = zone.get("width", 100)
        h = zone.get("height", 100)

        # Extract ROI
        try:
            h_frame, w_frame = frame.shape[:2]
            x1 = max(0, min(x, w_frame))
            y1 = max(0, min(y, h_frame))
            x2 = max(0, min(x + w, w_frame))
            y2 = max(0, min(y + h, h_frame))

            roi = frame[y1:y2, x1:x2]

            if roi.size == 0:
                return DetectionResult(
                    zone_id=zone_id,
                    detected=False,
                    conf_max=0.0,
                    infer_ms=0.0,
                    roi_size=(0, 0),
                    detections_count=0,
                )

            roi_h, roi_w = roi.shape[:2]

        except Exception as e:
            print(f"[YoloRoiDetector] ROI extraction error Z{zone_id}: {e}")
            return DetectionResult(
                zone_id=zone_id,
                detected=False,
                conf_max=0.0,
                infer_ms=0.0,
                roi_size=(0, 0),
                detections_count=0,
            )

        # Downscale if ROI is too large
        scale = 1.0
        if max(roi_w, roi_h) > self._config.max_roi_size:
            scale = self._config.max_roi_size / max(roi_w, roi_h)
            import cv2
            roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

        # Run YOLO inference
        start_ts = time.time()
        try:
            results = self._model(
                roi,
                conf=self._config.conf_threshold,
                classes=self._config.classes,
                verbose=False,
                device=self._config.device,
            )
            infer_ms = (time.time() - start_ts) * 1000

        except Exception as e:
            print(f"[YoloRoiDetector] Inference error Z{zone_id}: {e}")
            self._set_degraded(True)
            return DetectionResult(
                zone_id=zone_id,
                detected=False,
                conf_max=0.0,
                infer_ms=0.0,
                roi_size=(roi_w, roi_h),
                detections_count=0,
            )

        # Update performance metrics
        self._update_infer_metrics(infer_ms)

        # Check backoff
        if infer_ms > self._config.max_infer_ms:
            self._activate_backoff()

        # Parse results
        detected = False
        conf_max = 0.0
        detections_count = 0

        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                detected = True
                detections_count = len(boxes)
                confs = boxes.conf.cpu().numpy() if hasattr(boxes.conf, 'cpu') else boxes.conf
                if len(confs) > 0:
                    conf_max = float(max(confs))

        return DetectionResult(
            zone_id=zone_id,
            detected=detected,
            conf_max=conf_max,
            infer_ms=infer_ms,
            roi_size=(roi_w, roi_h),
            detections_count=detections_count,
        )

    # ==================== WORKER THREAD ====================

    def start(self) -> bool:
        """
        Start the detector worker thread.

        Returns:
            True if started successfully
        """
        if self._running:
            return True

        if not self._model_loaded:
            if not self.load_model():
                return False

        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="YoloRoiDetector-Worker"
        )
        self._worker_thread.start()
        print("[YoloRoiDetector] Worker thread started")
        return True

    def stop(self) -> None:
        """Stop the detector worker thread."""
        self._running = False
        if self._worker_thread:
            # Push empty frame to unblock queue
            try:
                self._frame_queue.put_nowait(None)
            except queue.Full:
                pass
            self._worker_thread.join(timeout=2.0)
            self._worker_thread = None
        print("[YoloRoiDetector] Worker thread stopped")

    def _worker_loop(self) -> None:
        """Worker thread main loop."""
        while self._running:
            try:
                # Wait for frame with timeout
                try:
                    frame = self._frame_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if frame is None:
                    continue

                # Process all visible zones
                self.process_frame_sync(frame)

            except Exception as e:
                print(f"[YoloRoiDetector] Worker error: {e}")
                self._set_degraded(True)
                time.sleep(0.1)

    # ==================== PERFORMANCE MANAGEMENT ====================

    def _update_infer_metrics(self, infer_ms: float) -> None:
        """Update inference time metrics."""
        self._infer_times.append(infer_ms)
        if len(self._infer_times) > 30:
            self._infer_times.pop(0)

        self._metrics.infer_ms_avg = sum(self._infer_times) / len(self._infer_times)

        # Calculate real FPS
        now = time.time()
        if self._last_process_ts > 0:
            interval = now - self._last_process_ts
            if interval > 0:
                self._metrics.fps_real = 1.0 / interval

    def _activate_backoff(self) -> None:
        """Activate backoff due to slow inference."""
        if not self._backoff_active:
            self._backoff_active = True
            self._backoff_factor = min(self._backoff_factor * 1.5, 4.0)
            print(f"[YoloRoiDetector] BACKOFF activated (factor={self._backoff_factor:.1f})")

    def _deactivate_backoff(self) -> None:
        """Deactivate backoff."""
        if self._backoff_active:
            self._backoff_active = False
            self._backoff_factor = 1.0
            print("[YoloRoiDetector] BACKOFF deactivated")

    def _set_degraded(self, degraded: bool) -> None:
        """Set degraded mode."""
        if self._degraded != degraded:
            self._degraded = degraded
            print(f"[YoloRoiDetector] DEGRADED={degraded}")

    # ==================== METRICS & LOGGING ====================

    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        return {
            "infer_ms_avg": round(self._metrics.infer_ms_avg, 1),
            "fps_real": round(self._metrics.fps_real, 1),
            "dropped_frames": self._metrics.dropped_frames,
            "total_frames": self._metrics.total_frames,
            "zones_processed": self._metrics.zones_processed,
            "backoff_active": self._backoff_active,
            "backoff_factor": self._backoff_factor,
            "degraded": self._degraded,
            "model_loaded": self._model_loaded,
        }

    def log_metrics(self) -> None:
        """Log performance metrics (rate-limited to every 3s)."""
        now = time.time()
        if now - self._metrics.last_log_ts < 3.0:
            return

        self._metrics.last_log_ts = now
        m = self.get_metrics()

        visible_count = len(self.get_visible_zones())
        active_str = "BACKOFF" if m["backoff_active"] else "OK"

        print(
            f"[YoloRoiDetector] infer={m['infer_ms_avg']:.0f}ms "
            f"fps={m['fps_real']:.1f} "
            f"dropped={m['dropped_frames']} "
            f"zones={visible_count} "
            f"[{active_str}]"
        )

    # ==================== CONFIGURATION ====================

    def set_conf_threshold(self, threshold: float) -> None:
        """Set YOLO confidence threshold."""
        self._config.conf_threshold = max(0.1, min(0.9, threshold))

    def set_rate_limit_fps(self, fps: float) -> None:
        """Set rate limit FPS."""
        self._config.rate_limit_fps = max(1.0, min(30.0, fps))
        self._min_interval = 1.0 / self._config.rate_limit_fps

    def set_max_infer_ms(self, max_ms: float) -> None:
        """Set max inference time before backoff."""
        self._config.max_infer_ms = max(50.0, min(500.0, max_ms))

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return {
            "conf_threshold": self._config.conf_threshold,
            "rate_limit_fps": self._config.rate_limit_fps,
            "max_infer_ms": self._config.max_infer_ms,
            "max_roi_size": self._config.max_roi_size,
            "model_path": self._config.model_path,
            "device": self._config.device,
        }

    # ==================== CALLBACK MANAGEMENT ====================

    def set_on_detection(self, callback: Callable[[int, bool, float], None]) -> None:
        """
        Set detection callback.

        Args:
            callback: Function(zone_id, detected, conf) called for each zone
        """
        self._on_detection = callback

    # ==================== DEBUG UTILITIES ====================

    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information."""
        return {
            "model_loaded": self._model_loaded,
            "model_error": self._model_error,
            "has_yolo": HAS_YOLO,
            "has_numpy": HAS_NUMPY,
            "running": self._running,
            "zones_count": len(self._zones),
            "visible_zones": self.get_visible_zones(),
            "queue_size": self._frame_queue.qsize(),
            "metrics": self.get_metrics(),
            "config": self.get_config(),
        }
