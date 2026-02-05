#!/usr/bin/env python3
"""
911 Fiesta V7 - Runtime Smoke Tests for Linux Headless

Executes minimal import and capability checks without requiring hardware.
Anything unavailable is marked SKIPPED (never crashes).

Usage:
    python tools/audit/runtime_smoke_tests.py [--out entrypoints_test.json]
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path


class SmokeRunner:
    """Collects results from individual smoke checks."""

    def __init__(self):
        self.results: list[dict] = []

    # ------------------------------------------------------------------
    def _record(self, category: str, name: str, status: str,
                detail: str = "", version: str = ""):
        self.results.append({
            "category": category,
            "name": name,
            "status": status,  # OK | FAIL | SKIPPED
            "detail": detail,
            "version": version,
        })

    def check(self, category: str, name: str, fn):
        """Run *fn*; record OK/FAIL/SKIPPED."""
        try:
            ver, detail = fn()
            self._record(category, name, "OK", detail=detail or "", version=ver or "")
        except ImportError as exc:
            self._record(category, name, "FAIL", detail=f"ImportError: {exc}")
        except Exception as exc:
            self._record(category, name, "FAIL", detail=f"{type(exc).__name__}: {exc}")

    def skip(self, category: str, name: str, reason: str):
        self._record(category, name, "SKIPPED", detail=reason)

    # ------------------------------------------------------------------
    def summary(self) -> dict:
        ok = sum(1 for r in self.results if r["status"] == "OK")
        fail = sum(1 for r in self.results if r["status"] == "FAIL")
        skipped = sum(1 for r in self.results if r["status"] == "SKIPPED")
        return {"ok": ok, "fail": fail, "skipped": skipped, "total": len(self.results)}


def _ver(module_name: str):
    """Import a module, return (version, '')."""
    mod = __import__(module_name)
    v = getattr(mod, "__version__", getattr(mod, "VERSION", "imported"))
    return str(v), ""


def _cmd_version(binary: str, args=("--version",)):
    """Run a CLI binary with --version, return (version_string, '')."""
    result = subprocess.run(
        [binary, *args],
        capture_output=True, text=True, timeout=10,
    )
    output = (result.stdout or result.stderr).strip().split("\n")[0]
    return output, ""


# ======================================================================
# Test batteries
# ======================================================================

def run_core_tests(runner: SmokeRunner):
    """Core / base dependencies."""
    runner.check("core", "numpy", lambda: _ver("numpy"))
    runner.check("core", "scipy", lambda: _ver("scipy"))
    runner.check("core", "pandas", lambda: _ver("pandas"))
    runner.check("core", "requests", lambda: _ver("requests"))
    runner.check("core", "python-dotenv", lambda: _ver("dotenv"))
    runner.check("core", "typing_extensions", lambda: _ver("typing_extensions"))
    runner.check("core", "pydantic", lambda: _ver("pydantic"))
    runner.check("core", "PyYAML", lambda: _ver("yaml"))
    runner.check("core", "rich", lambda: _ver("rich"))


def run_api_tests(runner: SmokeRunner):
    """FastAPI / web server stack."""
    runner.check("api", "fastapi", lambda: _ver("fastapi"))
    runner.check("api", "uvicorn", lambda: _ver("uvicorn"))
    runner.check("api", "starlette", lambda: _ver("starlette"))
    runner.check("api", "flask", lambda: _ver("flask"))
    runner.check("api", "flask-cors", lambda: (
        __import__("flask_cors") and ("imported", "")
    ))


def run_vision_tests(runner: SmokeRunner):
    """Vision / camera / ML dependencies."""
    # OpenCV
    def _cv2():
        import cv2
        headless = "headless" in (getattr(cv2, "__file__", "") or "").lower()
        variant = "headless" if headless else "full"
        return cv2.__version__, variant
    runner.check("vision", "opencv (cv2)", _cv2)

    # PyTorch
    def _torch():
        import torch
        cuda = torch.cuda.is_available()
        dev = ""
        if cuda:
            try:
                dev = torch.cuda.get_device_name(0)
            except Exception:
                dev = "cuda device"
        return torch.__version__, f"CUDA={'yes' if cuda else 'no'}{' ' + dev if dev else ''}"
    runner.check("vision", "torch", _torch)

    # torchvision
    runner.check("vision", "torchvision", lambda: _ver("torchvision"))

    # ultralytics (YOLO)
    def _ultra():
        from ultralytics import YOLO  # noqa: F401
        import ultralytics
        return ultralytics.__version__, "YOLO class available"
    runner.check("vision", "ultralytics", _ultra)

    # scikit-image
    runner.check("vision", "scikit-image", lambda: _ver("skimage"))

    # pillow
    def _pil():
        from PIL import Image  # noqa: F401
        import PIL
        return PIL.__version__, ""
    runner.check("vision", "pillow", _pil)


def run_audio_tests(runner: SmokeRunner):
    """Audio capture and analysis dependencies."""
    runner.check("audio", "librosa", lambda: _ver("librosa"))
    runner.check("audio", "soundfile", lambda: _ver("soundfile"))
    runner.check("audio", "audioread", lambda: _ver("audioread"))

    # sounddevice (requires portaudio)
    def _sd():
        import sounddevice as sd
        try:
            devs = sd.query_devices()
            return sd.__version__, f"{len(devs)} audio devices"
        except Exception as exc:
            return sd.__version__, f"portaudio issue: {exc}"
    runner.check("audio", "sounddevice", _sd)

    # aubio
    def _aubio():
        import aubio  # noqa: F401
        v = getattr(aubio, "__version__", getattr(aubio, "version", "imported"))
        return str(v), ""
    runner.check("audio", "aubio", _aubio)

    # torchaudio
    runner.check("audio", "torchaudio", lambda: _ver("torchaudio"))


def run_network_tests(runner: SmokeRunner):
    """Lighting control / network protocol libraries."""
    runner.check("network", "pyartnet", lambda: _ver("pyartnet"))

    def _artnet():
        import python_artnet  # noqa: F401
        return "imported", ""
    runner.check("network", "python-artnet", _artnet)

    runner.check("network", "sacn", lambda: _ver("sacn"))


def run_system_tests(runner: SmokeRunner):
    """System-level binaries and capabilities."""
    # ffmpeg
    if shutil.which("ffmpeg"):
        runner.check("system", "ffmpeg", lambda: _cmd_version("ffmpeg"))
    else:
        runner.skip("system", "ffmpeg", "binary not found in PATH")

    # nvidia-smi
    if shutil.which("nvidia-smi"):
        runner.check("system", "nvidia-smi", lambda: _cmd_version("nvidia-smi"))
    else:
        runner.skip("system", "nvidia-smi", "binary not found (no NVIDIA GPU or drivers)")

    # portaudio (via ldconfig or pkg-config)
    def _portaudio():
        try:
            result = subprocess.run(
                ["pkg-config", "--modversion", "portaudio-2.0"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip(), "via pkg-config"
        except FileNotFoundError:
            pass
        # Fallback: check ldconfig
        try:
            result = subprocess.run(
                ["ldconfig", "-p"],
                capture_output=True, text=True, timeout=5,
            )
            if "libportaudio" in result.stdout:
                return "found", "via ldconfig"
        except FileNotFoundError:
            pass
        raise FileNotFoundError("libportaudio not found")
    runner.check("system", "libportaudio", _portaudio)

    # libsndfile
    def _sndfile():
        try:
            result = subprocess.run(
                ["pkg-config", "--modversion", "sndfile"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip(), "via pkg-config"
        except FileNotFoundError:
            pass
        try:
            result = subprocess.run(
                ["ldconfig", "-p"],
                capture_output=True, text=True, timeout=5,
            )
            if "libsndfile" in result.stdout:
                return "found", "via ldconfig"
        except FileNotFoundError:
            pass
        raise FileNotFoundError("libsndfile not found")
    runner.check("system", "libsndfile", _sndfile)


def run_gpu_tests(runner: SmokeRunner):
    """GPU-specific checks."""
    def _cuda_torch():
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available")
        return torch.version.cuda or "unknown", f"devices={torch.cuda.device_count()}"
    runner.check("gpu", "torch.cuda", _cuda_torch)

    # cuDNN
    def _cudnn():
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available")
        cudnn_ver = torch.backends.cudnn.version()
        return str(cudnn_ver), f"enabled={torch.backends.cudnn.enabled}"
    runner.check("gpu", "cuDNN", _cudnn)


# ======================================================================
# Main
# ======================================================================

def run_all() -> dict:
    """Execute every test battery and return the full report dict."""
    runner = SmokeRunner()

    run_core_tests(runner)
    run_api_tests(runner)
    run_vision_tests(runner)
    run_audio_tests(runner)
    run_network_tests(runner)
    run_system_tests(runner)
    run_gpu_tests(runner)

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "python": sys.version,
        "platform": platform.platform(),
        "summary": runner.summary(),
        "results": runner.results,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Runtime smoke tests for 911 Fiesta V7")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--quiet", action="store_true", help="Suppress stdout")
    args = parser.parse_args()

    report = run_all()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    if not args.quiet:
        s = report["summary"]
        print(f"Python: {report['python'].split()[0]}")
        print(f"Platform: {report['platform']}")
        print()
        for r in report["results"]:
            tag = {"OK": "[  OK  ]", "FAIL": "[ FAIL ]", "SKIPPED": "[ SKIP ]"}[r["status"]]
            ver = f" v{r['version']}" if r["version"] else ""
            det = f"  ({r['detail']})" if r["detail"] else ""
            print(f"  {tag} {r['category']:10s} {r['name']}{ver}{det}")
        print()
        print(f"Total: {s['total']}  OK: {s['ok']}  FAIL: {s['fail']}  SKIPPED: {s['skipped']}")

    return report


if __name__ == "__main__":
    main()
