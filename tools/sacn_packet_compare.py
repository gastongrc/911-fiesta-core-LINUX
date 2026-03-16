#!/usr/bin/env python3
"""
sACN Packet Comparator — Byte-by-byte comparison.

Compares the golden sender output vs 911 Fiesta SacnEngine output.
Reports EVERY difference with field name, offset, expected, and actual.
"""

import sys
import os
import struct
import uuid

# ============================================================================
# 1. Build golden packet (inline, no imports from 911 Fiesta)
# ============================================================================

ACN_IDENTIFIER_CORRECT = b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"  # 12 bytes


def build_golden(dmx: bytearray, universe=1, seq=0, priority=100, cid=None, name="Golden"):
    """Build correct E1.31 packet — reference implementation."""
    if cid is None:
        cid = b"\xAA" * 16
    prop_values = b"\x00" + bytes(dmx[:512])
    if len(prop_values) < 513:
        prop_values += b"\x00" * (513 - len(prop_values))

    # DMP
    dmp_len = 10 + 513
    dmp = bytearray()
    dmp.extend(struct.pack(">H", 0x7000 | dmp_len))
    dmp.append(0x02)
    dmp.append(0xA1)
    dmp.extend(struct.pack(">H", 0x0000))
    dmp.extend(struct.pack(">H", 0x0001))
    dmp.extend(struct.pack(">H", 513))
    dmp.extend(prop_values)

    # Frame
    frame_len = 77 + len(dmp)
    frame = bytearray()
    frame.extend(struct.pack(">H", 0x7000 | frame_len))
    frame.extend(struct.pack(">I", 0x00000002))
    frame.extend(name.encode("utf-8")[:63].ljust(64, b"\x00"))
    frame.append(priority)
    frame.extend(struct.pack(">H", 0x0000))
    frame.append(seq & 0xFF)
    frame.append(0x00)
    frame.extend(struct.pack(">H", universe))
    frame.extend(dmp)

    # Root
    root_len = 22 + len(frame)
    pkt = bytearray()
    pkt.extend(struct.pack(">H", 0x0010))       # Preamble
    pkt.extend(struct.pack(">H", 0x0000))       # Postamble
    pkt.extend(ACN_IDENTIFIER_CORRECT)           # 12 bytes
    pkt.extend(struct.pack(">H", 0x7000 | root_len))
    pkt.extend(struct.pack(">I", 0x00000004))
    pkt.extend(cid[:16].ljust(16, b"\x00"))
    pkt.extend(frame)

    return bytes(pkt)


# ============================================================================
# 2. Build 911 Fiesta packet (import from actual codebase)
# ============================================================================

def build_fiesta(dmx: bytearray, universe=1, seq=0, priority=100, cid=None, name="911 Fiesta sACN Engine"):
    """Build packet using actual 911 Fiesta code."""
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, ROOT)

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

    for submod in ["dmx_state", "sacn_engine"]:
        full_name = f"core.transport.{submod}"
        if full_name not in sys.modules:
            sub_spec = importlib.util.spec_from_file_location(
                full_name,
                os.path.join(ROOT, "core", "transport", f"{submod}.py"),
            )
            sub_mod = importlib.util.module_from_spec(sub_spec)
            sys.modules[full_name] = sub_mod
            sub_spec.loader.exec_module(sub_mod)

    from core.transport.sacn_engine import build_sacn_packet

    if cid is None:
        cid = b"\xAA" * 16

    return build_sacn_packet(
        dmx_data=dmx,
        universe=universe,
        sequence=seq,
        priority=priority,
        cid=cid,
        source_name=name,
    )


# ============================================================================
# 3. Field map — what lives at each offset in a CORRECT packet
# ============================================================================

FIELD_MAP_CORRECT = [
    (0, 2, "Preamble Size"),
    (2, 2, "Postamble Size"),
    (4, 12, "ACN Packet Identifier"),
    (16, 2, "Root Flags+Length"),
    (18, 4, "Root Vector"),
    (22, 16, "CID"),
    (38, 2, "Frame Flags+Length"),
    (40, 4, "Frame Vector"),
    (44, 64, "Source Name"),
    (108, 1, "Priority"),
    (109, 2, "Sync Address"),
    (111, 1, "Sequence Number"),
    (112, 1, "Options"),
    (113, 2, "Universe"),
    (115, 2, "DMP Flags+Length"),
    (117, 1, "DMP Vector"),
    (118, 1, "Address Type"),
    (119, 2, "First Property Address"),
    (121, 2, "Address Increment"),
    (123, 2, "Property Value Count"),
    (125, 1, "Start Code"),
    (126, 512, "DMX Data"),
]


# ============================================================================
# 4. Compare
# ============================================================================

def compare_packets(golden: bytes, fiesta: bytes):
    """Byte-by-byte comparison with field annotations."""

    print("=" * 74)
    print("  sACN PACKET COMPARISON: GOLDEN vs 911 FIESTA")
    print("=" * 74)
    print(f"\n  Golden packet size:  {len(golden)} bytes")
    print(f"  Fiesta packet size:  {len(fiesta)} bytes")

    if len(golden) != len(fiesta):
        print(f"\n  *** SIZE MISMATCH: {len(fiesta) - len(golden):+d} bytes ***")
        print(f"  Expected 638, got {len(fiesta)}")
        print(f"  This means {abs(len(fiesta) - len(golden))} extra/missing bytes somewhere.\n")

    # Raw byte-by-byte diff
    diff_count = 0
    first_diff = None
    max_len = max(len(golden), len(fiesta))

    print("\n  --- Byte-by-byte differences ---\n")

    for i in range(max_len):
        g = golden[i] if i < len(golden) else None
        f = fiesta[i] if i < len(fiesta) else None
        if g != f:
            diff_count += 1
            if first_diff is None:
                first_diff = i
            g_str = f"0x{g:02x}" if g is not None else "N/A"
            f_str = f"0x{f:02x}" if f is not None else "N/A"
            # Find which golden field this offset belongs to
            field = "?"
            for (off, sz, name) in FIELD_MAP_CORRECT:
                if off <= i < off + sz:
                    field = name
                    break
            if diff_count <= 60:
                print(f"  offset {i:4d} (0x{i:04x}): golden={g_str}  fiesta={f_str}  [{field}]")

    if diff_count > 60:
        print(f"  ... and {diff_count - 60} more differences")

    print(f"\n  Total differences: {diff_count} bytes")
    if first_diff is not None:
        print(f"  First difference at offset: {first_diff}")

    # Field-level comparison on golden offsets
    print("\n\n  --- Field-level analysis (golden offsets applied to both) ---\n")

    for (off, sz, name) in FIELD_MAP_CORRECT:
        if off + sz > len(golden):
            break
        g_data = golden[off:off+sz]
        f_data = fiesta[off:off+sz] if off + sz <= len(fiesta) else b"<truncated>"

        if g_data == f_data:
            status = "MATCH"
        else:
            status = "*** DIFFERS ***"

        g_hex = " ".join(f"{b:02x}" for b in g_data[:20])
        f_hex = " ".join(f"{b:02x}" for b in f_data[:20]) if isinstance(f_data, (bytes, bytearray)) else str(f_data)

        if sz > 20:
            g_hex += " ..."
            if isinstance(f_data, (bytes, bytearray)):
                f_hex += " ..."

        print(f"  [{off:3d}:{off+sz:3d}] {name:30s} {status}")
        if status != "MATCH":
            print(f"           golden: {g_hex}")
            print(f"           fiesta: {f_hex}")
            # Decode what Fiesta actually has at this offset
            if name == "ACN Packet Identifier" and isinstance(f_data, (bytes, bytearray)):
                ascii_repr = "".join(chr(b) if 32 <= b < 127 else "." for b in f_data)
                print(f"           fiesta ASCII: {ascii_repr}")
            if name == "Root Vector" and isinstance(f_data, (bytes, bytearray)) and len(f_data) == 4:
                val = struct.unpack(">I", f_data)[0]
                print(f"           fiesta value: 0x{val:08x} (expected 0x00000004)")
            if name == "Frame Vector" and isinstance(f_data, (bytes, bytearray)) and len(f_data) == 4:
                val = struct.unpack(">I", f_data)[0]
                print(f"           fiesta value: 0x{val:08x} (expected 0x00000002)")
            if name == "Universe" and isinstance(f_data, (bytes, bytearray)) and len(f_data) == 2:
                val = struct.unpack(">H", f_data)[0]
                print(f"           fiesta value: {val} (expected 1)")

    # Check what Fiesta has at the BUGGY offsets (shifted by 4)
    if len(fiesta) == 642:
        print("\n\n  --- SHIFT ANALYSIS (Fiesta offsets +4 from correct) ---\n")
        print("  Fiesta has 4 extra bytes. Testing if content is shifted by 4...\n")

        # Check if fiesta[offset+4] matches golden[offset] for key fields
        shift = 4
        shifts_match = 0
        shifts_total = 0
        for (off, sz, name) in FIELD_MAP_CORRECT:
            if off < 4:  # Preamble/postamble — these are at the right place
                continue
            if name in ("ACN Packet Identifier", "CID", "Source Name", "DMX Data"):
                continue  # Skip large/variable fields for clarity
            if off + sz > len(golden) or off + shift + sz > len(fiesta):
                continue
            g_data = golden[off:off+sz]
            f_shifted = fiesta[off+shift:off+shift+sz]
            shifts_total += 1
            match = g_data == f_shifted
            if match:
                shifts_match += 1
            label = "MATCH" if match else "DIFFERS"
            g_hex = " ".join(f"{b:02x}" for b in g_data)
            f_hex = " ".join(f"{b:02x}" for b in f_shifted)
            print(f"  {name:30s} golden[{off}] vs fiesta[{off+shift}]: {label}")
            if not match:
                print(f"    golden: {g_hex}")
                print(f"    fiesta: {f_hex}")

        print(f"\n  Shifted fields matching: {shifts_match}/{shifts_total}")
        if shifts_match == shifts_total:
            print("  *** CONFIRMED: Fiesta packet is shifted by 4 bytes ***")
            print("  *** Root cause: Preamble+Postamble duplicated in ACN_PACKET_IDENTIFIER ***")

    # Final diagnosis
    print("\n\n" + "=" * 74)
    print("  DIAGNOSIS")
    print("=" * 74)

    if len(fiesta) == 642 and len(golden) == 638:
        print("""
  BUG CONFIRMED: 911 Fiesta emits 642 bytes instead of 638.

  Root cause:
    ACN_PACKET_IDENTIFIER constant includes preamble+postamble bytes (16 bytes)
    but build_sacn_packet() also writes preamble+postamble explicitly.
    Result: 4 bytes duplicated at the start of the packet.

  Effect:
    Every field after byte 7 is shifted by 4 bytes.
    Titan (and any E1.31 compliant receiver) sees:
      - Corrupted ACN Packet Identifier at offset 4
      - Wrong Root Vector
      - Wrong CID
      - Wrong everything in Framing and DMP layers
      - DMX data at wrong offset (offset 130 instead of 126)

  This is why Titan does not respond: the packet is MALFORMED.

  Fix:
    Change ACN_PACKET_IDENTIFIER from 16 bytes to 12 bytes:
    BEFORE: b"\\x00\\x10\\x00\\x00\\x41\\x53\\x43\\x2d\\x45\\x31\\x2e\\x31\\x37\\x00\\x00\\x00"
    AFTER:  b"\\x41\\x53\\x43\\x2d\\x45\\x31\\x2e\\x31\\x37\\x00\\x00\\x00"
""")
    elif diff_count == 0:
        print("\n  Packets are IDENTICAL. No bugs found in packet construction.")
    else:
        print(f"\n  {diff_count} byte differences found. Manual review required.")


def main():
    # Same DMX data, same CID, same params — only the packet builder differs
    dmx = bytearray(512)
    dmx[0] = 255   # Channel 1 = 255
    dmx[40] = 255   # Channel 41 = 255

    cid = b"\xAA" * 16  # Fixed CID for comparison

    golden = build_golden(dmx, universe=1, seq=0, priority=100, cid=cid, name="Test Source")
    fiesta = build_fiesta(dmx, universe=1, seq=0, priority=100, cid=cid, name="Test Source")

    compare_packets(golden, fiesta)


if __name__ == "__main__":
    main()
