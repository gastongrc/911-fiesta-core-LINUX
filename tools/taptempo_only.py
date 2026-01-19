#!/usr/bin/env python3
"""
taptempo_only.py - Standalone TapTempo runner for 911 Fiesta
============================================================
Uses the EXACT same audio pipeline as the main app:
- sounddevice.InputStream (same as engine_audio.py)
- KickPulseDetector V14 (sample-accurate timestamps)
- AutoClock V10 (interval-gated anti-double hit)

Usage:
    python tools/taptempo_only.py
    python tools/taptempo_only.py --device 2
    python tools/taptempo_only.py --list-devices

NO TitanQueue, NO Vision, NO CueEngine, NO StateManager.
Just pure audio → kick detection → BPM tracking.
"""

import sys
import os
import time
import argparse
import threading

# Add parent directory to path for imports
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import numpy as np
import sounddevice as sd

from tempo.kick_detector import KickPulseDetector
from tempo.auto_clock import AutoClock, LockState


class TapTempoRunner:
    """
    Standalone TapTempo runner using sounddevice + KickPulseDetector + AutoClock.

    Uses same audio params as main app:
    - blocksize: 1024 samples
    - samplerate: from device or 44100
    - channels: 2 (stereo, converted to mono for detection)
    """

    DEFAULT_BLOCKSIZE = 1024
    DEFAULT_SAMPLERATE = 44100

    def __init__(self, device_index=None, blocksize=None, samplerate=None):
        self.device_index = device_index
        self.blocksize = blocksize or self.DEFAULT_BLOCKSIZE
        self.req_samplerate = samplerate
        self.samplerate = None

        self.stream = None
        self.running = False

        # Initialize KickPulseDetector V14
        self.kick_detector = KickPulseDetector(
            debounce_ms=150.0,
            threshold_k=2.5,
            lp_cutoff_hz=150.0
        )

        # Initialize AutoClock V10
        self.auto_clock = AutoClock(interval_ms=600, correction_period=2.0)

        # Stats
        self._total_blocks = 0
        self._total_kicks = 0
        self._start_time = None

        # Lock for thread-safe access
        self._lock = threading.Lock()

    def _audio_callback(self, indata, frames, time_info, status):
        """
        Audio callback from sounddevice.

        Args:
            indata: Input audio data (frames x channels)
            frames: Number of frames in this block
            time_info: Timing info with input_buffer_adc_time
            status: Stream status flags
        """
        if status:
            print(f"[AUDIO] Status: {status}")

        # Get block_start_ts from sounddevice time_info (ADC time)
        # This is the most accurate timestamp available
        try:
            block_start_ts = time_info.input_buffer_adc_time
        except:
            block_start_ts = time.monotonic()

        # Convert to float32 mono
        x = np.asarray(indata, dtype=np.float32)
        if x.ndim == 2:
            x = x.mean(axis=1)

        # Process with KickPulseDetector V14 (sample-accurate)
        kick_detected = self.kick_detector.process_audio(
            x,
            self.samplerate,
            block_start_ts=block_start_ts
        )

        with self._lock:
            self._total_blocks += 1
            if kick_detected:
                self._total_kicks += 1

    def _process_kicks(self):
        """
        Process detected kicks from KickPulseDetector queue.
        Called from main thread.
        """
        kicks = self.kick_detector.pop_all_kicks()

        for kick_ts in kicks:
            # Feed AutoClock V10 with kick timestamp
            self.auto_clock.register_hit(kick_ts)

            # Log current state
            state = self.auto_clock.get_lock_state()
            bpm = self.auto_clock.get_bpm()
            interval = self.auto_clock.get_interval_ms()

            state_str = state.value
            print(f"[TapTempo] BPM={bpm:.1f} interval={interval:.0f}ms state={state_str}")

    def start(self):
        """Start audio stream and processing."""
        if self.running:
            return

        # Get device info
        if self.device_index is not None:
            dev = self.device_index
        else:
            dev = sd.default.device[0]

        info = sd.query_devices(dev, 'input')
        self.samplerate = int(self.req_samplerate or info['default_samplerate'])

        print(f"[TapTempo] Starting with device={dev} ({info['name']})")
        print(f"[TapTempo] samplerate={self.samplerate} blocksize={self.blocksize}")
        print(f"[TapTempo] KickDetector V14 + AutoClock V10")
        print("-" * 60)

        # Create stream (same as engine_audio.py)
        self.stream = sd.InputStream(
            device=dev,
            channels=2,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            dtype='float32',
            callback=self._audio_callback
        )

        self.stream.start()
        self.running = True
        self._start_time = time.time()

        print("[TapTempo] Stream started. Press Ctrl+C to stop.")
        print("")

    def stop(self):
        """Stop audio stream."""
        if not self.running:
            return

        try:
            self.stream.stop()
            self.stream.close()
        except:
            pass

        self.stream = None
        self.running = False

        # Print stats
        elapsed = time.time() - self._start_time if self._start_time else 0
        print("")
        print("-" * 60)
        print(f"[TapTempo] Stopped after {elapsed:.1f}s")
        print(f"[TapTempo] Total blocks: {self._total_blocks}")
        print(f"[TapTempo] Total kicks: {self._total_kicks}")

        final_bpm = self.auto_clock.get_bpm()
        final_state = self.auto_clock.get_lock_state().value
        print(f"[TapTempo] Final BPM: {final_bpm:.1f} State: {final_state}")

    def run(self):
        """Main loop - process kicks and apply corrections."""
        self.start()

        try:
            while self.running:
                # Process any detected kicks
                self._process_kicks()

                # Apply AutoClock corrections periodically
                self.auto_clock.apply_correction()

                # Sleep to avoid busy loop (same cadence as main app)
                time.sleep(0.016)  # ~60Hz

        except KeyboardInterrupt:
            print("\n[TapTempo] Interrupted by user")
        finally:
            self.stop()


def list_devices():
    """List available audio input devices."""
    print("Available audio input devices:")
    print("-" * 60)

    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            default = " (default)" if i == sd.default.device[0] else ""
            print(f"  [{i}] {dev['name']}{default}")
            print(f"       Channels: {dev['max_input_channels']}, SR: {dev['default_samplerate']}")

    print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Standalone TapTempo runner for 911 Fiesta",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python tools/taptempo_only.py                    # Use default device
    python tools/taptempo_only.py --device 2         # Use device index 2
    python tools/taptempo_only.py --list-devices     # List available devices
    python tools/taptempo_only.py --blocksize 512    # Use smaller block size
        """
    )

    parser.add_argument(
        '--device', '-d',
        type=int,
        default=None,
        help='Audio input device index (use --list-devices to see options)'
    )

    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help='List available audio input devices and exit'
    )

    parser.add_argument(
        '--blocksize', '-b',
        type=int,
        default=1024,
        help='Audio block size in samples (default: 1024)'
    )

    parser.add_argument(
        '--samplerate', '-s',
        type=int,
        default=None,
        help='Sample rate (default: from device)'
    )

    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return 0

    print("=" * 60)
    print("TapTempo Only - 911 Fiesta Standalone Runner")
    print("=" * 60)
    print("")

    runner = TapTempoRunner(
        device_index=args.device,
        blocksize=args.blocksize,
        samplerate=args.samplerate
    )

    runner.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
