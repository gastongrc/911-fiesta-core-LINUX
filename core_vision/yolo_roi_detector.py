"""
YoloRoiDetector V9.1 - YOLO-based ROI-only Person Detection
Phase 9.1: GPU acceleration + optimizations (P0+P1 fixes)

GOLDEN RULES:
1. Never freeze core/UI - drop frames, lower FPS, backoff if heavy
2. Detection ONLY on ROI crop (not full frame)
3. YOLO direct (ultralytics YOLOv8n)
4. Rate-limited processing (default 6 FPS)
5. Backoff if inference > 250ms
6. Queue size=1 (latest frame only, drop rest)

V9.1 Optimizations:
- Auto-select device (cuda > mps > cpu)
- model.eval() + torch.no_grad() for inference
- Warmup on load (3 dummy inferences)
- FP16 (half precision) on GPU
- Skip old frames (frame_age > threshold)
- Enhanced metrics logging

Performance Controls:
- downscale: Resize large ROIs before inference
- conf_threshold: YOLO confidence threshold (default 0.35)
- rate_limit_fps: Max processing rate (default 6 FPS)
- max_infer_ms: Backoff threshold (default 250ms)
- queue_size: Frame queue size (default 1, latest only)
- device: "auto" | "cuda" | "mps" | "cpu"
- fp16: Enable half precision on GPU (default True)
- skip_frame_age_ms: Skip frames older than this (default 250ms)
"""
import time
import threading
import queue
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field

# PyTorch import for device detection and optimizations
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    torch = None

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
    device: str = "auto"  # Device: "auto" | "cuda" | "mps" | "cpu"
    classes: List[int] = field(default_factory=lambda: [0])  # Person class only
    fp16: bool = True  # Enable FP16/half on GPU (default True)
    skip_frame_age_ms: float = 250.0  # Skip frames older than this (ms)


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
    total_zone_ms_avg: float = 0.0  # Total time for all zones
    loop_ms_avg: float = 0.0  # Full loop time
    frame_age_ms_avg: float = 0.0  # Average frame age
    fps_real: float = 0.0
    dropped_frames: int = 0
    skipped_old_frames: int = 0  # Frames skipped due to age
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
        self._zone_times: List[float] = []  # Total time for all zones
        self._frame_ages: List[float] = []  # Frame age samples
        self._loop_times: List[float] = []  # Full loop times

        # Zone configurations (set by set_zones)
        self._zones: Dict[int, Dict[str, Any]] = {}

        # Degraded mode flag
        self._degraded = False

        # Resolved device (set in load_model)
        self._resolved_device: str = "cpu"

        # Skip frame logging rate limiter
        self._last_skip_log_ts: float = 0.0

        print(f"[YoloRoiDetector] V9.1 initialized (YOLO={HAS_YOLO}, torch={HAS_TORCH})")

    # ==================== MODEL MANAGEMENT ====================

    def load_model(self) -> bool:
        """
        Load YOLO model with optimizations.

        V9.1 Optimizations:
        - Auto-select best device (cuda > mps > cpu)
        - Set model to eval mode
        - Run warmup inferences
        - Log device and CUDA info

        Returns:
            True if model loaded successfully
        """
        if not HAS_YOLO:
            self._model_error = "ultralytics not installed"
            print(f"[YoloRoiDetector] ERROR: {self._model_error}")
            return False

        try:
            # === STEP 1: Resolve device ===
            self._resolved_device = self._resolve_device()
            self._log_device_info()

            # === STEP 2: Load model ===
            print(f"[YoloRoiDetector] Loading model: {self._config.model_path}")
            self._model = YOLO(self._config.model_path)

            # === STEP 3: Set model to eval mode ===
            try:
                if hasattr(self._model, 'model') and self._model.model is not None:
                    self._model.model.eval()
                    print("[YoloRoiDetector] model.eval() OK")
            except Exception as e:
                print(f"[YoloRoiDetector] model.eval() warning: {e}")

            # === STEP 4: Warmup ===
            self._run_warmup()

            self._model_loaded = True
            fp16_str = "FP16" if (self._config.fp16 and self._resolved_device == "cuda") else "FP32"
            print(f"[YoloRoiDetector] Model ready: device={self._resolved_device} {fp16_str} warmup=OK")
            return True

        except Exception as e:
            self._model_error = str(e)
            print(f"[YoloRoiDetector] Model load ERROR: {e}")
            return False

    def _resolve_device(self) -> str:
        """
        Resolve the best available device.

        Priority: cuda > mps > cpu

        Returns:
            Device string ("cuda", "mps", or "cpu")
        """
        configured = self._config.device.lower().strip()

        # If explicit device configured (not "auto"), use it
        if configured in ("cuda", "mps", "cpu"):
            # Validate CUDA is actually available if requested
            if configured == "cuda":
                if HAS_TORCH and torch.cuda.is_available():
                    return "cuda"
                else:
                    print("[YoloRoiDetector] WARNING: cuda requested but not available, falling back to cpu")
                    return "cpu"
            elif configured == "mps":
                if HAS_TORCH and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                    return "mps"
                else:
                    print("[YoloRoiDetector] WARNING: mps requested but not available, falling back to cpu")
                    return "cpu"
            return configured

        # Auto-detect best device
        if HAS_TORCH:
            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"

        return "cpu"

    def _log_device_info(self) -> None:
        """Log device and CUDA information at boot."""
        print(f"\n{'='*60}")
        print("[YoloRoiDetector] DEVICE DIAGNOSTICS")
        print(f"{'='*60}")

        if HAS_TORCH:
            print(f"  torch.version       = {torch.__version__}")
            print(f"  torch.cuda.available= {torch.cuda.is_available()}")

            if torch.cuda.is_available():
                print(f"  cuda.device_count   = {torch.cuda.device_count()}")
                print(f"  cuda.device_name    = {torch.cuda.get_device_name(0)}")
                try:
                    cap = torch.cuda.get_device_capability(0)
                    print(f"  cuda.capability     = {cap[0]}.{cap[1]}")
                    mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    print(f"  cuda.memory         = {mem_gb:.1f} GB")
                except Exception:
                    pass

            # MPS info
            if hasattr(torch.backends, 'mps'):
                print(f"  mps.available       = {torch.backends.mps.is_available()}")
        else:
            print("  torch: NOT AVAILABLE")

        print(f"  config.device       = {self._config.device}")
        print(f"  resolved_device     = {self._resolved_device}")
        print(f"  config.fp16         = {self._config.fp16}")
        print(f"{'='*60}\n")

    def _run_warmup(self) -> None:
        """Run warmup inferences to initialize CUDA kernels."""
        if not HAS_NUMPY:
            return

        print(f"[YoloRoiDetector] Running warmup on {self._resolved_device}...")

        # Create dummy image (320x320 black)
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)

        # Determine if we should use FP16
        use_half = self._config.fp16 and self._resolved_device == "cuda"

        # Run 3 warmup inferences
        warmup_times = []
        for i in range(3):
            start = time.perf_counter()
            try:
                if HAS_TORCH:
                    with torch.no_grad():
                        self._model(
                            dummy,
                            device=self._resolved_device,
                            verbose=False,
                            half=use_half,
                        )
                else:
                    self._model(
                        dummy,
                        device=self._resolved_device,
                        verbose=False,
                    )
                elapsed_ms = (time.perf_counter() - start) * 1000
                warmup_times.append(elapsed_ms)
            except Exception as e:
                print(f"[YoloRoiDetector] Warmup {i+1} error: {e}")

        if warmup_times:
            avg_ms = sum(warmup_times) / len(warmup_times)
            print(f"[YoloRoiDetector] Warmup complete: {len(warmup_times)} runs, avg={avg_ms:.1f}ms")

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
                # Support zones 1-10 (DJ uses 1-5, Artist uses 1-8)
                if zone_id and 1 <= zone_id <= 10:
                    self._zones[zone_id] = zone
            print(f"[YoloRoiDetector] {len(self._zones)} zones configured (ids={list(self._zones.keys())})")

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

    def process_frame_sync(
        self,
        frame,
        zones: Optional[List[Dict[str, Any]]] = None,
        frame_ts: Optional[float] = None,
    ) -> List[DetectionResult]:
        """
        Process a frame synchronously (blocking).
        For use when worker thread is not running.

        V9.1: Added frame_ts for frame age calculation and skip logic.

        Args:
            frame: OpenCV frame
            zones: Zone configurations
            frame_ts: Timestamp when frame was captured (for age calculation)

        Returns:
            List of DetectionResult per zone
        """
        if frame is None or not self._model_loaded:
            return []

        loop_start = time.perf_counter()

        # === Frame age check (P1 fix) ===
        frame_age_ms = 0.0
        if frame_ts is not None:
            frame_age_ms = (time.time() - frame_ts) * 1000
            self._update_frame_age_metric(frame_age_ms)

            # Skip old frames
            if frame_age_ms > self._config.skip_frame_age_ms:
                self._metrics.skipped_old_frames += 1
                self._log_skip_old_frame(frame_age_ms)
                return []

        if zones:
            self.set_zones(zones)

        results = []
        visible_zones = self.get_visible_zones()
        zone_start = time.perf_counter()

        for zone_id in visible_zones:
            zone = self._zones.get(zone_id)
            if not zone:
                continue

            result = self._process_zone_roi(frame, zone)
            results.append(result)

            # Callback if set
            if self._on_detection and result:
                self._on_detection(result.zone_id, result.detected, result.conf_max)

        zone_elapsed_ms = (time.perf_counter() - zone_start) * 1000
        self._update_zone_time_metric(zone_elapsed_ms)

        self._metrics.total_frames += 1
        self._metrics.zones_processed = len(results)
        self._last_process_ts = time.time()

        # Update loop time metric
        loop_elapsed_ms = (time.perf_counter() - loop_start) * 1000
        self._update_loop_time_metric(loop_elapsed_ms)

        return results

    def _log_skip_old_frame(self, frame_age_ms: float) -> None:
        """Log skipped old frame (rate-limited to every 5s)."""
        now = time.time()
        if now - self._last_skip_log_ts >= 5.0:
            self._last_skip_log_ts = now
            print(f"[YoloRoiDetector] SKIP old frame age={frame_age_ms:.0f}ms (threshold={self._config.skip_frame_age_ms}ms)")

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

        # Run YOLO inference with optimizations (P0+P1)
        start_ts = time.perf_counter()
        try:
            # Determine if we should use FP16
            use_half = self._config.fp16 and self._resolved_device == "cuda"

            # Use torch.no_grad() for inference (P0 fix)
            if HAS_TORCH:
                with torch.no_grad():
                    results = self._model(
                        roi,
                        conf=self._config.conf_threshold,
                        classes=self._config.classes,
                        verbose=False,
                        device=self._resolved_device,
                        half=use_half,
                    )
            else:
                results = self._model(
                    roi,
                    conf=self._config.conf_threshold,
                    classes=self._config.classes,
                    verbose=False,
                    device=self._resolved_device,
                )
            infer_ms = (time.perf_counter() - start_ts) * 1000

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

    def _update_zone_time_metric(self, zone_ms: float) -> None:
        """Update total zone processing time metric."""
        self._zone_times.append(zone_ms)
        if len(self._zone_times) > 30:
            self._zone_times.pop(0)
        self._metrics.total_zone_ms_avg = sum(self._zone_times) / len(self._zone_times)

    def _update_loop_time_metric(self, loop_ms: float) -> None:
        """Update loop time metric."""
        self._loop_times.append(loop_ms)
        if len(self._loop_times) > 30:
            self._loop_times.pop(0)
        self._metrics.loop_ms_avg = sum(self._loop_times) / len(self._loop_times)

    def _update_frame_age_metric(self, age_ms: float) -> None:
        """Update frame age metric."""
        self._frame_ages.append(age_ms)
        if len(self._frame_ages) > 30:
            self._frame_ages.pop(0)
        self._metrics.frame_age_ms_avg = sum(self._frame_ages) / len(self._frame_ages)

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
            "total_zone_ms_avg": round(self._metrics.total_zone_ms_avg, 1),
            "loop_ms_avg": round(self._metrics.loop_ms_avg, 1),
            "frame_age_ms_avg": round(self._metrics.frame_age_ms_avg, 1),
            "fps_real": round(self._metrics.fps_real, 1),
            "dropped_frames": self._metrics.dropped_frames,
            "skipped_old_frames": self._metrics.skipped_old_frames,
            "total_frames": self._metrics.total_frames,
            "zones_processed": self._metrics.zones_processed,
            "backoff_active": self._backoff_active,
            "backoff_factor": self._backoff_factor,
            "degraded": self._degraded,
            "model_loaded": self._model_loaded,
            "device": self._resolved_device,
            "fp16": self._config.fp16 and self._resolved_device == "cuda",
        }

    def log_metrics(self) -> None:
        """Log performance metrics (rate-limited to every 1s for V9.1)."""
        now = time.time()
        if now - self._metrics.last_log_ts < 1.0:
            return

        self._metrics.last_log_ts = now
        m = self.get_metrics()

        visible_count = len(self.get_visible_zones())
        status_str = "BACKOFF" if m["backoff_active"] else "OK"
        device_str = f"{m['device']}" + ("/FP16" if m['fp16'] else "")

        # V9.1: Enhanced metrics logging
        print(
            f"[YoloRoiDetector] zones={visible_count} "
            f"infer={m['infer_ms_avg']:.0f}ms "
            f"total_zone={m['total_zone_ms_avg']:.0f}ms "
            f"loop={m['loop_ms_avg']:.0f}ms "
            f"fps={m['fps_real']:.1f} "
            f"age={m['frame_age_ms_avg']:.0f}ms "
            f"skip={m['skipped_old_frames']} "
            f"[{device_str}] [{status_str}]"
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
            "device_resolved": self._resolved_device,
            "fp16": self._config.fp16,
            "skip_frame_age_ms": self._config.skip_frame_age_ms,
        }

    def set_device(self, device: str) -> None:
        """Set device (requires model reload)."""
        self._config.device = device

    def set_fp16(self, enabled: bool) -> None:
        """Set FP16 mode (requires model reload for full effect)."""
        self._config.fp16 = enabled

    def set_skip_frame_age_ms(self, ms: float) -> None:
        """Set skip frame age threshold in ms."""
        self._config.skip_frame_age_ms = max(50.0, min(1000.0, ms))

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
            "has_torch": HAS_TORCH,
            "running": self._running,
            "zones_count": len(self._zones),
            "visible_zones": self.get_visible_zones(),
            "queue_size": self._frame_queue.qsize(),
            "device_resolved": self._resolved_device,
            "metrics": self.get_metrics(),
            "config": self.get_config(),
        }
