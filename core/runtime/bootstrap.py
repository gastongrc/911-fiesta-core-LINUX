# ============================================================================
# core/runtime/bootstrap.py — Single Runtime Bootstrap
# ============================================================================
# Initializes the DMX pipeline for headless (uvicorn) or GUI (main.py) mode.
# GUARANTEES a single runtime per process via threading lock + idempotent guard.
#
# Creates:
#   AvolitesController → TitanQueue → ArtNetTransport
#   CueEngine (optional, if deps available)
#
# Registers everything in AppState singleton so the API can access it.
#
# Usage:
#   from core.runtime.bootstrap import start_runtime
#   start_runtime()           # headless: no auto-update loop
#   start_runtime(gui=True)   # GUI: with auto-update loop
#
# Access instances after bootstrap:
#   from core.runtime.bootstrap import get_controller, get_cue_engine
# ============================================================================

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("Bootstrap")

# Guard against double initialization (thread-safe within a single process)
_runtime_lock = threading.Lock()
_runtime_started = False

# Singleton references — set once during start_runtime(), read-only after
_controller = None
_cue_engine = None
_state_manager = None
_energy_detector = None


def start_runtime(gui: bool = False) -> bool:
    """
    Initialize the 911 Fiesta DMX runtime.

    Creates AvolitesController, CueEngine, and registers them in AppState.
    Safe to call multiple times — only the first call does anything.
    Idempotent: subsequent calls return False without side effects.

    Args:
        gui: If True, start CueEngine auto-update loop (needs StateManager
             with real audio feed). If False (headless/uvicorn), skip the
             loop — cues are fired via API only.

    Returns:
        True if runtime was started, False if already running or failed.
    """
    global _runtime_started, _controller, _cue_engine, _state_manager, _energy_detector

    with _runtime_lock:
        if _runtime_started:
            logger.info("[BOOTSTRAP] runtime already started (pid=%d), skipping", os.getpid())
            return False

        logger.info("[BOOTSTRAP] runtime starting (pid=%d, gui=%s)...", os.getpid(), gui)

        try:
            # === 1. AvolitesController ===
            controller = _create_controller()
            if controller is None:
                logger.error("[BOOTSTRAP] FAILED: could not create AvolitesController")
                return False
            logger.info("[BOOTSTRAP] AvolitesController created (id=%d)", id(controller))

            # === 2. Apply configured transport ===
            _apply_transport(controller)

            # === 3. EnergyDetector (stub for headless) ===
            energy_detector = _create_energy_detector()
            logger.info("[BOOTSTRAP] EnergyDetector created (%s)", type(energy_detector).__name__)

            # === 4. StateManager ===
            state_manager = _create_state_manager(energy_detector)
            logger.info("[BOOTSTRAP] StateManager created (%s)", type(state_manager).__name__)

            # === 5. CueEngine ===
            cue_engine = _create_cue_engine(controller, state_manager, energy_detector, gui)
            if cue_engine:
                logger.info("[BOOTSTRAP] CueEngine created (auto_update=%s)", gui)
            else:
                logger.warning("[BOOTSTRAP] CueEngine not available (cue dispatch via controller only)")

            # === 6. Register in AppState ===
            _register_app_state(controller, cue_engine, state_manager, energy_detector)
            logger.info("[BOOTSTRAP] AppState registered")

            # === 7. Store singleton refs ===
            _controller = controller
            _cue_engine = cue_engine
            _state_manager = state_manager
            _energy_detector = energy_detector

            # === 8. Verify transport ===
            _verify_pipeline(controller)

            _runtime_started = True
            logger.info("[BOOTSTRAP] runtime started OK (pid=%d)", os.getpid())
            return True

        except Exception as e:
            logger.error("[BOOTSTRAP] FATAL: %s", e, exc_info=True)
            return False


def is_runtime_started() -> bool:
    """Check if the runtime has been initialized."""
    return _runtime_started


def get_controller():
    """Return the singleton AvolitesController (None if not started)."""
    return _controller


def get_cue_engine():
    """Return the singleton CueEngine (None if not started or unavailable)."""
    return _cue_engine


def get_state_manager():
    """Return the singleton StateManager (None if not started)."""
    return _state_manager


def get_energy_detector():
    """Return the singleton EnergyDetector (None if not started)."""
    return _energy_detector


# ============================================================================
# Internal helpers
# ============================================================================

def _create_controller():
    """Create AvolitesController with error handling."""
    try:
        from avolites_config import AvolitesController
        controller = AvolitesController(auto_connect=False)
        return controller
    except Exception as e:
        logger.error("[BOOTSTRAP] AvolitesController import/init failed: %s", e)
        return None


def _apply_transport(controller):
    """
    Apply the configured transport (artnet or http).

    Priority:
      1. Environment variable FIESTA_TRANSPORT (artnet|http)
      2. Config file avolites_config.json -> "transport"
      3. Default: http
    """
    try:
        # Environment override takes priority
        env_transport = os.environ.get("FIESTA_TRANSPORT", "").lower().strip()
        config_transport = controller.config_manager.config.get("transport", "http")
        transport = env_transport if env_transport in ("artnet", "http", "https") else config_transport

        if env_transport and env_transport != config_transport:
            logger.info("[BOOTSTRAP] FIESTA_TRANSPORT=%s overrides config=%s", env_transport, config_transport)

        if transport == "artnet":
            artnet_cfg = controller.config_manager.config.get("artnet", {})
            result = controller.set_transport("artnet", artnet_params=artnet_cfg)
            logger.info("[BOOTSTRAP] transport -> artnet (result=%s)", result)
        else:
            logger.info("[BOOTSTRAP] transport -> %s (default)", transport)

        # Log the active transport for verification
        active = type(controller._titan_queue.get_transport()).__name__
        logger.info("[BOOTSTRAP] active transport verified: %s", active)
    except Exception as e:
        logger.error("[BOOTSTRAP] transport apply failed: %s", e)


def _create_energy_detector():
    """Create EnergyDetector, falling back to a stub if not available."""
    try:
        from energy_detector import EnergyDetector
        return EnergyDetector()
    except Exception:
        # Headless stub — returns neutral energy values
        return _EnergyDetectorStub()


class _EnergyDetectorStub:
    """Minimal EnergyDetector for headless mode (no audio input)."""
    ENERGY_NAMES = ["BAJA", "MEDIA", "ALTA"]

    def __init__(self):
        self.current_energy = 0
        self.energy_score = 0.5

    def process(self, block, sr):
        pass

    def get_energy_level(self):
        return self.current_energy

    def get_energy_name(self):
        return self.ENERGY_NAMES[self.current_energy]

    def get_energy_score(self):
        return self.energy_score

    def reset_calibration(self):
        pass


def _create_state_manager(energy_detector):
    """Create StateManager, falling back to a stub if not available."""
    try:
        from state_manager import StateManager
        return StateManager(
            energy_detector=energy_detector,
            min_hold_seconds=2.0,
            hysteresis_margin=0.6,
            cooldown_seconds=0.5,
        )
    except Exception:
        return _StateManagerStub()


class _StateManagerStub:
    """Minimal StateManager for headless mode (no audio-driven state)."""

    def __init__(self):
        self.current_state = "BAJADA"

    def get_state(self):
        return self.current_state

    def get_energy(self):
        return "MEDIA"

    def set_disabled_states(self, states):
        pass


def _create_cue_engine(controller, state_manager, energy_detector, auto_update: bool):
    """Create CueEngine if available. Returns None on failure."""
    try:
        from cue_engine import create_cue_engine
        engine = create_cue_engine(
            avolites_controller=controller,
            state_manager=state_manager,
            energy_detector=energy_detector,
            auto_update=auto_update,
        )
        if auto_update:
            engine.start_auto_update()
        return engine
    except Exception as e:
        logger.error("[BOOTSTRAP] CueEngine creation failed: %s", e)
        return None


def _register_app_state(controller, cue_engine, state_manager, energy_detector):
    """Register runtime objects in AppState singleton for API access."""
    from services.app_state import AppState
    AppState.initialize(
        state_manager=state_manager,
        audio_engine=None,
        cue_engine=cue_engine,
        avolites=controller,
        vision_manager=None,
        modules_by_state={},
        energy_detector=energy_detector,
        audio_monitor=None,
        auto_clock=None,
    )


def _verify_pipeline(controller):
    """Log the state of the transport pipeline."""
    try:
        q = controller._titan_queue
        transport = q.get_transport()
        transport_name = type(transport).__name__
        transport_id = id(transport)
        logger.info("[BOOTSTRAP] pipeline: TitanQueue(id=%d) -> %s(id=%d)",
                    id(q), transport_name, transport_id)

        if transport_name == "ArtNetTransport":
            stats = transport.get_stats()
            logger.info(
                "[BOOTSTRAP] ArtNet: target=%s broadcast=%s universe=%s refresh=%sHz",
                stats.get("target_ip"), stats.get("broadcast"),
                stats.get("artnet_universe"), stats.get("refresh_rate_hz"),
            )
            if transport.ping():
                logger.info("[BOOTSTRAP] ArtNet TX thread alive: YES")
            else:
                logger.error("[BOOTSTRAP] ArtNet TX thread alive: NO (PROBLEM)")
    except Exception as e:
        logger.error("[BOOTSTRAP] pipeline verification failed: %s", e)
