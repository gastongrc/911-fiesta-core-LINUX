"""
Tests para el sistema Art-Net DMX: DmxState, ArtNetEngine, CueOutputAdapter.
"""
import json
import struct
import sys
import os
import time
import threading

# Agregar root al path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Import directo del subpaquete transport sin pasar por core/__init__.py
# (core/__init__.py importa camera_manager que necesita cv2)
import importlib
_transport_pkg = os.path.join(ROOT, "core", "transport")
sys.path.insert(0, os.path.join(ROOT, "core", "transport"))

# Workaround: importar como top-level modules
import types
core_pkg = types.ModuleType("core")
core_pkg.__path__ = [os.path.join(ROOT, "core")]
sys.modules["core"] = core_pkg

transport_pkg = types.ModuleType("core.transport")
transport_pkg.__path__ = [os.path.join(ROOT, "core", "transport")]
sys.modules["core.transport"] = transport_pkg

from core.transport.dmx_state import DmxState, DMX_CHANNELS
from core.transport.artnet_engine import ArtNetEngine, build_artnet_dmx_packet, ARTNET_PORT
from core.transport.cue_output_adapter import CueOutputAdapter


# ============================================================================
# TEST: DmxState
# ============================================================================

def test_dmx_state_init():
    """Estado inicial: 512 canales en 0."""
    state = DmxState()
    frame = state.snapshot()
    assert len(frame) == 512
    assert all(v == 0 for v in frame)
    print("[OK] test_dmx_state_init")


def test_dmx_state_fire_kill():
    """fire() pone canal en 255, kill() lo pone en 0."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})

    # FIRE C41
    result = state.fire(41)
    assert result is True
    frame = state.snapshot()
    assert frame[40] == 255  # canal 41 → index 40

    # Estado persistente: sigue en 255
    frame2 = state.snapshot()
    assert frame2[40] == 255

    # KILL C41
    result = state.kill(41)
    assert result is True
    frame3 = state.snapshot()
    assert frame3[40] == 0

    print("[OK] test_dmx_state_fire_kill")


def test_dmx_state_unmapped_cue():
    """Cue sin mapeo retorna False."""
    state = DmxState(cue_channel_map={1: [1]})
    assert state.fire(999) is False
    assert state.kill(999) is False
    print("[OK] test_dmx_state_unmapped_cue")


def test_dmx_state_multi_channel():
    """Un cue puede controlar múltiples canales."""
    state = DmxState(cue_channel_map={1: [1, 2, 3]})
    state.fire(1)
    frame = state.snapshot()
    assert frame[0] == 255
    assert frame[1] == 255
    assert frame[2] == 255
    assert frame[3] == 0  # canal 4 no afectado

    state.kill(1)
    frame2 = state.snapshot()
    assert frame2[0] == 0
    assert frame2[1] == 0
    assert frame2[2] == 0
    print("[OK] test_dmx_state_multi_channel")


def test_dmx_state_kill_all():
    """kill_all() pone todo a 0."""
    state = DmxState(cue_channel_map={1: [1], 2: [2], 3: [3]})
    state.fire(1)
    state.fire(2)
    state.fire(3)

    frame = state.snapshot()
    assert frame[0] == 255
    assert frame[1] == 255
    assert frame[2] == 255

    state.kill_all()
    frame2 = state.snapshot()
    assert all(v == 0 for v in frame2)
    assert len(state.get_active_cues()) == 0
    print("[OK] test_dmx_state_kill_all")


def test_dmx_state_active_cues():
    """Tracking de cues activos."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})
    assert len(state.get_active_cues()) == 0

    state.fire(41)
    assert 41 in state.get_active_cues()

    state.fire(42)
    assert 41 in state.get_active_cues()
    assert 42 in state.get_active_cues()

    state.kill(41)
    assert 41 not in state.get_active_cues()
    assert 42 in state.get_active_cues()
    print("[OK] test_dmx_state_active_cues")


def test_dmx_state_thread_safety():
    """Múltiples threads haciendo fire/kill concurrentemente."""
    state = DmxState(cue_channel_map={i: [i] for i in range(1, 101)})
    errors = []

    def fire_worker(start, end):
        try:
            for i in range(start, end):
                state.fire(i)
                state.snapshot()
        except Exception as e:
            errors.append(e)

    def kill_worker(start, end):
        try:
            for i in range(start, end):
                state.kill(i)
                state.snapshot()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=fire_worker, args=(1, 51)),
        threading.Thread(target=fire_worker, args=(51, 101)),
        threading.Thread(target=kill_worker, args=(1, 51)),
        threading.Thread(target=kill_worker, args=(51, 101)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Thread errors: {errors}"
    # Snapshot must always be 512 bytes
    assert len(state.snapshot()) == 512
    print("[OK] test_dmx_state_thread_safety")


def test_dmx_state_from_json():
    """Carga desde archivo cue_map.json."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cue_map_path = os.path.join(project_root, "cue_map.json")
    state = DmxState.from_json(cue_map_path)

    # Verificar que carga los mapeos
    cue_map = state.get_cue_map()
    assert 41 in cue_map
    assert 1 in cue_map
    assert 82 in cue_map

    # Fire y verificar
    state.fire(41)
    assert state.get_channel(41) == 255
    state.kill(41)
    assert state.get_channel(41) == 0
    print("[OK] test_dmx_state_from_json")


def test_dmx_state_persistence():
    """El estado DMX es persistente — no se resetea entre snapshots."""
    state = DmxState(cue_channel_map={41: [41]})
    state.fire(41)

    # Tomar 100 snapshots — el valor debe mantenerse
    for _ in range(100):
        frame = state.snapshot()
        assert frame[40] == 255, "DMX state must be persistent, not pulsed"

    print("[OK] test_dmx_state_persistence")


# ============================================================================
# TEST: Art-Net Packet
# ============================================================================

def test_artnet_packet_structure():
    """Verifica estructura del paquete Art-Net OpDmx."""
    dmx_data = bytearray(512)
    dmx_data[40] = 255  # ch41 = 255

    packet = build_artnet_dmx_packet(dmx_data, universe=10, sequence=1)

    # Total: 18 header + 512 data = 530 bytes
    assert len(packet) == 530

    # Header "Art-Net\0"
    assert packet[0:8] == b"Art-Net\x00"

    # OpCode 0x5000 (little-endian → bytes 0x00, 0x50)
    assert packet[8] == 0x00
    assert packet[9] == 0x50

    # Protocol version 14 (big-endian → 0x00, 0x0E)
    assert packet[10] == 0x00
    assert packet[11] == 0x0E

    # Sequence = 1
    assert packet[12] == 1

    # Physical = 0
    assert packet[13] == 0

    # Universe 10 (little-endian)
    assert packet[14] == 10  # low byte
    assert packet[15] == 0   # high byte

    # Length 512 (big-endian → 0x02, 0x00)
    assert packet[16] == 0x02
    assert packet[17] == 0x00

    # DMX data: ch41 (index 40) = 255
    assert packet[18 + 40] == 255

    # Resto debe ser 0
    assert packet[18] == 0   # ch1
    assert packet[18 + 511] == 0  # ch512

    print("[OK] test_artnet_packet_structure")


def test_artnet_packet_universe_encoding():
    """Universe se codifica little-endian correctamente."""
    dmx_data = bytearray(512)

    # Universe 0
    pkt = build_artnet_dmx_packet(dmx_data, universe=0)
    assert pkt[14] == 0 and pkt[15] == 0

    # Universe 255
    pkt = build_artnet_dmx_packet(dmx_data, universe=255)
    assert pkt[14] == 255 and pkt[15] == 0

    # Universe 256
    pkt = build_artnet_dmx_packet(dmx_data, universe=256)
    assert pkt[14] == 0 and pkt[15] == 1

    # Universe 300 (0x012C)
    pkt = build_artnet_dmx_packet(dmx_data, universe=300)
    assert pkt[14] == 0x2C and pkt[15] == 0x01

    print("[OK] test_artnet_packet_universe_encoding")


# ============================================================================
# TEST: ArtNetEngine
# ============================================================================

def test_artnet_engine_start_stop():
    """Engine arranca y para sin errores."""
    state = DmxState(cue_channel_map={41: [41]})
    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)

    engine.start()
    assert engine.running is True
    time.sleep(0.15)  # ~6 frames

    stats = engine.get_stats()
    assert stats["running"] is True
    assert stats["frames_sent"] > 0

    engine.stop()
    assert engine.running is False
    print(f"[OK] test_artnet_engine_start_stop (sent {stats['frames_sent']} frames)")


def test_artnet_engine_sends_persistent_state():
    """Engine envía estado DMX persistente (no pulsos)."""
    state = DmxState(cue_channel_map={41: [41]})
    state.fire(41)  # ch41 = 255

    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)
    engine.start()
    time.sleep(0.2)

    # Verificar que el estado sigue en 255 después de muchos frames
    frame = state.snapshot()
    assert frame[40] == 255, "State must persist across frames"

    stats = engine.get_stats()
    assert stats["frames_sent"] > 5
    assert stats["errors"] == 0

    engine.stop()
    print(f"[OK] test_artnet_engine_sends_persistent_state ({stats['frames_sent']} frames)")


def test_artnet_engine_from_json():
    """Carga config desde artnet_config.json."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_root, "artnet_config.json")
    state = DmxState()

    engine = ArtNetEngine.from_json(config_path, state)
    stats = engine.get_stats()
    assert stats["universe"] == 0
    assert stats["configured_fps"] == 40
    assert stats["port"] == 6454
    print("[OK] test_artnet_engine_from_json")


# ============================================================================
# TEST: CueOutputAdapter
# ============================================================================

def test_adapter_fire_kill():
    """Adapter traduce fire/kill a DMX."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})
    adapter = CueOutputAdapter(state)

    adapter.fire(41)
    assert state.get_channel(41) == 255
    assert adapter.is_active(41) is True

    adapter.kill(41)
    assert state.get_channel(41) == 0
    assert adapter.is_active(41) is False
    print("[OK] test_adapter_fire_kill")


def test_adapter_kill_pool():
    """Adapter puede matar múltiples cues."""
    state = DmxState(cue_channel_map={1: [1], 2: [2], 3: [3]})
    adapter = CueOutputAdapter(state)

    adapter.fire(1)
    adapter.fire(2)
    adapter.fire(3)
    assert len(adapter.get_active_cues()) == 3

    count = adapter.kill_pool([1, 2, 3])
    assert count == 3
    assert len(adapter.get_active_cues()) == 0
    print("[OK] test_adapter_kill_pool")


def test_adapter_stats():
    """Stats del adaptador."""
    state = DmxState(cue_channel_map={41: [41]})
    adapter = CueOutputAdapter(state)

    adapter.fire(41)
    adapter.kill(41)
    adapter.fire(999)  # unmapped

    stats = adapter.get_stats()
    assert stats["fires"] == 1
    assert stats["kills"] == 1
    assert stats["unmapped"] == 1
    print("[OK] test_adapter_stats")


# ============================================================================
# TEST: Integration
# ============================================================================

def test_full_pipeline():
    """
    Test end-to-end: Adapter → DmxState → ArtNetEngine.
    Simula el flujo completo como lo haría CueEngine.
    """
    # Setup
    state = DmxState(cue_channel_map={41: [41], 42: [42], 37: [37]})
    adapter = CueOutputAdapter(state)
    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)
    engine.start()

    # Simular: CueEngine hace fire(41)
    adapter.fire(41)
    time.sleep(0.1)

    # Verificar estado persistente
    frame = state.snapshot()
    assert frame[40] == 255, "C41 must be ON (255)"
    assert frame[41] == 0,   "C42 must be OFF (0)"

    # Simular: CueEngine hace fire(42) y kill(41)
    adapter.fire(42)
    adapter.kill(41)
    time.sleep(0.1)

    frame2 = state.snapshot()
    assert frame2[40] == 0,   "C41 must be OFF after kill"
    assert frame2[41] == 255, "C42 must be ON (255)"

    # Verificar stats
    engine_stats = engine.get_stats()
    assert engine_stats["frames_sent"] > 0
    assert engine_stats["errors"] == 0

    engine.stop()
    print(f"[OK] test_full_pipeline ({engine_stats['frames_sent']} frames sent)")


# ============================================================================
# RUN ALL
# ============================================================================

if __name__ == "__main__":
    tests = [
        test_dmx_state_init,
        test_dmx_state_fire_kill,
        test_dmx_state_unmapped_cue,
        test_dmx_state_multi_channel,
        test_dmx_state_kill_all,
        test_dmx_state_active_cues,
        test_dmx_state_thread_safety,
        test_dmx_state_from_json,
        test_dmx_state_persistence,
        test_artnet_packet_structure,
        test_artnet_packet_universe_encoding,
        test_artnet_engine_start_stop,
        test_artnet_engine_sends_persistent_state,
        test_artnet_engine_from_json,
        test_adapter_fire_kill,
        test_adapter_kill_pool,
        test_adapter_stats,
        test_full_pipeline,
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

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        sys.exit(1)
