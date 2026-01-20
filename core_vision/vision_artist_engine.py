"""
VisionArtistEngine V9 - Multi-Zone Artist Detection Engine
Phase 9: YOLO-based ROI-only detection with 8-zone support

GOLDEN RULES:
1. Never freeze core/UI - drop frames, lower FPS, backoff if heavy
2. Detection only within ROI of each zone (not full frame)
3. YOLO direct (ultralytics) - no HOG
4. Clear, minimal, testable architecture
5. Multi-zone real: 1..8 zones, each can fire its cue simultaneously

Cue Mapping (C72-C79):
    ARTIST_1 => C72
    ARTIST_2 => C73
    ARTIST_3 => C74
    ARTIST_4 => C75
    ARTIST_5 => C76
    ARTIST_6 => C77
    ARTIST_7 => C78
    ARTIST_8 => C79
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Callable, TYPE_CHECKING
import time
import threading
import queue

from core.cues import FAMILIA_ARTIST, ARTIST_CUE_MAP

if TYPE_CHECKING:
    from core.cues import FamilyManager


@dataclass
class ArtistZoneConfig:
    """Configuration for a single artist detection zone."""
    id: int
    x: int
    y: int
    width: int
    height: int
    visible: bool = True
    cue_id: Optional[int] = None

    def __post_init__(self):
        # Auto-assign cue_id from ARTIST_CUE_MAP if not provided
        if self.cue_id is None:
            self.cue_id = ARTIST_CUE_MAP.get(self.id)

    def get_roi_slice(self):
        """Returns (y_start, y_end, x_start, x_end) for numpy slicing."""
        return (self.y, self.y + self.height, self.x, self.x + self.width)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "visible": self.visible,
            "cue_id": self.cue_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtistZoneConfig":
        return cls(
            id=data.get("id", 1),
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", data.get("w", 100)),
            height=data.get("height", data.get("h", 100)),
            visible=data.get("visible", True),
            cue_id=data.get("cue_id"),
        )


@dataclass
class ArtistZoneState:
    """Runtime state for a single artist zone."""
    zone_id: int
    active: bool = False  # True if person detected and cue is ON
    last_seen_ts: float = 0.0  # Last time person was seen in this zone
    last_fire_ts: float = 0.0  # Last time cue was fired for this zone
    detected: bool = False  # Current frame detection result
    conf: float = 0.0  # Detection confidence


@dataclass
class ArtistEngineConfig:
    """Global artist engine configuration."""
    disappear_delay: float = 2.0  # Seconds before turning OFF after person leaves
    conf_threshold: float = 0.35  # YOLO confidence threshold
    target_fps: float = 6.0  # Target processing FPS
    max_infer_ms: float = 250.0  # Max inference time before backoff
    enabled: bool = False  # Engine enabled flag
    watchdog_timeout: float = 2.0  # Seconds without frames before marking degraded


class ArtistCueEvent:
    """Non-blocking cue event for queue processing."""
    __slots__ = ('zone_id', 'event_type', 'cue_id', 'timestamp')

    def __init__(self, zone_id: int, event_type: str, cue_id: int):
        self.zone_id = zone_id
        self.event_type = event_type  # "ON" or "OFF"
        self.cue_id = cue_id
        self.timestamp = time.time()


class VisionArtistEngine:
    """
    V9 Multi-Zone Artist Detection Engine.

    Architecture:
    - Maintains zones (id, x,y,w,h, visible, cue_id)
    - Maintains ZoneState per zone (active, last_seen_ts, last_fire_ts)
    - tick(now, detections) decides ON/OFF per zone based on detection + delay

    Integration:
    - Detector calls update_detection(zone_id, detected, conf)
    - Engine calls tick() to process state machine
    - CueBridge receives events via queue (non-blocking)
    """

    MAX_ZONES = 8  # Artist supports 8 zones

    def __init__(self, config: Optional[ArtistEngineConfig] = None):
        self._config = config or ArtistEngineConfig()
        self._zones: Dict[int, ArtistZoneConfig] = {}
        self._states: Dict[int, ArtistZoneState] = {}
        self._lock = threading.RLock()

        # Cue event queue (non-blocking bridge)
        self._cue_queue: queue.Queue[ArtistCueEvent] = queue.Queue(maxsize=100)

        # FamilyManager for canonical cue firing (set externally)
        self._family_manager: Optional["FamilyManager"] = None

        # Callbacks for UI/monitoring
        self._on_state_change: Optional[Callable[[int, bool], None]] = None

        # Performance metrics
        self._last_tick_ts: float = 0.0
        self._tick_count: int = 0
        self._last_frame_ts: float = 0.0  # Last frame processing time

        # Degraded mode flag
        self._degraded: bool = False

        # Watchdog state
        self._watchdog_triggered: bool = False
        self._watchdog_last_check: float = 0.0
        self._original_fps: float = self._config.target_fps

        # Safety: Track consecutive errors
        self._consecutive_errors: int = 0
        self._max_consecutive_errors: int = 5

        print("[VisionArtistEngine] V9 initialized (8 zones)")

    # ==================== ZONE MANAGEMENT ====================

    def set_zones(self, zones: List[Dict[str, Any]]) -> None:
        """
        Set detection zones from config dict list.

        Args:
            zones: List of zone dicts [{id, x, y, width, height, visible}, ...]
        """
        with self._lock:
            self._zones.clear()
            self._states.clear()

            for zone_data in zones:
                zone = ArtistZoneConfig.from_dict(zone_data)
                if 1 <= zone.id <= self.MAX_ZONES:
                    self._zones[zone.id] = zone
                    self._states[zone.id] = ArtistZoneState(zone_id=zone.id)

            print(f"[VisionArtistEngine] {len(self._zones)} zones configured")

    def get_zones(self) -> List[Dict[str, Any]]:
        """Get current zone configurations."""
        with self._lock:
            return [z.to_dict() for z in self._zones.values()]

    def set_zone_visible(self, zone_id: int, visible: bool) -> None:
        """
        Set zone visibility. If visible=False, immediately turn OFF.

        Args:
            zone_id: Zone ID (1-8)
            visible: Whether zone should process detections
        """
        with self._lock:
            zone = self._zones.get(zone_id)
            if zone:
                zone.visible = visible
                if not visible:
                    # Immediate OFF when hidden
                    self._turn_off_zone(zone_id)
                print(f"[VisionArtistEngine] Zone {zone_id} visible={visible}")

    def get_visible_zones(self) -> List[int]:
        """Get list of visible zone IDs."""
        with self._lock:
            return [z.id for z in self._zones.values() if z.visible]

    # ==================== DETECTION UPDATE ====================

    def update_detection(self, zone_id: int, detected: bool, conf: float = 0.0) -> None:
        """
        Update detection result for a zone.
        Called by YoloRoiDetector after processing ROI.

        Args:
            zone_id: Zone ID
            detected: Whether person was detected
            conf: Detection confidence (0-1)
        """
        with self._lock:
            state = self._states.get(zone_id)
            zone = self._zones.get(zone_id)

            if not state or not zone or not zone.visible:
                return

            state.detected = detected
            state.conf = conf

            if detected:
                state.last_seen_ts = time.time()

    # ==================== STATE MACHINE TICK ====================

    def tick(self, now: Optional[float] = None) -> Dict[str, Any]:
        """
        Process state machine for all zones.
        Decides ON/OFF based on detection and disappear_delay.

        Args:
            now: Current timestamp (defaults to time.time())

        Returns:
            Dict with tick results and active zones
        """
        now = now or time.time()
        self._last_tick_ts = now
        self._tick_count += 1

        if not self._config.enabled:
            return {"enabled": False, "active_zones": []}

        active_zones = []
        events_fired = []

        with self._lock:
            for zone_id, state in self._states.items():
                zone = self._zones.get(zone_id)
                if not zone or not zone.visible:
                    # If zone became invisible, ensure it's OFF
                    if state.active:
                        self._turn_off_zone(zone_id)
                    continue

                # Calculate time since last detection
                time_since_seen = now - state.last_seen_ts if state.last_seen_ts > 0 else float('inf')

                if state.detected or time_since_seen <= self._config.disappear_delay:
                    # Person detected OR within grace period: should be ON
                    if not state.active:
                        # Transition to ON
                        event = self._turn_on_zone(zone_id, now)
                        if event:
                            events_fired.append(event)
                    active_zones.append(zone_id)
                else:
                    # No detection and grace period expired: should be OFF
                    if state.active:
                        event = self._turn_off_zone(zone_id)
                        if event:
                            events_fired.append(event)

        return {
            "enabled": self._config.enabled,
            "active_zones": active_zones,
            "events_fired": len(events_fired),
            "tick_count": self._tick_count,
            "degraded": self._degraded,
        }

    def _turn_on_zone(self, zone_id: int, now: float) -> Optional[ArtistCueEvent]:
        """Turn ON a zone (fire cue)."""
        state = self._states.get(zone_id)
        zone = self._zones.get(zone_id)

        if not state or not zone or not zone.cue_id:
            return None

        state.active = True
        state.last_fire_ts = now

        event = ArtistCueEvent(zone_id, "ON", zone.cue_id)
        self._enqueue_event(event)

        print(f"[VisionArtistEngine] ARTIST ON zone={zone_id} C{zone.cue_id} (detected=True)")

        if self._on_state_change:
            try:
                self._on_state_change(zone_id, True)
            except Exception:
                pass

        return event

    def _turn_off_zone(self, zone_id: int) -> Optional[ArtistCueEvent]:
        """Turn OFF a zone (kill cue)."""
        state = self._states.get(zone_id)
        zone = self._zones.get(zone_id)

        if not state:
            return None

        if not state.active:
            return None  # Already OFF

        # Calculate time since last detection for logging
        now = time.time()
        last_seen_age = now - state.last_seen_ts if state.last_seen_ts > 0 else 0.0

        state.active = False
        state.detected = False

        if zone and zone.cue_id:
            event = ArtistCueEvent(zone_id, "OFF", zone.cue_id)
            self._enqueue_event(event)
            print(f"[VisionArtistEngine] ARTIST OFF zone={zone_id} C{zone.cue_id} (last_seen_age={last_seen_age:.1f}s)")

            if self._on_state_change:
                try:
                    self._on_state_change(zone_id, False)
                except Exception:
                    pass

            return event

        return None

    def _enqueue_event(self, event: ArtistCueEvent) -> bool:
        """Enqueue cue event for non-blocking processing."""
        try:
            self._cue_queue.put_nowait(event)
            return True
        except queue.Full:
            print(f"[VisionArtistEngine] WARNING: Cue queue full, dropping event {event.event_type} Z{event.zone_id}")
            return False

    # ==================== CUE BRIDGE ====================

    def process_cue_queue(self) -> int:
        """
        Process pending cue events via FamilyManager.
        Should be called from main thread tick (non-blocking).

        Uses activate_zone/deactivate_zone for per-zone ON/OFF.
        - ON fires only this zone's cue (no kill of other zones)
        - OFF kills only this zone's cue (not entire family)

        Returns:
            Number of events processed
        """
        if not self._family_manager:
            return 0

        processed = 0
        while True:
            try:
                event = self._cue_queue.get_nowait()
            except queue.Empty:
                break

            try:
                if event.event_type == "ON":
                    # Fire only this zone's cue, don't kill other zones
                    self._family_manager.activate_zone(FAMILIA_ARTIST, event.zone_id, source="vision_artist")
                elif event.event_type == "OFF":
                    # Kill only this zone's cue, not entire family
                    self._family_manager.deactivate_zone(FAMILIA_ARTIST, event.zone_id, source="vision_artist")
                processed += 1
            except Exception as e:
                print(f"[VisionArtistEngine] ERROR processing cue event: {e}")

        return processed

    def set_family_manager(self, family_manager: "FamilyManager") -> None:
        """Set FamilyManager for cue firing."""
        self._family_manager = family_manager
        print("[VisionArtistEngine] FamilyManager connected")

    # ==================== CONFIGURATION ====================

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the engine."""
        with self._lock:
            if self._config.enabled != enabled:
                self._config.enabled = enabled
                print(f"[VisionArtistEngine] enabled={enabled}")

                if not enabled:
                    # Turn off all active zones
                    for zone_id in list(self._states.keys()):
                        self._turn_off_zone(zone_id)

    def set_disappear_delay(self, delay: float) -> None:
        """Set disappear delay in seconds."""
        self._config.disappear_delay = max(0.5, min(10.0, delay))
        print(f"[VisionArtistEngine] disappear_delay={self._config.disappear_delay}")

    def set_conf_threshold(self, threshold: float) -> None:
        """Set YOLO confidence threshold."""
        self._config.conf_threshold = max(0.1, min(0.9, threshold))

    def set_target_fps(self, fps: float) -> None:
        """Set target processing FPS."""
        self._config.target_fps = max(1.0, min(30.0, fps))

    def get_config(self) -> Dict[str, Any]:
        """Get current engine configuration."""
        return {
            "enabled": self._config.enabled,
            "disappear_delay": self._config.disappear_delay,
            "conf_threshold": self._config.conf_threshold,
            "target_fps": self._config.target_fps,
            "max_infer_ms": self._config.max_infer_ms,
        }

    # ==================== STATE ACCESS ====================

    def get_state(self) -> Dict[str, Any]:
        """Get full engine state for UI/monitoring."""
        with self._lock:
            zones_state = {}
            active_zones = []

            for zone_id, state in self._states.items():
                zone = self._zones.get(zone_id)
                zones_state[zone_id] = {
                    "active": state.active,
                    "detected": state.detected,
                    "conf": state.conf,
                    "visible": zone.visible if zone else False,
                    "cue_id": zone.cue_id if zone else None,
                }
                if state.active:
                    active_zones.append(zone_id)

            return {
                "enabled": self._config.enabled,
                "active_zones": active_zones,
                "zones_count": len(self._zones),
                "zones": zones_state,
                "degraded": self._degraded,
                "tick_count": self._tick_count,
            }

    def get_active_zones(self) -> List[int]:
        """Get list of currently active zone IDs."""
        with self._lock:
            return [zone_id for zone_id, state in self._states.items() if state.active]

    def is_zone_active(self, zone_id: int) -> bool:
        """Check if a specific zone is active."""
        with self._lock:
            state = self._states.get(zone_id)
            return state.active if state else False

    # ==================== DEGRADED MODE ====================

    def set_degraded(self, degraded: bool) -> None:
        """Set degraded mode (auto backoff)."""
        if self._degraded != degraded:
            self._degraded = degraded
            print(f"[VisionArtistEngine] DEGRADED={degraded}")

    def is_degraded(self) -> bool:
        """Check if engine is in degraded mode."""
        return self._degraded

    # ==================== CALLBACKS ====================

    def set_on_state_change(self, callback: Callable[[int, bool], None]) -> None:
        """Set callback for zone state changes."""
        self._on_state_change = callback

    # ==================== WATCHDOG ====================

    def mark_frame_processed(self) -> None:
        """Mark that a frame was processed. Call this from detector."""
        self._last_frame_ts = time.time()
        self._consecutive_errors = 0  # Reset error counter on success

        # Auto-recover from degraded mode if frames are flowing
        if self._watchdog_triggered:
            self._recover_from_watchdog()

    def check_watchdog(self) -> Dict[str, Any]:
        """
        Check if engine is processing frames.
        Should be called periodically (e.g., every second).

        If no frames processed for >watchdog_timeout:
        - Mark engine as degraded
        - Auto-reduce FPS to reduce load

        Returns:
            Dict with watchdog status
        """
        now = time.time()
        self._watchdog_last_check = now

        if not self._config.enabled:
            return {"triggered": False, "status": "disabled"}

        # Check time since last frame
        time_since_frame = now - self._last_frame_ts if self._last_frame_ts > 0 else 0

        if time_since_frame > self._config.watchdog_timeout:
            if not self._watchdog_triggered:
                self._trigger_watchdog()

            return {
                "triggered": True,
                "status": "degraded",
                "time_since_frame": round(time_since_frame, 1),
                "fps_reduced_to": self._config.target_fps,
            }

        return {
            "triggered": False,
            "status": "ok",
            "time_since_frame": round(time_since_frame, 1),
        }

    def _trigger_watchdog(self) -> None:
        """Trigger watchdog - auto-reduce FPS and mark degraded."""
        self._watchdog_triggered = True
        self._degraded = True

        # Save original FPS and reduce
        self._original_fps = self._config.target_fps
        new_fps = max(1.0, self._config.target_fps / 2)
        self._config.target_fps = new_fps

        print(f"[VisionArtistEngine] WATCHDOG TRIGGERED: No frames for {self._config.watchdog_timeout}s")
        print(f"[VisionArtistEngine] Auto-reduced FPS: {self._original_fps} -> {new_fps}")

    def _recover_from_watchdog(self) -> None:
        """Recover from watchdog - restore FPS."""
        if not self._watchdog_triggered:
            return

        self._watchdog_triggered = False
        self._degraded = False
        self._config.target_fps = self._original_fps

        print(f"[VisionArtistEngine] WATCHDOG RECOVERED: FPS restored to {self._original_fps}")

    def report_error(self, error: Exception) -> None:
        """
        Report an error from detector/processing.
        If too many consecutive errors, enter degraded mode.

        Args:
            error: The exception that occurred
        """
        self._consecutive_errors += 1

        if self._consecutive_errors >= self._max_consecutive_errors:
            if not self._degraded:
                self._degraded = True
                print(f"[VisionArtistEngine] DEGRADED: {self._consecutive_errors} consecutive errors")
                print(f"[VisionArtistEngine] Last error: {error}")

    def reset_errors(self) -> None:
        """Reset error counter and recover from degraded mode."""
        self._consecutive_errors = 0
        if self._degraded and not self._watchdog_triggered:
            self._degraded = False
            print("[VisionArtistEngine] Error counter reset, exiting degraded mode")

    def get_health(self) -> Dict[str, Any]:
        """
        Get engine health status.

        Returns:
            Dict with health metrics
        """
        now = time.time()
        return {
            "enabled": self._config.enabled,
            "degraded": self._degraded,
            "watchdog_triggered": self._watchdog_triggered,
            "consecutive_errors": self._consecutive_errors,
            "time_since_last_frame": round(now - self._last_frame_ts, 1) if self._last_frame_ts > 0 else None,
            "time_since_last_tick": round(now - self._last_tick_ts, 1) if self._last_tick_ts > 0 else None,
            "tick_count": self._tick_count,
            "current_fps": self._config.target_fps,
        }

    # ==================== TEST UTILITIES ====================

    def test_fire_zone(self, zone_id: int) -> bool:
        """
        Manually fire a zone cue for testing.
        Does not require detection - directly fires cue.

        Args:
            zone_id: Zone ID to fire (1-8)

        Returns:
            True if fired successfully
        """
        cue_id = ARTIST_CUE_MAP.get(zone_id)
        if not cue_id:
            print(f"[VisionArtistEngine] TEST_FIRE: Invalid zone {zone_id}")
            return False

        if not self._family_manager:
            print("[VisionArtistEngine] TEST_FIRE: No FamilyManager connected")
            return False

        try:
            print(f"[VisionArtistEngine] TEST_FIRE ZONE={zone_id} C{cue_id}")
            self._family_manager.activate_zone(FAMILIA_ARTIST, zone_id, source="test")
            return True
        except Exception as e:
            print(f"[VisionArtistEngine] TEST_FIRE ERROR: {e}")
            return False

    def test_kill_all(self) -> bool:
        """Kill all Artist cues for testing."""
        if not self._family_manager:
            return False

        try:
            print("[VisionArtistEngine] TEST_KILL_ALL")
            self._family_manager.deactivate_family(FAMILIA_ARTIST)
            return True
        except Exception as e:
            print(f"[VisionArtistEngine] TEST_KILL_ALL ERROR: {e}")
            return False
