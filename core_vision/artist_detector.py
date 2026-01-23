"""
Artist Detector V9 - Facade for VisionArtistEngine + YoloRoiDetector
Maintains backward-compatible API while using V9 engine internally.
YOLO-based ROI-only detection for 8-zone artist presence tracking.

Replaces old ArtistTracker (HOG-based, blocking, single-zone).
"""
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from .vision_artist_engine import VisionArtistEngine, ArtistEngineConfig
from .yolo_roi_detector import YoloRoiDetector, DetectorConfig

if TYPE_CHECKING:
    from core.cues import FamilyManager


class ArtistDetector:
    """
    V9 Artist Detector - Facade for VisionArtistEngine + YoloRoiDetector.

    Maintains backward-compatible API for integration with:
    - VisionManager
    - CameraLoop
    - VisionArtistTab
    - SystemBridge

    Architecture:
    - YoloRoiDetector: YOLO-based person detection on ROI only
    - VisionArtistEngine: Multi-zone state machine with disappear delay
    - Non-blocking cue firing via event queue

    Golden Rules:
    - Never freeze core/UI
    - Detection only within ROI of each zone
    - YOLO direct (ultralytics)
    - 8 zones (C72-C79)
    """

    def __init__(self, config, vision_state, cue_engine=None):
        """
        Initialize Artist Detector with V9 engine and YOLO detector.

        Args:
            config (VisionConfig): Vision system configuration
            vision_state (VisionState): Shared vision state
            cue_engine: Legacy CueEngine (not used in V9)
        """
        self.config = config
        self.vision_state = vision_state
        self.cue_engine = cue_engine

        # Load config from VisionConfig
        artist_config = config.get_artist_config()
        self.enabled = artist_config.get("enabled", False)
        self.zones = artist_config.get("zones", [])
        self.disappear_delay = artist_config.get("disappear_delay", 2.0)

        # V9 Engine configuration
        engine_config = ArtistEngineConfig(
            disappear_delay=self.disappear_delay,
            enabled=self.enabled,
            conf_threshold=artist_config.get("conf_threshold", 0.35),
            target_fps=artist_config.get("target_fps", 6.0),
        )
        self._engine = VisionArtistEngine(config=engine_config)
        self._engine.set_zones(self.zones)

        # YOLO detector configuration (V9.1: GPU + optimizations)
        detector_config = DetectorConfig(
            conf_threshold=artist_config.get("conf_threshold", 0.35),
            rate_limit_fps=artist_config.get("target_fps", 6.0),
            max_infer_ms=artist_config.get("max_infer_ms", 250.0),
            max_roi_size=artist_config.get("max_roi_size", 320),
            device=artist_config.get("device", "auto"),  # V9.1: auto-device
            fp16=artist_config.get("fp16", True),  # V9.1: FP16 on GPU
            skip_frame_age_ms=artist_config.get("skip_frame_age_ms", 250.0),  # V9.1: skip old frames
        )

        # Initialize detector with callback to engine
        self._detector = YoloRoiDetector(
            config=detector_config,
            on_detection=self._on_zone_detection,
        )
        self._detector.set_zones(self.zones)

        # Try to load YOLO model
        self._detector_available = self._detector.load_model()

        # Update VisionState
        self.vision_state.set_tracking_enabled(self.enabled)
        self.vision_state.set_artist_zones_count(len(self.zones))

        # Log zone IDs for verification
        zone_ids = [z.get("id") for z in self.zones]
        print(f"[ArtistDetector] V9 initialized: zones={len(self.zones)} ids={zone_ids}, enabled={self.enabled}, YOLO={self._detector_available}")

        # Periodic log state
        self._last_visible_log_ts = 0.0

    def _on_zone_detection(self, zone_id: int, detected: bool, conf: float) -> None:
        """
        Callback from YoloRoiDetector for each zone detection.

        Args:
            zone_id: Zone ID
            detected: Whether person was detected
            conf: Detection confidence
        """
        self._engine.update_detection(zone_id, detected, conf)

    def _log_visible_zones(self, visible_zones: list) -> None:
        """Log visible zones periodically (every 30 seconds)."""
        import time
        now = time.time()
        if now - self._last_visible_log_ts >= 30.0:
            self._last_visible_log_ts = now
            print(f"[ArtistDetector] processing visible_zones={len(visible_zones)} ids={visible_zones}")

    def process_frame(self, frame, frame_ts: float = None) -> Dict[str, Any]:
        """
        Process a frame for artist detection.
        Uses YOLO ROI-only detection and V9 state machine.

        Safety: Never crashes, enters degraded mode on errors.

        Args:
            frame: OpenCV frame (numpy array BGR)
            frame_ts: Frame timestamp for age calculation (V9.1)

        Returns:
            dict: Detection state
        """
        if frame is None:
            return self.get_state()

        if not self.enabled:
            return self.get_state()

        # Check if any zones are visible
        visible_zones = self._engine.get_visible_zones()
        if not visible_zones:
            # No visible zones - no processing needed
            return self.get_state()

        # Log visible zones periodically (every 30s)
        self._log_visible_zones(visible_zones)

        # Run YOLO detection on visible zones with safety wrapper
        try:
            if self._detector_available:
                zones_config = [
                    z for z in self.zones
                    if z.get("id") in visible_zones
                ]
                # V9.1: Pass frame timestamp for age-based skip
                self._detector.process_frame_sync(frame, zones_config, frame_ts=frame_ts)

                # Log metrics periodically
                self._detector.log_metrics()

            # Mark frame as processed (for watchdog)
            self._engine.mark_frame_processed()

        except Exception as e:
            # Report error but don't crash
            self._engine.report_error(e)
            print(f"[ArtistDetector] ERROR in detection: {e}")

        # Tick the state machine (always runs, even on detector error)
        try:
            self._engine.tick()

            # Process cue queue (non-blocking)
            self._engine.process_cue_queue()
        except Exception as e:
            self._engine.report_error(e)
            print(f"[ArtistDetector] ERROR in engine tick: {e}")

        # Update VisionState
        active_zones = self._engine.get_active_zones()
        active_zone = active_zones[0] if active_zones else None
        state_str = "active" if active_zones else "idle"
        self.vision_state.update_tracking(zone=active_zone, state=state_str)

        return self.get_state()

    def get_state(self) -> Dict[str, Any]:
        """
        Get current detector state.

        Returns:
            dict: Full state for UI/monitoring
        """
        engine_state = self._engine.get_state()
        active_zones = engine_state.get("active_zones", [])

        # Get detector metrics
        detector_metrics = {}
        if self._detector:
            detector_metrics = self._detector.get_metrics()

        return {
            "enabled": self.enabled,
            "active_zone": active_zones[0] if active_zones else None,
            "active_zones": active_zones,
            "state": "disabled" if not self.enabled else ("active" if active_zones else "idle"),
            "zones_count": len(self.zones),
            "zones": self.zones,
            "zones_visible": len(self._engine.get_visible_zones()),
            "current_cue": None,  # Managed by engine
            "detector_available": self._detector_available,
            "degraded": engine_state.get("degraded", False) or detector_metrics.get("degraded", False),
            "infer_ms": detector_metrics.get("infer_ms_avg", 0),
            "fps_real": detector_metrics.get("fps_real", 0),
            "dropped_frames": detector_metrics.get("dropped_frames", 0),
        }

    def set_zones(self, zones: List[Dict[str, Any]]):
        """
        Set detection zones and persist to config.

        Args:
            zones: List of zone dicts [{id, x, y, width, height, visible}, ...]
        """
        self.zones = zones
        self._engine.set_zones(zones)
        self._detector.set_zones(zones)
        self.config.set_artist_zones(zones)
        self.vision_state.set_artist_zones_count(len(zones))
        print(f"[ArtistDetector] Zones updated: {len(zones)} zones")

    def set_zone_visible(self, zone_id: int, visible: bool):
        """
        Set visibility for a specific zone.

        Args:
            zone_id: Zone ID (1-8)
            visible: Whether zone should process detections
        """
        self._engine.set_zone_visible(zone_id, visible)

        # Update local zones list
        for zone in self.zones:
            if zone.get("id") == zone_id:
                zone["visible"] = visible
                break

    def set_enabled(self, enabled: bool, persist: bool = True):
        """
        Enable/disable detector.

        V9.2 FIX: Added persist parameter for calendar vs UI control.
        - persist=True: Save to config (user preference)
        - persist=False: Runtime only (calendar temporary state)
        """
        self.enabled = enabled
        self._engine.set_enabled(enabled)
        if persist:
            self.config.set_artist_enabled(enabled)
        self.vision_state.set_tracking_enabled(enabled)
        persist_str = "persisted" if persist else "runtime"
        print(f"[ArtistDetector] Enabled={enabled} ({persist_str})")

    def set_cue_engine(self, cue_engine):
        """Legacy: Store CueEngine reference."""
        self.cue_engine = cue_engine
        print("[ArtistDetector] CueEngine connected (legacy)")

    def set_family_manager(self, family_manager: "FamilyManager"):
        """
        Connect FamilyManager for canonical cue firing.

        Args:
            family_manager: FamilyManager instance
        """
        self._engine.set_family_manager(family_manager)
        print("[ArtistDetector] FamilyManager connected (V9)")

    def set_disappear_delay(self, delay: float):
        """Set disappear delay in seconds."""
        self.disappear_delay = delay
        self._engine.set_disappear_delay(delay)

    def set_conf_threshold(self, threshold: float):
        """Set YOLO confidence threshold."""
        self._engine.set_conf_threshold(threshold)
        self._detector.set_conf_threshold(threshold)

    def set_target_fps(self, fps: float):
        """Set target processing FPS."""
        self._engine.set_target_fps(fps)
        self._detector.set_rate_limit_fps(fps)

    def get_engine(self) -> VisionArtistEngine:
        """Get underlying V9 engine for advanced access."""
        return self._engine

    def get_detector(self) -> YoloRoiDetector:
        """Get underlying YOLO detector for advanced access."""
        return self._detector

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        return self._detector.get_metrics() if self._detector else {}

    def _test_fire_zone(self, zone_id: int = 1, force_off: bool = False) -> Dict[str, Any]:
        """
        Diagnostic: Test fire/kill for a zone.

        Args:
            zone_id: Zone ID to test (1-8)
            force_off: If True, kill instead of fire

        Returns:
            dict: Test result
        """
        if force_off:
            success = self._engine.test_kill_all()
            return {"test_result": "OFF_SUCCESS" if success else "OFF_ERROR"}
        else:
            success = self._engine.test_fire_zone(zone_id)
            return {"test_result": "ON_SUCCESS" if success else "ON_ERROR"}

    def start_detector_thread(self) -> bool:
        """
        Start YOLO detector worker thread for async processing.

        Returns:
            True if started successfully
        """
        if not self._detector_available:
            return False
        return self._detector.start()

    def stop_detector_thread(self) -> None:
        """Stop YOLO detector worker thread."""
        if self._detector:
            self._detector.stop()

    def check_watchdog(self) -> Dict[str, Any]:
        """
        Check engine watchdog status.
        Should be called periodically to detect stuck processing.

        Returns:
            Dict with watchdog status
        """
        return self._engine.check_watchdog()

    def get_health(self) -> Dict[str, Any]:
        """
        Get overall health status of the artist detector.

        Returns:
            Dict with health metrics from engine and detector
        """
        engine_health = self._engine.get_health()
        detector_metrics = self._detector.get_metrics() if self._detector else {}

        return {
            "engine": engine_health,
            "detector": {
                "available": self._detector_available,
                "metrics": detector_metrics,
            },
            "overall": {
                "healthy": not engine_health.get("degraded", True) and not detector_metrics.get("degraded", True),
                "enabled": self.enabled,
            },
        }

    # ==================== LEGACY COMPATIBILITY ====================
    # These methods maintain compatibility with old ArtistTracker API

    def set_mode_show_artist(self, enabled: bool):
        """Legacy: mode_show_artist no longer needed (no calendar gating)."""
        # V9 doesn't use calendar gating - always process if enabled
        pass

    @property
    def mode_show_artist(self) -> bool:
        """Legacy: Always returns True (no calendar gating in V9)."""
        return True

    @property
    def detector_available(self) -> bool:
        """Legacy: Alias for _detector_available."""
        return self._detector_available
