#!/usr/bin/env python3
"""
Golden sACN Sender — Emisor E1.31 mínimo de referencia.

NO usa ningún código de 911 Fiesta.
Construye el paquete E1.31 desde cero, byte a byte, según ANSI E1.31-2018.

Uso:
    python3 tools/golden_sacn_sender.py          # emite ch1=255, 10 frames
    python3 tools/golden_sacn_sender.py --dump    # solo imprime hex dump sin enviar

Si Titan recibe esto correctamente, el bug está en SacnEngine.
Si Titan NO recibe esto, el problema es de red/configuración.
"""

import argparse
import socket
import struct
import time
import uuid


# ============================================================================
# E1.31 CONSTANTS (from ANSI E1.31-2018 spec)
# ============================================================================

# ACN Packet Identifier: "ASC-E1.17" + 3 null bytes = 12 bytes
# This is the ONLY correct value per ANSI E1.17 / E1.31
ACN_IDENTIFIER = b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"
assert len(ACN_IDENTIFIER) == 12, f"ACN identifier must be 12 bytes, got {len(ACN_IDENTIFIER)}"

VECTOR_ROOT = 0x00000004   # E1.31 Data Packet
VECTOR_FRAME = 0x00000002  # E1.31 Data Packet
VECTOR_DMP = 0x02          # Set Property

SACN_PORT = 5568


def build_golden_packet(
    dmx_data: bytes,
    universe: int = 1,
    sequence: int = 0,
    priority: int = 100,
    cid: bytes = None,
    source_name: str = "Golden sACN Sender",
) -> bytes:
    """
    Build a correct E1.31 Data Packet per ANSI E1.31-2018.

    Packet layout (total 638 bytes for 512 channels):
        Root Layer Preamble:
            [0-1]     Preamble Size:          0x0010 (16)
            [2-3]     Post-amble Size:        0x0000
            [4-15]    ACN Packet Identifier:  12 bytes "ASC-E1.17\0\0\0"
        Root Layer PDU:
            [16-17]   Flags + Length:          0x7000 | 622
            [18-21]   Vector:                 0x00000004
            [22-37]   CID:                    16 bytes
        Framing Layer PDU:
            [38-39]   Flags + Length:          0x7000 | 600
            [40-43]   Vector:                 0x00000002
            [44-107]  Source Name:            64 bytes (null-padded)
            [108]     Priority:               0-200
            [109-110] Sync Address:           0x0000
            [111]     Sequence Number:        0-255
            [112]     Options:                0x00
            [113-114] Universe:               big-endian
        DMP Layer PDU:
            [115-116] Flags + Length:          0x7000 | 523
            [117]     Vector:                 0x02
            [118]     Address Type:           0xA1
            [119-120] First Property Address: 0x0000
            [121-122] Address Increment:      0x0001
            [123-124] Property Value Count:   0x0201 (513)
            [125]     Start Code:             0x00
            [126-637] DMX Data:               512 bytes
    """
    if cid is None:
        cid = uuid.uuid4().bytes

    # Ensure 512 bytes of DMX data
    dmx = bytearray(dmx_data[:512])
    if len(dmx) < 512:
        dmx.extend(b"\x00" * (512 - len(dmx)))

    # Property values: start code (0x00) + 512 DMX channels = 513 bytes
    prop_values = b"\x00" + bytes(dmx)
    prop_count = 513

    # ---- DMP Layer PDU ----
    dmp_length = 10 + prop_count  # 523
    dmp = bytearray()
    dmp.extend(struct.pack(">H", 0x7000 | dmp_length))  # Flags + Length
    dmp.append(VECTOR_DMP)                                # Vector: 0x02
    dmp.append(0xA1)                                      # Address Type & Data Type
    dmp.extend(struct.pack(">H", 0x0000))                 # First Property Address
    dmp.extend(struct.pack(">H", 0x0001))                 # Address Increment
    dmp.extend(struct.pack(">H", prop_count))             # Property Value Count: 513
    dmp.extend(prop_values)                               # Start code + DMX data

    # ---- Framing Layer PDU ----
    frame_length = 77 + len(dmp)  # 77 + 523 = 600
    frame = bytearray()
    frame.extend(struct.pack(">H", 0x7000 | frame_length))  # Flags + Length
    frame.extend(struct.pack(">I", VECTOR_FRAME))             # Vector: 0x00000002
    # Source Name: 64 bytes, null-padded
    name_bytes = source_name.encode("utf-8")[:63]
    frame.extend(name_bytes.ljust(64, b"\x00"))
    frame.append(min(200, max(0, priority)))                  # Priority
    frame.extend(struct.pack(">H", 0x0000))                   # Sync Address
    frame.append(sequence & 0xFF)                             # Sequence Number
    frame.append(0x00)                                        # Options
    frame.extend(struct.pack(">H", universe))                 # Universe
    frame.extend(dmp)

    # ---- Root Layer ----
    root_length = 22 + len(frame)  # 22 + 600 = 622
    packet = bytearray()
    # Preamble (NOT part of the ACN identifier)
    packet.extend(struct.pack(">H", 0x0010))                  # Preamble Size: 16
    packet.extend(struct.pack(">H", 0x0000))                  # Post-amble Size: 0
    # ACN Packet Identifier (12 bytes, NOT 16)
    packet.extend(ACN_IDENTIFIER)
    # Root Layer PDU
    packet.extend(struct.pack(">H", 0x7000 | root_length))   # Flags + Length
    packet.extend(struct.pack(">I", VECTOR_ROOT))              # Vector: 0x00000004
    packet.extend(cid[:16].ljust(16, b"\x00"))                # CID: 16 bytes
    # Framing + DMP
    packet.extend(frame)

    return bytes(packet)


def multicast_ip(universe: int) -> str:
    """E1.31 multicast: 239.255.<hi>.<lo>"""
    hi = (universe >> 8) & 0xFF
    lo = universe & 0xFF
    return f"239.255.{hi}.{lo}"


def hex_dump(data: bytes, label: str = "") -> None:
    """Print hex dump with offsets and ASCII."""
    if label:
        print(f"\n{'='*70}")
        print(f"  {label}")
        print(f"  Total size: {len(data)} bytes")
        print(f"{'='*70}")
    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  {i:04x}  {hex_part:<48s}  {ascii_part}")


def annotated_dump(packet: bytes) -> None:
    """Print annotated field-by-field breakdown."""
    print(f"\n{'='*70}")
    print(f"  ANNOTATED E1.31 PACKET BREAKDOWN")
    print(f"  Total: {len(packet)} bytes")
    print(f"{'='*70}")

    def show(name, offset, length, expected=None):
        data = packet[offset:offset+length]
        hex_str = " ".join(f"{b:02x}" for b in data)
        status = ""
        if expected is not None:
            if isinstance(expected, bytes):
                status = " OK" if data == expected else " *** MISMATCH ***"
            elif isinstance(expected, int):
                val = int.from_bytes(data, "big")
                status = " OK" if val == expected else f" *** EXPECTED {expected}, GOT {val} ***"
        print(f"  [{offset:3d}-{offset+length-1:3d}] {name:30s} = {hex_str}{status}")

    print("\n  --- Root Layer Preamble ---")
    show("Preamble Size", 0, 2, 0x0010)
    show("Post-amble Size", 2, 2, 0x0000)
    show("ACN Packet Identifier", 4, 12, ACN_IDENTIFIER)

    print("\n  --- Root Layer PDU ---")
    show("Flags + Length", 16, 2)
    show("Vector", 18, 4, VECTOR_ROOT)
    show("CID", 22, 16)

    print("\n  --- Framing Layer PDU ---")
    show("Flags + Length", 38, 2)
    show("Vector", 40, 4, VECTOR_FRAME)
    show("Source Name (first 20)", 44, 20)
    show("Priority", 108, 1)
    show("Sync Address", 109, 2, 0x0000)
    show("Sequence", 111, 1)
    show("Options", 112, 1, 0x00)
    show("Universe", 113, 2)

    print("\n  --- DMP Layer PDU ---")
    show("Flags + Length", 115, 2)
    show("Vector", 117, 1, VECTOR_DMP)
    show("Address Type", 118, 1, 0xA1)
    show("First Property Address", 119, 2, 0x0000)
    show("Address Increment", 121, 2, 0x0001)
    show("Property Value Count", 123, 2, 513)
    show("Start Code", 125, 1, 0x00)

    print("\n  --- DMX Data (first 50 channels) ---")
    for i in range(50):
        val = packet[126 + i]
        if val > 0:
            print(f"  [ch{i+1:3d}] = {val:3d}  (offset {126+i})")
    zero_count = sum(1 for b in packet[126:638] if b == 0)
    nonzero_count = 512 - zero_count
    print(f"\n  Non-zero channels: {nonzero_count}")
    print(f"  Zero channels: {zero_count}")


def main():
    parser = argparse.ArgumentParser(description="Golden sACN E1.31 sender")
    parser.add_argument("--dump", action="store_true", help="Only print hex dump, don't send")
    parser.add_argument("--frames", type=int, default=10, help="Number of frames to send")
    parser.add_argument("--universe", type=int, default=1, help="Universe number")
    parser.add_argument("--fps", type=int, default=40, help="Frames per second")
    args = parser.parse_args()

    # DMX data: channel 1 = 255, channel 41 = 255, rest = 0
    dmx = bytearray(512)
    dmx[0] = 255   # Channel 1
    dmx[40] = 255   # Channel 41

    cid = uuid.uuid4().bytes

    packet = build_golden_packet(
        dmx_data=dmx,
        universe=args.universe,
        sequence=0,
        priority=100,
        cid=cid,
        source_name="Golden sACN Sender",
    )

    print(f"Packet size: {len(packet)} bytes (expected: 638)")
    assert len(packet) == 638, f"WRONG SIZE: {len(packet)} (expected 638)"

    annotated_dump(packet)
    hex_dump(packet, "GOLDEN PACKET — Full hex dump")

    if args.dump:
        print("\n[--dump mode] Not sending to network.")
        return

    # Send
    dest_ip = multicast_ip(args.universe)
    print(f"\nSending {args.frames} frames to {dest_ip}:{SACN_PORT} (universe {args.universe})")
    print(f"DMX: ch1=255, ch41=255, rest=0")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    interval = 1.0 / args.fps
    for i in range(args.frames):
        pkt = build_golden_packet(
            dmx_data=dmx,
            universe=args.universe,
            sequence=i & 0xFF,
            priority=100,
            cid=cid,
            source_name="Golden sACN Sender",
        )
        sock.sendto(pkt, (dest_ip, SACN_PORT))
        print(f"  Frame {i+1}/{args.frames} sent (seq={i & 0xFF})")
        if i < args.frames - 1:
            time.sleep(interval)

    sock.close()
    print(f"\nDone. {args.frames} frames sent.")


if __name__ == "__main__":
    main()
