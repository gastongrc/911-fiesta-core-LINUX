"""
Integration test: AvolitesController with Art-Net transport.
Validates that set_transport("artnet") starts the Art-Net subsystem and
routes fire_cue/kill_cue through DmxState instead of TitanQueue.
"""
import sys
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Prevent core/__init__.py from importing camera_manager (needs cv2)
# by creating a minimal core package that only exposes transport
import types
import importlib
import importlib.util

# Create core package stub that delegates transport to real subpackage
core_pkg = types.ModuleType("core")
core_pkg.__path__ = [os.path.join(ROOT, "core")]
sys.modules["core"] = core_pkg

# Load real transport subpackage
transport_spec = importlib.util.spec_from_file_location(
    "core.transport",
    os.path.join(ROOT, "core", "transport", "__init__.py"),
    submodule_search_locations=[os.path.join(ROOT, "core", "transport")],
)
transport_mod = importlib.util.module_from_spec(transport_spec)
sys.modules["core.transport"] = transport_mod
transport_spec.loader.exec_module(transport_mod)

# Also register submodules so avolites_config.py can import them
for submod in ["dmx_state", "artnet_engine", "cue_output_adapter",
               "titan_transport", "titan_queue", "titan_sync"]:
    full_name = f"core.transport.{submod}"
    if full_name not in sys.modules:
        sub_spec = importlib.util.spec_from_file_location(
            full_name,
            os.path.join(ROOT, "core", "transport", f"{submod}.py"),
        )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[full_name] = sub_mod
        sub_spec.loader.exec_module(sub_mod)

from avolites_config import AvolitesController


def test_controller_starts_http_by_default():
    """Default transport is HTTP, Art-Net is inactive."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    assert ctrl.transport in ("http", "https")
    assert ctrl._artnet_active is False
    assert ctrl._artnet_engine is None
    assert ctrl._dmx_state is None
    ctrl._titan_queue.stop()
    print("[OK] test_controller_starts_http_by_default")


def test_controller_switch_to_artnet():
    """set_transport('artnet') starts Art-Net subsystem."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    assert ctrl._artnet_active is False

    result = ctrl.set_transport("artnet")
    assert result is True
    assert ctrl.transport == "artnet"
    assert ctrl._artnet_active is True
    assert ctrl._artnet_engine is not None
    assert ctrl._artnet_engine.running is True
    assert ctrl._dmx_state is not None
    assert ctrl._cue_adapter is not None

    stats = ctrl._artnet_engine.get_stats()
    assert stats["running"] is True
    assert stats["configured_fps"] == 40

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_switch_to_artnet")


def test_controller_fire_kill_artnet_mode():
    """fire_cue/kill_cue route through DmxState when in artnet mode."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")

    # Fire C41
    ctrl.fire_cue(41)
    assert ctrl._dmx_state.get_channel(41) == 255
    assert 41 in ctrl._dmx_state.get_active_cues()

    # State persists
    time.sleep(0.05)
    assert ctrl._dmx_state.get_channel(41) == 255

    # Kill C41
    ctrl.kill_cue(41)
    assert ctrl._dmx_state.get_channel(41) == 0
    assert 41 not in ctrl._dmx_state.get_active_cues()

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_fire_kill_artnet_mode")


def test_controller_fire_critical_artnet():
    """fire_cue_critical routes through adapter in artnet mode."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")

    ctrl.fire_cue_critical(41)
    assert ctrl._dmx_state.get_channel(41) == 255

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_fire_critical_artnet")


def test_controller_kill_all_artnet():
    """kill_all_cues works in artnet mode."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")

    ctrl.fire_cue(1)
    ctrl.fire_cue(41)
    ctrl.fire_cue(42)
    assert ctrl._dmx_state.get_channel(1) == 255
    assert ctrl._dmx_state.get_channel(41) == 255
    assert ctrl._dmx_state.get_channel(42) == 255

    ctrl.kill_all_cues()
    assert ctrl._dmx_state.get_channel(1) == 0
    assert ctrl._dmx_state.get_channel(41) == 0
    assert ctrl._dmx_state.get_channel(42) == 0

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_kill_all_artnet")


def test_controller_switch_back_to_http():
    """Switching from artnet back to http stops Art-Net."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")
    assert ctrl._artnet_active is True

    ctrl.set_transport("http")
    assert ctrl._artnet_active is False
    assert ctrl._artnet_engine is None
    assert ctrl.transport == "http"

    ctrl._titan_queue.stop()
    print("[OK] test_controller_switch_back_to_http")


def test_controller_artnet_engine_emits_frames():
    """Art-Net engine sends frames when controller is in artnet mode."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")

    ctrl.fire_cue(41)
    time.sleep(0.2)  # ~8 frames

    stats = ctrl._artnet_engine.get_stats()
    assert stats["frames_sent"] > 5
    assert stats["errors"] == 0

    # DMX state must be persistent
    assert ctrl._dmx_state.get_channel(41) == 255

    ctrl._artnet_engine.stop()
    print(f"[OK] test_controller_artnet_engine_emits_frames ({stats['frames_sent']} frames)")


def test_controller_get_status_includes_artnet():
    """get_status() includes artnet_stats when in artnet mode."""
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("artnet")
    time.sleep(0.1)

    status = ctrl.get_status()
    assert status["transport"] == "artnet"
    assert status["artnet_active"] is True
    assert status["artnet_stats"] is not None
    assert status["artnet_stats"]["running"] is True
    assert "adapter" in status["artnet_stats"]

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_get_status_includes_artnet")


if __name__ == "__main__":
    tests = [
        test_controller_starts_http_by_default,
        test_controller_switch_to_artnet,
        test_controller_fire_kill_artnet_mode,
        test_controller_fire_critical_artnet,
        test_controller_kill_all_artnet,
        test_controller_switch_back_to_http,
        test_controller_artnet_engine_emits_frames,
        test_controller_get_status_includes_artnet,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        sys.exit(1)
