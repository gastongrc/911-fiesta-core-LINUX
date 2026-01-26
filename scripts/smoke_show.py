#!/usr/bin/env python3
"""
Smoke Test - SHOW Runtime (911 Fiesta V7)

Valida que todas las dependencias criticas estan instaladas correctamente.
Exit code 0 = OK, Exit code 1 = FAIL

Uso:
    python scripts/smoke_show.py
"""
import sys

# Track results
results = []
failed = False


def check(name: str, test_func):
    """Run a test and record result."""
    global failed
    try:
        result = test_func()
        if result:
            print(f"[OK] {name}: {result}")
            results.append((name, "OK", result))
        else:
            print(f"[OK] {name}")
            results.append((name, "OK", ""))
    except ImportError as e:
        print(f"[FAIL] {name}: ImportError - {e}")
        results.append((name, "FAIL", str(e)))
        failed = True
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__} - {e}")
        results.append((name, "FAIL", str(e)))
        failed = True


def main():
    global failed

    print("=" * 60)
    print("SMOKE TEST - 911 Fiesta V7 SHOW Runtime")
    print("=" * 60)
    print()

    # === Core Scientific ===
    print("--- Core Scientific ---")

    check("numpy", lambda: __import__("numpy").__version__)
    check("scipy", lambda: __import__("scipy").__version__)

    # === Qt UI ===
    print("\n--- Qt UI Framework ---")

    def check_pyside6():
        from PySide6 import __version__
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        return __version__
    check("PySide6", check_pyside6)

    def check_pyqtgraph():
        import pyqtgraph
        return pyqtgraph.__version__
    check("pyqtgraph", check_pyqtgraph)

    # === Audio ===
    print("\n--- Audio ---")

    def check_sounddevice():
        import sounddevice as sd
        # List devices to verify portaudio works
        devices = sd.query_devices()
        return f"{sd.__version__} ({len(devices)} devices)"
    check("sounddevice", check_sounddevice)

    def check_librosa():
        import librosa
        return librosa.__version__
    check("librosa", check_librosa)

    # === Video/Vision ===
    print("\n--- Video/Vision ---")

    def check_opencv():
        import cv2
        return cv2.__version__
    check("cv2 (OpenCV)", check_opencv)

    def check_av():
        import av
        return av.__version__
    check("av (PyAV)", check_av)

    # === PyTorch + YOLO ===
    print("\n--- PyTorch + YOLO ---")

    def check_torch():
        import torch
        cuda_avail = torch.cuda.is_available()
        device_name = ""
        if cuda_avail:
            try:
                device_name = torch.cuda.get_device_name(0)
            except:
                device_name = "CUDA device"
        return f"{torch.__version__} (CUDA: {cuda_avail}{', ' + device_name if device_name else ''})"
    check("torch", check_torch)

    def check_ultralytics():
        from ultralytics import YOLO
        # Don't load model, just verify import works
        return "OK (YOLO class available)"
    check("ultralytics", check_ultralytics)

    # === Network ===
    print("\n--- Network ---")

    check("requests", lambda: __import__("requests").__version__)

    # === Flask (legacy) ===
    print("\n--- Flask Legacy ---")

    def check_flask():
        import flask
        from flask_cors import CORS
        return flask.__version__
    check("Flask + flask-cors", check_flask)

    # === Utilities ===
    print("\n--- Utilities ---")

    check("psutil", lambda: __import__("psutil").__version__)
    def check_dotenv():
        import dotenv
        try:
            from importlib.metadata import version
            return version("python-dotenv")
        except Exception:
            return "imported"
    check("python-dotenv", check_dotenv)

    # === Internal Modules (quick check) ===
    print("\n--- Internal Modules (import check) ---")

    def check_internal(module_name):
        def _check():
            __import__(module_name)
            return "imported"
        return _check

    # Add project root to path
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    check("engine_audio", check_internal("engine_audio"))
    check("state_manager", check_internal("state_manager"))
    check("cue_engine", check_internal("cue_engine"))

    # === Summary ===
    print()
    print("=" * 60)

    ok_count = sum(1 for _, status, _ in results if status == "OK")
    fail_count = sum(1 for _, status, _ in results if status == "FAIL")

    print(f"Results: {ok_count} OK, {fail_count} FAIL")
    print()

    if failed:
        print("SMOKE TEST FAILED")
        print()
        print("Failed components:")
        for name, status, msg in results:
            if status == "FAIL":
                print(f"  - {name}: {msg}")
        print()
        print("Please install missing dependencies:")
        print("  pip install -r requirements/show.lock.txt")
        print()
        print("For PyTorch with CUDA:")
        print("  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        sys.exit(1)
    else:
        print("SMOKE TEST PASSED")
        print()
        print("All SHOW runtime dependencies are correctly installed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
