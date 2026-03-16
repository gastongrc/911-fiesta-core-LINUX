"""
Tests for SacnEngine — sACN E1.31 transport.
Validates packet construction, engine lifecycle, and DmxState integration.
"""
import sys
import os
import struct
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Stub core package to avoid heavy imports (same pattern as test_artnet_integration)
import types
import importlib
import importlib.util

core_pkg = types.ModuleType("core")
core_pkg.__path__ = [os.path.join(ROOT, "core")]
sys.modules["core"] = core_pkg

transport_spec = importlib.util.spec_from_file_location(
    "core.transport",
    os.path.join(ROOT, "core", "transport", "__init__.py"),
    submodule_search_locations=[os.path.join(ROOT, "core", "transport")],
)
transport_mod = importlib.util.module_from_spec(transport_spec)
sys.modules["core.transport"] = transport_mod
transport_spec.loader.exec_module(transport_mod)

for submod in ["dmx_state", "artnet_engine", "cue_output_adapter",
               "titan_transport", "titan_queue", "titan_sync", "sacn_engine"]:
    full_name = f"core.transport.{submod}"
    if full_name not in sys.modules:
        sub_spec = importlib.util.spec_from_file_location(
            full_name,
            os.path.join(ROOT, "core", "transport", f"{submod}.py"),
        )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[full_name] = sub_mod
        sub_spec.loader.exec_module(sub_mod)

from core.transport.dmx_state import DmxState, DMX_CHANNELS
from core.transport.sacn_engine import (
    SacnEngine,
    build_sacn_packet,
    multicast_ip_for_universe,
    SACN_PORT,
    ACN_PACKET_IDENTIFIER,
    E131_VECTOR_ROOT,
)
from core.transport.cue_output_adapter import CueOutputAdapter


# ===== UNIT TESTS =====

def test_multicast_ip_for_universe():
    """Multicast IP follows E1.31 spec: 239.255.<hi>.<lo>."""
    assert multicast_ip_for_universe(1) == "239.255.0.1"
    assert multicast_ip_for_universe(255) == "239.255.0.255"
    assert multicast_ip_for_universe(256) == "239.255.1.0"
    assert multicast_ip_for_universe(512) == "239.255.2.0"
    print("[OK] test_multicast_ip_for_universe")


def test_build_sacn_packet_structure():
    """sACN packet has correct preamble, vector, and size."""
    dmx = bytearray(DMX_CHANNELS)
    dmx[40] = 255  # Channel 41 (0-indexed = 40)
    cid = b"\x01" * 16

    packet = build_sacn_packet(dmx, universe=1, sequence=42, priority=100, cid=cid)

    # Preamble Size (2 bytes) = 0x0010
    assert struct.unpack(">H", packet[0:2])[0] == 0x0010
    # Postamble Size (2 bytes) = 0x0000
    assert struct.unpack(">H", packet[2:4])[0] == 0x0000
    # ACN Packet Identifier (12 bytes at offset 4)
    assert packet[4:16] == ACN_PACKET_IDENTIFIER
    assert len(ACN_PACKET_IDENTIFIER) == 12
    # Root Flags+Length at offset 16
    # Root Vector at offset 18 = 0x00000004
    root_vector = struct.unpack(">I", packet[18:22])[0]
    assert root_vector == E131_VECTOR_ROOT

    # CID at offset 22 (16 bytes)
    assert packet[22:38] == cid

    # Total packet size: 638 bytes (per ANSI E1.31-2018)
    # Root: preamble(2) + postamble(2) + ACN_ID(12) + flags+len(2) + vector(4) + cid(16) = 38
    # Frame: flags+len(2) + vector(4) + source_name(64) + priority(1) + sync(2) + seq(1) + options(1) + universe(2) = 77
    # DMP: flags+len(2) + vector(1) + addr_type(1) + first_addr(2) + incr(2) + count(2) + data(513) = 523
    # Total = 38 + 77 + 523 = 638
    assert len(packet) == 638

    print("[OK] test_build_sacn_packet_structure")


def test_build_sacn_packet_contains_dmx_data():
    """DMX data is embedded in the sACN packet."""
    dmx = bytearray(DMX_CHANNELS)
    dmx[40] = 255  # Channel 41

    packet = build_sacn_packet(dmx, universe=1, sequence=0, priority=100)

    # DMX data is at the end of the packet, preceded by start code (0x00)
    # Last 513 bytes = start_code + 512 dmx channels
    prop_values = packet[-513:]
    assert prop_values[0] == 0x00  # Start code
    assert prop_values[41] == 255  # Channel 41 (1-indexed in prop_values after start code)
    assert prop_values[1] == 0    # Channel 1 = 0

    print("[OK] test_build_sacn_packet_contains_dmx_data")


def test_build_sacn_packet_universe():
    """Universe is correctly encoded in framing layer."""
    dmx = bytearray(DMX_CHANNELS)
    packet = build_sacn_packet(dmx, universe=42)

    # Universe offset:
    # Root layer: preamble(2) + postamble(2) + ACN_ID(12) + flags+len(2) + vector(4) + cid(16) = 38
    # Framing: flags+len(2) + vector(4) + source_name(64) + priority(1) + sync(2) + seq(1) + options(1) = 75
    # Universe at: 38 + 75 = 113
    universe_offset = 113
    universe = struct.unpack(">H", packet[universe_offset:universe_offset+2])[0]
    assert universe == 42

    print("[OK] test_build_sacn_packet_universe")


def test_sacn_engine_init():
    """SacnEngine initializes with correct defaults."""
    dmx = DmxState(cue_channel_map={41: [41]})
    engine = SacnEngine(dmx, universe=1, fps=40)

    assert engine.running is False
    stats = engine.get_stats()
    assert stats["universe"] == 1
    assert stats["configured_fps"] == 40
    assert stats["multicast_ip"] == "239.255.0.1"
    assert stats["port"] == SACN_PORT
    assert stats["priority"] == 100

    print("[OK] test_sacn_engine_init")


def test_sacn_engine_start_stop():
    """SacnEngine starts and stops cleanly."""
    dmx = DmxState(cue_channel_map={41: [41]})
    engine = SacnEngine(dmx, universe=1, fps=40)

    assert engine.start() is True
    assert engine.running is True

    time.sleep(0.15)  # ~6 frames
    stats = engine.get_stats()
    assert stats["frames_sent"] > 3
    assert stats["errors"] == 0

    engine.stop()
    assert engine.running is False

    print(f"[OK] test_sacn_engine_start_stop ({stats['frames_sent']} frames)")


def test_sacn_engine_dmx_state_integration():
    """Pulse mode: fire triggers 1-frame pulse, auto-resets via snapshot."""
    dmx = DmxState(cue_channel_map={41: [41]})

    # Test pulse without engine: fire sets 255, snapshot captures and resets
    dmx.fire(41)
    assert dmx.get_channel(41) == 255  # Pulse is pending

    frame1 = dmx.snapshot()
    assert frame1[40] == 255           # Frame captured the pulse

    assert dmx.get_channel(41) == 0    # Auto-reset after snapshot
    frame2 = dmx.snapshot()
    assert frame2[40] == 0             # Next frame sees 0

    # Test with engine running
    engine = SacnEngine(dmx, universe=1, fps=40)
    engine.start()

    dmx.fire(41)
    time.sleep(0.15)  # ~6 frames — pulse consumed
    stats = engine.get_stats()
    assert stats["frames_sent"] > 3
    assert dmx.get_channel(41) == 0  # Already auto-reset

    engine.stop()
    print("[OK] test_sacn_engine_dmx_state_integration")


def test_sacn_engine_from_config():
    """SacnEngine.from_config() creates engine with correct params."""
    dmx = DmxState(cue_channel_map={41: [41]})
    config = {
        "universe": 5,
        "fps": 30,
        "multicast_ip": "239.255.0.5",
        "port": 5568,
        "priority": 150,
    }
    engine = SacnEngine.from_config(config, dmx)
    stats = engine.get_stats()
    assert stats["universe"] == 5
    assert stats["configured_fps"] == 30
    assert stats["multicast_ip"] == "239.255.0.5"
    assert stats["port"] == 5568
    assert stats["priority"] == 150

    print("[OK] test_sacn_engine_from_config")


def test_sacn_engine_update_config():
    """update_config() changes engine parameters."""
    dmx = DmxState(cue_channel_map={41: [41]})
    engine = SacnEngine(dmx, universe=1, fps=40)

    engine.update_config(universe=10, fps=20, priority=50)
    stats = engine.get_stats()
    assert stats["universe"] == 10
    assert stats["configured_fps"] == 20
    assert stats["priority"] == 50
    # Multicast IP auto-updates when universe changes
    assert stats["multicast_ip"] == "239.255.0.10"

    print("[OK] test_sacn_engine_update_config")


def test_sacn_with_cue_output_adapter():
    """CueOutputAdapter pulse mode with SacnEngine pipeline."""
    dmx = DmxState(cue_channel_map={41: [41], 1: [1]})
    adapter = CueOutputAdapter(dmx)

    # Test without engine to verify pulse logic
    assert adapter.fire(41) is True
    assert dmx.get_channel(41) == 255  # Pulse pending

    frame = dmx.snapshot()
    assert frame[40] == 255            # Captured in frame
    assert dmx.get_channel(41) == 0    # Auto-reset

    # Kill is no-op in pulse mode
    assert adapter.kill(41) is True

    # Unmapped cue
    assert adapter.fire(999) is False

    # Verify stats
    stats = adapter.get_stats()
    assert stats["fires"] == 1
    assert stats["kills"] == 1
    assert stats["unmapped"] == 1

    # Verify with engine running
    engine = SacnEngine(dmx, universe=1, fps=40)
    engine.start()
    adapter.fire(1)
    time.sleep(0.1)
    assert dmx.get_channel(1) == 0  # Already consumed by engine
    engine.stop()

    print("[OK] test_sacn_with_cue_output_adapter")


# ===== INTEGRATION TEST: Controller + sACN =====

def test_controller_switch_to_sacn():
    """set_transport('sacn') starts sACN subsystem."""
    from avolites_config import AvolitesController
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    assert ctrl._sacn_active is False

    result = ctrl.set_transport("sacn")
    assert result is True
    assert ctrl.transport == "sacn"
    assert ctrl._sacn_active is True
    assert ctrl._sacn_engine is not None
    assert ctrl._sacn_engine.running is True
    assert ctrl._dmx_state is not None
    assert ctrl._cue_adapter is not None
    assert ctrl._artnet_active is False

    stats = ctrl._sacn_engine.get_stats()
    assert stats["running"] is True

    ctrl._sacn_engine.stop()
    print("[OK] test_controller_switch_to_sacn")


def test_controller_fire_kill_sacn_mode():
    """fire_cue routes through DmxState pulse mode when in sacn mode."""
    from avolites_config import AvolitesController
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("sacn")

    # Stop engine briefly to test pulse without race condition
    ctrl._sacn_engine.stop()

    ctrl.fire_cue(41)
    assert ctrl._dmx_state.get_channel(41) == 255  # Pulse pending

    frame = ctrl._dmx_state.snapshot()
    assert frame[40] == 255                          # Captured
    assert ctrl._dmx_state.get_channel(41) == 0     # Auto-reset

    # Pulse mode: no active cues
    assert ctrl._dmx_state.get_active_cues() == set()

    print("[OK] test_controller_fire_kill_sacn_mode")


def test_controller_sacn_to_http():
    """Switching from sacn to http stops sACN."""
    from avolites_config import AvolitesController
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("sacn")
    assert ctrl._sacn_active is True

    ctrl.set_transport("http")
    assert ctrl._sacn_active is False
    assert ctrl._sacn_engine is None
    assert ctrl.transport == "http"

    ctrl._titan_queue.stop()
    print("[OK] test_controller_sacn_to_http")


def test_controller_sacn_to_artnet():
    """Switching from sacn to artnet stops sACN and starts Art-Net."""
    from avolites_config import AvolitesController
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("sacn")
    assert ctrl._sacn_active is True
    assert ctrl._artnet_active is False

    ctrl.set_transport("artnet")
    assert ctrl._sacn_active is False
    assert ctrl._artnet_active is True

    ctrl._artnet_engine.stop()
    print("[OK] test_controller_sacn_to_artnet")


def test_controller_get_status_includes_sacn():
    """get_status() includes sacn_stats when in sacn mode."""
    from avolites_config import AvolitesController
    ctrl = AvolitesController(verbose=False, auto_connect=False)
    ctrl.set_transport("sacn")
    time.sleep(0.1)

    status = ctrl.get_status()
    assert status["transport"] == "sacn"
    assert status["sacn_active"] is True
    assert status["sacn_stats"] is not None
    assert status["sacn_stats"]["running"] is True
    assert "adapter" in status["sacn_stats"]

    ctrl._sacn_engine.stop()
    print("[OK] test_controller_get_status_includes_sacn")


if __name__ == "__main__":
    tests = [
        # Unit tests
        test_multicast_ip_for_universe,
        test_build_sacn_packet_structure,
        test_build_sacn_packet_contains_dmx_data,
        test_build_sacn_packet_universe,
        test_sacn_engine_init,
        test_sacn_engine_start_stop,
        test_sacn_engine_dmx_state_integration,
        test_sacn_engine_from_config,
        test_sacn_engine_update_config,
        test_sacn_with_cue_output_adapter,
        # Integration tests
        test_controller_switch_to_sacn,
        test_controller_fire_kill_sacn_mode,
        test_controller_sacn_to_http,
        test_controller_sacn_to_artnet,
        test_controller_get_status_includes_sacn,
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
