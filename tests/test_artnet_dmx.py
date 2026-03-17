"""
Tests para el sistema Art-Net DMX: DmxState, ArtNetEngine, CueOutputAdapter.
Single-channel toggle mode: fire and kill pulse the SAME channel.
"""
import json
import socket
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
from core.transport.artnet_engine import (
    ArtNetEngine, build_artnet_dmx_packet, build_artpoll_reply,
    ARTNET_PORT, ARTNET_HEADER, ARTNET_OPCODE_POLL, _is_artpoll,
)
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
    """fire() and kill() both pulse the SAME channel."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})

    # FIRE C41 — pulse on ch 41
    result = state.fire(41)
    assert result is True
    assert state.get_channel(41) == 255  # fire pulse pending

    frame = state.snapshot()
    assert frame[40] == 255  # fire ch 41 (index 40)

    # Auto-reset
    frame2 = state.snapshot()
    assert frame2[40] == 0

    # KILL C41 — pulse on SAME channel 41 (toggle)
    result = state.kill(41)
    assert result is True
    assert state.get_channel(41) == 255  # kill pulse on same channel

    frame3 = state.snapshot()
    assert frame3[40] == 255  # same channel as fire

    # Auto-reset
    frame4 = state.snapshot()
    assert frame4[40] == 0

    print("[OK] test_dmx_state_fire_kill")


def test_dmx_state_unmapped_cue():
    """Cue sin mapeo retorna False for both fire and kill."""
    state = DmxState(cue_channel_map={1: [1]})
    assert state.fire(999) is False
    assert state.kill(999) is False

    # Mapped cue works for both
    assert state.fire(1) is True
    assert state.kill(1) is True
    print("[OK] test_dmx_state_unmapped_cue")


def test_dmx_state_multi_channel():
    """Un cue puede controlar múltiples canales — all pulse in 1 frame."""
    state = DmxState(cue_channel_map={1: [1, 2, 3]})
    state.fire(1)
    frame = state.snapshot()
    assert frame[0] == 255
    assert frame[1] == 255
    assert frame[2] == 255
    assert frame[3] == 0  # canal 4 no afectado

    # Auto-reset after snapshot
    frame2 = state.snapshot()
    assert frame2[0] == 0
    assert frame2[1] == 0
    assert frame2[2] == 0
    print("[OK] test_dmx_state_multi_channel")


def test_dmx_state_kill_all():
    """kill_all() forces all channels to 0 immediately."""
    state = DmxState(cue_channel_map={1: [1], 2: [2], 3: [3]})
    state.fire(1)
    state.fire(2)
    state.fire(3)

    # kill_all before snapshot — clears pending pulses too
    state.kill_all()
    frame = state.snapshot()
    assert all(v == 0 for v in frame)
    print("[OK] test_dmx_state_kill_all")


def test_dmx_state_toggle_same_channel():
    """Toggle: fire and kill use the same channel — both produce identical pulses."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})

    # No sustained active cues
    assert len(state.get_active_cues()) == 0

    # Fire + kill same cue before snapshot — same channel pulsed (not doubled)
    state.fire(41)
    state.kill(41)
    frame = state.snapshot()
    assert frame[40] == 255  # ch 41 pulsed
    # No other channels affected
    assert frame[41] == 0   # ch 42 not touched

    # Auto-reset
    frame2 = state.snapshot()
    assert frame2[40] == 0

    # Fire two cues, kill one — 2 channels pulsed (fire ch 41, kill ch 42 = same as fire ch 42)
    state.fire(41)
    state.fire(42)
    state.kill(42)  # same channel as fire(42)
    frame3 = state.snapshot()
    assert frame3[40] == 255  # ch 41
    assert frame3[41] == 255  # ch 42 (fire and kill both pulsed it)

    print("[OK] test_dmx_state_toggle_same_channel")


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

    # Fire y verificar pulse
    state.fire(41)
    assert state.get_channel(41) == 255  # pending
    frame = state.snapshot()
    assert frame[40] == 255              # captured
    assert state.get_channel(41) == 0    # auto-reset
    print("[OK] test_dmx_state_from_json")


def test_dmx_state_pulse_single_frame():
    """Pulse lasts exactly 1 frame — value present in first snapshot only."""
    state = DmxState(cue_channel_map={41: [41]})
    state.fire(41)

    # First snapshot captures the pulse
    frame1 = state.snapshot()
    assert frame1[40] == 255, "First frame must have pulse value"

    # All subsequent snapshots must be 0
    for i in range(10):
        frame = state.snapshot()
        assert frame[40] == 0, f"Frame {i+2} must be 0 after pulse"

    print("[OK] test_dmx_state_pulse_single_frame")


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


def test_artnet_engine_sends_pulse():
    """Engine sends pulse and auto-resets — channel is 0 after first frame."""
    state = DmxState(cue_channel_map={41: [41]})
    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)
    engine.start()

    state.fire(41)  # ch41 = 255 for 1 frame
    time.sleep(0.2)  # Engine consumes pulse via snapshot

    # After engine consumed the pulse, channel must be 0
    assert state.get_channel(41) == 0, "Pulse must auto-reset after engine snapshot"

    stats = engine.get_stats()
    assert stats["frames_sent"] > 5
    assert stats["errors"] == 0

    engine.stop()
    print(f"[OK] test_artnet_engine_sends_pulse ({stats['frames_sent']} frames)")


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
    """Adapter fire and kill both pulse the SAME channel."""
    state = DmxState(cue_channel_map={41: [41], 42: [42]})
    adapter = CueOutputAdapter(state)

    # Fire pulse
    adapter.fire(41)
    assert state.get_channel(41) == 255  # fire pulse pending
    frame = state.snapshot()
    assert frame[40] == 255              # fire captured
    assert state.get_channel(41) == 0    # auto-reset

    # Kill pulse — on SAME channel
    adapter.kill(41)
    assert state.get_channel(41) == 255  # kill pulse on same channel
    frame2 = state.snapshot()
    assert frame2[40] == 255             # kill captured on same channel
    assert state.get_channel(41) == 0    # auto-reset

    # is_active always False in pulse mode
    assert adapter.is_active(41) is False

    print("[OK] test_adapter_fire_kill")


def test_adapter_kill_pool():
    """Adapter kill_pool generates kill pulses on SAME channels as fire."""
    state = DmxState(cue_channel_map={1: [1], 2: [2], 3: [3]})
    adapter = CueOutputAdapter(state)

    # Fire 3 cues
    adapter.fire(1)
    adapter.fire(2)
    adapter.fire(3)
    frame = state.snapshot()
    assert frame[0] == 255
    assert frame[1] == 255
    assert frame[2] == 255

    # kill_pool generates kill pulses on SAME channels
    count = adapter.kill_pool([1, 2, 3])
    assert count == 3
    frame2 = state.snapshot()
    assert frame2[0] == 255  # kill cue 1 → ch 1
    assert frame2[1] == 255  # kill cue 2 → ch 2
    assert frame2[2] == 255  # kill cue 3 → ch 3

    print("[OK] test_adapter_kill_pool")


def test_adapter_stats():
    """Stats del adaptador — fires, kills, and unmapped tracked separately."""
    state = DmxState(cue_channel_map={41: [41]})
    adapter = CueOutputAdapter(state)

    adapter.fire(41)
    adapter.kill(41)
    adapter.fire(999)  # unmapped fire
    adapter.kill(999)  # unmapped kill

    stats = adapter.get_stats()
    assert stats["fires"] == 1
    assert stats["kills"] == 1
    assert stats["unmapped"] == 2
    print("[OK] test_adapter_stats")


# ============================================================================
# TEST: Integration
# ============================================================================

def test_multi_cue_same_frame():
    """Multiple fire/kill cues produce a single frame with all channels active.

    DMX must NOT queue — all pulses accumulate in the same frame.
    fire_cue(1), fire_cue(2), fire_cue(3) → one frame: ch1=255, ch2=255, ch3=255.
    Next snapshot resets all to 0.
    """
    cue_map = {i: [i] for i in range(1, 83)}  # 82 cues, channels 1-82
    state = DmxState(cue_channel_map=cue_map)

    # --- Multiple fires in one frame ---
    state.fire(1)
    state.fire(2)
    state.fire(3)
    frame = state.snapshot()
    assert frame[0] == 255, "ch1 fire"
    assert frame[1] == 255, "ch2 fire"
    assert frame[2] == 255, "ch3 fire"
    assert frame[3] == 0,   "ch4 not fired"

    # All reset in next frame
    frame2 = state.snapshot()
    assert frame2[0] == 0
    assert frame2[1] == 0
    assert frame2[2] == 0

    # --- Multiple kills in one frame (same channels as fire) ---
    state.kill(1)
    state.kill(2)
    state.kill(3)
    frame3 = state.snapshot()
    assert frame3[0] == 255, "ch1 kill (same channel as fire)"
    assert frame3[1] == 255, "ch2 kill (same channel as fire)"
    assert frame3[2] == 255, "ch3 kill (same channel as fire)"

    # All channels reset
    frame4 = state.snapshot()
    assert frame4[0] == 0
    assert frame4[1] == 0
    assert frame4[2] == 0

    # --- Mixed fire + kill in one frame ---
    state.fire(41)
    state.kill(42)
    state.fire(1)
    state.kill(1)
    frame5 = state.snapshot()
    assert frame5[40] == 255,  "ch41 fire cue 41"
    assert frame5[41] == 255,  "ch42 kill cue 42 (same channel)"
    assert frame5[0] == 255,   "ch1 fire+kill cue 1 (same channel)"

    # All reset
    frame6 = state.snapshot()
    assert all(v == 0 for v in frame6), "All channels must reset after snapshot"

    print("[OK] test_multi_cue_same_frame")


def test_single_channel_layout():
    """Verify single-channel toggle: fire and kill use same channel.

    With 82 cues on channels 1-82:
      fire cue 41 → ch 41
      kill cue 41 → ch 41 (same!)
      No channels beyond 82 used.
    """
    cue_map = {i: [i] for i in range(1, 83)}
    state = DmxState(cue_channel_map=cue_map)

    # Fire and kill both use ch 41
    state.fire(41)
    frame = state.snapshot()
    assert frame[40] == 255, "fire cue 41 → ch 41 (index 40)"

    state.kill(41)
    frame2 = state.snapshot()
    assert frame2[40] == 255, "kill cue 41 → ch 41 (index 40) — same channel!"

    # First and last cue
    state.fire(1)
    state.kill(82)
    frame3 = state.snapshot()
    assert frame3[0] == 255,  "fire cue 1 → ch 1"
    assert frame3[81] == 255, "kill cue 82 → ch 82"

    # Nothing beyond 82
    assert all(v == 0 for v in frame3[82:]), "No channels beyond 82 should be active"

    print("[OK] test_single_channel_layout")


def test_full_pipeline():
    """
    Test end-to-end: Adapter → DmxState → ArtNetEngine (single-channel toggle).
    Both fire and kill pulse the same channel.
    """
    state = DmxState(cue_channel_map={41: [41], 42: [42], 37: [37]})
    adapter = CueOutputAdapter(state)

    # Fire C41 — pulse on ch 41
    adapter.fire(41)
    frame1 = state.snapshot()
    assert frame1[40] == 255, "C41 fire pulse must be 255"
    assert frame1[41] == 0,   "C42 channel must be 0"

    # Kill C41 — pulse on SAME ch 41
    adapter.kill(41)
    frame2 = state.snapshot()
    assert frame2[40] == 255, "C41 kill pulse must be 255 (same channel)"

    # Auto-reset
    frame3 = state.snapshot()
    assert frame3[40] == 0, "C41 channel must auto-reset"

    # Fire + Kill same frame (concurrent events — same channel)
    adapter.fire(42)
    adapter.kill(41)
    frame4 = state.snapshot()
    assert frame4[41] == 255, "C42 fire pulse"
    assert frame4[40] == 255, "C41 kill pulse (same channel as fire)"

    # With engine running
    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)
    engine.start()

    adapter.fire(37)
    time.sleep(0.1)
    assert state.get_channel(37) == 0, "Fire pulse consumed"

    adapter.kill(37)
    time.sleep(0.1)
    assert state.get_channel(37) == 0, "Kill pulse consumed (same channel)"

    engine_stats = engine.get_stats()
    assert engine_stats["frames_sent"] > 0
    assert engine_stats["errors"] == 0

    engine.stop()
    print(f"[OK] test_full_pipeline ({engine_stats['frames_sent']} frames sent)")


# ============================================================================
# TEST: ArtPoll / ArtPollReply
# ============================================================================

def test_artpoll_reply_structure():
    """Verifica estructura del paquete ArtPollReply."""
    reply = build_artpoll_reply(
        ip_address="192.168.1.100",
        port=6454,
        universe=10,
        short_name="911Fiesta",
        long_name="911 Fiesta DMX Engine",
    )

    # Minimum 239 bytes
    assert len(reply) >= 239

    # Header "Art-Net\0"
    assert reply[0:8] == b"Art-Net\x00"

    # OpCode ArtPollReply 0x2100 (little-endian)
    opcode = struct.unpack_from("<H", reply, 8)[0]
    assert opcode == 0x2100

    # IP Address: 192.168.1.100
    assert reply[10] == 192
    assert reply[11] == 168
    assert reply[12] == 1
    assert reply[13] == 100

    # Port 6454 (little-endian)
    port = struct.unpack_from("<H", reply, 14)[0]
    assert port == 6454

    # Find "911Fiesta" in the packet
    assert b"911Fiesta" in reply
    assert b"911 Fiesta DMX Engine" in reply

    print("[OK] test_artpoll_reply_structure")


def test_artpoll_reply_different_universes():
    """ArtPollReply codifica universo correctamente."""
    reply_u0 = build_artpoll_reply("10.0.0.1", 6454, universe=0)
    reply_u10 = build_artpoll_reply("10.0.0.1", 6454, universe=10)
    reply_u256 = build_artpoll_reply("10.0.0.1", 6454, universe=256)

    # All must be valid packets
    assert len(reply_u0) >= 239
    assert len(reply_u10) >= 239
    assert len(reply_u256) >= 239

    # All have correct header
    for r in [reply_u0, reply_u10, reply_u256]:
        assert r[0:8] == ARTNET_HEADER

    print("[OK] test_artpoll_reply_different_universes")


def test_is_artpoll():
    """_is_artpoll detecta paquetes ArtPoll correctamente."""
    # Valid ArtPoll
    artpoll = bytearray()
    artpoll.extend(ARTNET_HEADER)
    artpoll.extend(struct.pack("<H", ARTNET_OPCODE_POLL))  # 0x2000
    artpoll.extend(struct.pack(">H", 14))  # protocol version
    assert _is_artpoll(bytes(artpoll)) is True

    # Not ArtPoll (OpDmx)
    opdmx = bytearray()
    opdmx.extend(ARTNET_HEADER)
    opdmx.extend(struct.pack("<H", 0x5000))
    opdmx.extend(b"\x00\x0e")
    assert _is_artpoll(bytes(opdmx)) is False

    # Too short
    assert _is_artpoll(b"Art-Net") is False

    # Wrong header
    assert _is_artpoll(b"NotArtNt\x00\x20\x00\x0e") is False

    print("[OK] test_is_artpoll")


def test_artnet_engine_fps_timing():
    """Engine debe enviar a ~40fps (no 1fps)."""
    state = DmxState(cue_channel_map={1: [1]})
    engine = ArtNetEngine(state, target_ip="127.0.0.1", fps=40)

    engine.start()
    time.sleep(0.5)  # 500ms = should get ~20 frames at 40fps

    stats = engine.get_stats()
    engine.stop()

    frames = stats["frames_sent"]
    # At 40fps, 500ms should give ~20 frames. Allow 14-26 range for timing variance.
    assert frames >= 14, f"Expected ~20 frames in 500ms at 40fps, got {frames} (too slow!)"
    assert frames <= 26, f"Expected ~20 frames in 500ms at 40fps, got {frames} (too fast!)"

    actual_fps = stats["actual_fps"]
    assert actual_fps >= 25, f"Actual FPS {actual_fps} is way below configured 40fps"

    print(f"[OK] test_artnet_engine_fps_timing ({frames} frames in 500ms, ~{actual_fps}fps)")


def test_artnet_engine_artpoll_response():
    """Engine responde ArtPoll con ArtPollReply."""
    state = DmxState(cue_channel_map={41: [41]})
    # Use a non-standard port to avoid conflicts
    engine = ArtNetEngine(state, target_ip="127.0.0.1", port=16454, universe=5)
    engine.start()
    time.sleep(0.1)  # let it bind

    # Send ArtPoll to the engine's listener
    poll_packet = bytearray()
    poll_packet.extend(ARTNET_HEADER)
    poll_packet.extend(struct.pack("<H", ARTNET_OPCODE_POLL))
    poll_packet.extend(struct.pack(">H", 14))  # protocol version
    poll_packet.extend(b"\x00\x00")  # TalkToMe + Priority

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)
    sock.sendto(bytes(poll_packet), ("127.0.0.1", 16454))

    # Wait for reply
    try:
        reply_data, reply_addr = sock.recvfrom(1024)
        # Verify it's an ArtPollReply
        assert reply_data[0:8] == ARTNET_HEADER
        opcode = struct.unpack_from("<H", reply_data, 8)[0]
        assert opcode == 0x2100, f"Expected ArtPollReply (0x2100), got 0x{opcode:04X}"
        assert b"911Fiesta" in reply_data
        got_reply = True
    except socket.timeout:
        got_reply = False
    finally:
        sock.close()

    engine.stop()

    stats = engine.get_stats()
    assert got_reply, "Did not receive ArtPollReply"
    assert stats["polls_received"] >= 1
    assert stats["replies_sent"] >= 1
    print(f"[OK] test_artnet_engine_artpoll_response (polls={stats['polls_received']})")


def test_artnet_engine_stats_v2():
    """Stats v2 incluyen polls y node info."""
    state = DmxState()
    engine = ArtNetEngine(state, target_ip="127.0.0.1", universe=7, node_name="TestNode")

    stats = engine.get_stats()
    assert "polls_received" in stats
    assert "replies_sent" in stats
    assert "local_ip" in stats
    assert "node_name" in stats
    assert stats["node_name"] == "TestNode"
    assert stats["universe"] == 7
    print("[OK] test_artnet_engine_stats_v2")


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
        test_dmx_state_toggle_same_channel,
        test_dmx_state_thread_safety,
        test_dmx_state_from_json,
        test_dmx_state_pulse_single_frame,
        test_artnet_packet_structure,
        test_artnet_packet_universe_encoding,
        test_artpoll_reply_structure,
        test_artpoll_reply_different_universes,
        test_is_artpoll,
        test_artnet_engine_start_stop,
        test_artnet_engine_sends_pulse,
        test_artnet_engine_from_json,
        test_artnet_engine_fps_timing,
        test_artnet_engine_artpoll_response,
        test_artnet_engine_stats_v2,
        test_adapter_fire_kill,
        test_adapter_kill_pool,
        test_adapter_stats,
        test_multi_cue_same_frame,
        test_single_channel_layout,
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
