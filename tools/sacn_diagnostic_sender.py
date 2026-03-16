#!/usr/bin/env python3
"""
sACN Diagnostic Sender — Emite directamente desde SacnEngine con payload controlado.

Bypasses CueEngine. Fuerza canales específicos para verificar que Titan recibe.

Uso:
    python3 tools/sacn_diagnostic_sender.py                    # ch1=255, ch41=255, 5 segundos
    python3 tools/sacn_diagnostic_sender.py --seconds 30       # 30 segundos
    python3 tools/sacn_diagnostic_sender.py --channel 1 255    # solo ch1=255
"""

import argparse
import os
import sys
import time

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

from core.transport.dmx_state import DmxState
from core.transport.sacn_engine import SacnEngine


def main():
    parser = argparse.ArgumentParser(description="sACN diagnostic sender using SacnEngine")
    parser.add_argument("--seconds", type=int, default=5, help="Duration in seconds")
    parser.add_argument("--universe", type=int, default=1, help="Universe")
    parser.add_argument("--fps", type=int, default=40, help="FPS")
    parser.add_argument("--channel", nargs=2, type=int, action="append",
                        metavar=("CH", "VAL"), help="Set channel CH to VAL (repeatable)")
    args = parser.parse_args()

    # Create DmxState without cue map — direct channel control
    dmx = DmxState()

    # Default: ch1=255, ch41=255
    channels = args.channel if args.channel else [[1, 255], [41, 255]]

    for ch, val in channels:
        dmx.set_channel(ch, val)
        print(f"  Set channel {ch} = {val}")

    # Create and start engine
    engine = SacnEngine(dmx, universe=args.universe, fps=args.fps)
    engine.start()

    print(f"\n  Emitting sACN on universe {args.universe} for {args.seconds} seconds...")
    print(f"  Multicast: {engine._multicast_ip}:{engine._port}")
    print(f"  FPS: {args.fps}")
    print(f"  Active channels: {channels}")
    print(f"\n  If Titan sees these values, sACN is working correctly.")
    print(f"  Press Ctrl+C to stop early.\n")

    try:
        time.sleep(args.seconds)
    except KeyboardInterrupt:
        print("\n  Interrupted by user.")

    stats = engine.get_stats()
    engine.stop()

    print(f"\n  Done. {stats['frames_sent']} frames sent in {stats['uptime_s']}s")
    print(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    main()
