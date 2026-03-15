# ============================================================================
# core/runtime/bootstrap.py — Headless Runtime Bootstrap
# ============================================================================
# Initializes the DMX pipeline for headless (uvicorn) or GUI (main.py) mode.
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
# ============================================================================

from __future__ import annotations

import os
import threading
from typing import Optional

# Guard against double initialization
_runtime_lock = threading.Lock()
_runtime_started = False


def start_runtime(gui: bool = False) -> bool:
    """
    Initialize the 911 Fiesta DMX runtime.

    Creates AvolitesController, CueEngine, and registers them in AppState.
    Safe to call multiple times — only the first call does anything.

    Args:
        gui: If True, start CueEngine auto-update loop (needs StateManager
             with real audio feed). If False (headless/uvicorn), skip the
             loop — cues are fired via API only.

    Returns:
        True if runtime was started, False if already running or failed.
    """
    global _runtime_started

    with _runtime_lock:
        if _runtime_started:
            print("[BOOTSTRAP] runtime already started, skipping")
            return False

        print("[BOOTSTRAP] runtime starting...")

        try:
            # === 1. AvolitesController ===
            controller = _create_controller()
            if controller is None:
                print("[BOOTSTRAP] FAILED: could not create AvolitesController")
                return False
            print(f"[BOOTSTRAP] AvolitesController created (id={id(controller)})")

            # === 2. Apply configured transport ===
            _apply_transport(controller)

            # === 3. EnergyDetector (stub for headless) ===
            energy_detector = _create_energy_detector()
            print(f"[BOOTSTRAP] EnergyDetector created ({type(energy_detector).__name__})")

            # === 4. StateManager ===
            state_manager = _create_state_manager(energy_detector)
            print(f"[BOOTSTRAP] StateManager created ({type(state_manager).__name__})")

            # === 5. CueEngine ===
            cue_engine = _create_cue_engine(controller, state_manager, energy_detector, gui)
            if cue_engine:
                print(f"[BOOTSTRAP] CueEngine created (auto_update={gui})")
            else:
                print("[BOOTSTRAP] CueEngine not available (cue dispatch via controller only)")

            # === 6. Register in AppState ===
            _register_app_state(controller, cue_engine, state_manager, energy_detector)
            print("[BOOTSTRAP] AppState registered")

            # === 7. Verify transport ===
            _verify_pipeline(controller)

            _runtime_started = True
            print("[BOOTSTRAP] runtime started OK")
            return True

        except Exception as e:
            print(f"[BOOTSTRAP] FATAL: {e}")
            import traceback
            traceback.print_exc()
            return False


def is_runtime_started() -> bool:
    """Check if the runtime has been initialized."""
    return _runtime_started


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
        print(f"[BOOTSTRAP] AvolitesController import/init failed: {e}")
        return None


def _apply_transport(controller):
    """Apply the configured transport (artnet or http) from config file."""
    try:
        transport = controller.config_manager.config.get("transport", "http")
        if transport == "artnet":
            artnet_cfg = controller.config_manager.config.get("artnet", {})
            result = controller.set_transport("artnet", artnet_params=artnet_cfg)
            print(f"[BOOTSTRAP] transport -> artnet (result={result})")
        else:
            print(f"[BOOTSTRAP] transport -> {transport} (default)")
    except Exception as e:
        print(f"[BOOTSTRAP] transport apply failed: {e}")


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
        print(f"[BOOTSTRAP] CueEngine creation failed: {e}")
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
        queue = controller._titan_queue
        transport = queue.get_transport()
        transport_name = type(transport).__name__
        transport_id = id(transport)
        print(f"[BOOTSTRAP] pipeline: TitanQueue -> {transport_name} (id={transport_id})")

        if transport_name == "ArtNetTransport":
            stats = transport.get_stats()
            print(
                f"[BOOTSTRAP] ArtNet: target={stats.get('target_ip')} "
                f"broadcast={stats.get('broadcast')} "
                f"universe={stats.get('artnet_universe')} "
                f"refresh={stats.get('refresh_rate_hz')}Hz"
            )
            if transport.ping():
                print("[BOOTSTRAP] ArtNet TX thread alive: YES")
            else:
                print("[BOOTSTRAP] ArtNet TX thread alive: NO (PROBLEM)")
    except Exception as e:
        print(f"[BOOTSTRAP] pipeline verification failed: {e}")
