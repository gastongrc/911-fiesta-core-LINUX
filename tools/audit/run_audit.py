#!/usr/bin/env python3
"""
911 Fiesta V7 - Full Dependency Audit

Generates:
    audit/REPORT.md            – Human-readable audit report
    audit/artifacts/           – Machine-readable artefacts
        pip_freeze.txt
        python_version.txt
        platform.txt
        gpu.txt
        imports_used.json
        entrypoints_test.json
        files_scanned.txt

Usage:
    python tools/audit/run_audit.py [--root /path/to/repo]
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure repo root on sys.path so sibling modules resolve
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


# ======================================================================
# 1. Artifact collectors
# ======================================================================

def collect_pip_freeze(out_dir: Path) -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True, text=True, timeout=60,
        )
        text = result.stdout.strip()
    except Exception as exc:
        text = f"# ERROR: {exc}"
    (out_dir / "pip_freeze.txt").write_text(text + "\n", encoding="utf-8")
    return text


def collect_python_version(out_dir: Path) -> str:
    text = f"{sys.version}\n{sys.executable}"
    (out_dir / "python_version.txt").write_text(text + "\n", encoding="utf-8")
    return text


def collect_platform_info(out_dir: Path) -> dict:
    info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "platform": platform.platform(),
        "python_implementation": platform.python_implementation(),
    }
    lines = [f"{k}: {v}" for k, v in info.items()]
    (out_dir / "platform.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return info


def collect_gpu_info(out_dir: Path) -> str:
    if not shutil.which("nvidia-smi"):
        text = "# nvidia-smi not found — no NVIDIA GPU detected or drivers missing"
    else:
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True, text=True, timeout=15,
            )
            text = result.stdout.strip() or result.stderr.strip() or "# empty output"
        except Exception as exc:
            text = f"# ERROR: {exc}"
    (out_dir / "gpu.txt").write_text(text + "\n", encoding="utf-8")
    return text


def collect_static_imports(repo_root: str, out_dir: Path) -> dict:
    from static_import_scan import scan_directory, build_report  # sibling module
    scan = scan_directory(repo_root)
    report = build_report(scan)
    out_path = out_dir / "imports_used.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    # Also write files_scanned.txt
    (out_dir / "files_scanned.txt").write_text(
        "\n".join(report["files_scanned"]) + "\n", encoding="utf-8"
    )
    return report


def collect_smoke_tests(out_dir: Path) -> dict:
    from runtime_smoke_tests import run_all  # sibling module
    report = run_all()
    out_path = out_dir / "entrypoints_test.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return report


# ======================================================================
# 2. Analysis helpers
# ======================================================================

# Maps pip package name -> apt package candidates (Ubuntu/Debian)
_PIP_TO_APT = {
    "numpy": "python3-numpy",
    "scipy": "python3-scipy",
    "opencv-python": "python3-opencv",
    "opencv-python-headless": "python3-opencv",
    "pillow": "python3-pil",
    "librosa": None,  # pip only
    "sounddevice": "libportaudio2 portaudio19-dev",
    "soundfile": "libsndfile1 libsndfile1-dev",
    "pyaudio": "libportaudio2 portaudio19-dev python3-pyaudio",
    "aubio": "libaubio-dev python3-aubio",
    "torch": None,  # pip/conda only
    "torchvision": None,
    "torchaudio": None,
    "ultralytics": None,
    "PySide6": "libgl1 libegl1 libxkbcommon0 libdbus-1-3",
    "pyqtgraph": None,
    "flask": "python3-flask",
    "fastapi": None,
    "uvicorn": None,
    "pydantic": None,
    "psutil": "python3-psutil",
    "requests": "python3-requests",
    "av": "libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev libswscale-dev libswresample-dev ffmpeg",
    "pandas": "python3-pandas",
    "matplotlib": "python3-matplotlib",
    "scikit-learn": "python3-sklearn",
    "scikit-image": "python3-skimage",
    "h5py": "python3-h5py libhdf5-dev",
    "tensorflow": None,
}

# Classify third-party packages into requirement tiers
_TIER_VISION = {
    "cv2", "opencv", "torch", "torchvision", "ultralytics", "skimage",
    "PIL", "pillow", "av", "tensorflow", "keras", "tf_keras",
    "tensorflow_hub", "tensorboard",
}
_TIER_AUDIO = {
    "librosa", "sounddevice", "soundfile", "audioread", "aubio",
    "torchaudio", "soxr", "numba",
}
_TIER_NETWORK = {
    "pyartnet", "python_artnet", "sacn",
}
_TIER_UI = {
    "PySide6", "PyQt5", "customtkinter", "dearpygui", "pyqtgraph",
    "darkdetect", "pyqt5_sip", "shiboken6",
}

# pip-name normalization: import name -> pip package name
_IMPORT_TO_PIP = {
    "cv2": "opencv-python-headless",
    "PIL": "pillow",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "skimage": "scikit-image",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "gi": "PyGObject",
    "serial": "pyserial",
    "usb": "pyusb",
    "flask_cors": "flask-cors",
    "dateutil": "python-dateutil",
    "shiboken6": "PySide6",
}


def classify_import(name: str) -> str:
    """Return tier: base / vision / audio / network / ui."""
    low = name.lower()
    if low in {n.lower() for n in _TIER_VISION}:
        return "vision"
    if low in {n.lower() for n in _TIER_AUDIO}:
        return "audio"
    if low in {n.lower() for n in _TIER_NETWORK}:
        return "network"
    if low in {n.lower() for n in _TIER_UI}:
        return "ui"
    return "base"


def pip_name(import_name: str) -> str:
    """Best-effort pip package name from an import name."""
    return _IMPORT_TO_PIP.get(import_name, import_name)


def apt_candidates(pip_pkg: str) -> str:
    """Return apt package suggestion or empty string."""
    return _PIP_TO_APT.get(pip_pkg.lower(), _PIP_TO_APT.get(pip_pkg, "")) or ""


# ======================================================================
# 3. Report generator
# ======================================================================

def generate_report(
    repo_root: str,
    platform_info: dict,
    python_version: str,
    gpu_info: str,
    imports_report: dict,
    smoke_report: dict,
    pip_freeze_text: str,
) -> str:
    """Build the full REPORT.md markdown string."""
    now = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    py_ver = sys.version.split()[0]

    # Parse pip freeze into dict
    installed = {}
    for line in pip_freeze_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" in line:
            pkg, ver = line.split("==", 1)
            installed[pkg.strip().lower()] = ver.strip()
        elif "@" in line:
            pkg = line.split("@")[0].strip()
            installed[pkg.lower()] = "(local/git)"

    # Build third-party table
    third_party = imports_report.get("third_party", {})
    table_rows = []
    for imp_name, info in sorted(third_party.items(), key=lambda x: x[0].lower()):
        tier = classify_import(imp_name)
        ppkg = pip_name(imp_name)
        version = installed.get(ppkg.lower(), installed.get(imp_name.lower(), "—"))
        files_list = info.get("files", [])
        sample_files = ", ".join(files_list[:3])
        if len(files_list) > 3:
            sample_files += f" (+{len(files_list) - 3} more)"
        table_rows.append({
            "import": imp_name,
            "pip": ppkg,
            "version": version,
            "tier": tier,
            "refs": info["count"],
            "where": sample_files,
        })

    # Smoke test summary per category
    smoke_by_cat = {}
    for r in smoke_report.get("results", []):
        cat = r["category"]
        if cat not in smoke_by_cat:
            smoke_by_cat[cat] = {"ok": 0, "fail": 0, "skip": 0, "items": []}
        smoke_by_cat[cat]["items"].append(r)
        if r["status"] == "OK":
            smoke_by_cat[cat]["ok"] += 1
        elif r["status"] == "FAIL":
            smoke_by_cat[cat]["fail"] += 1
        else:
            smoke_by_cat[cat]["skip"] += 1

    # GPU status
    has_gpu = "nvidia-smi not found" not in gpu_info and "ERROR" not in gpu_info

    # Infer apt packages
    apt_pkgs: dict[str, str] = {}  # pkg -> reason
    # Always needed on headless Linux
    apt_pkgs["python3"] = "Python interpreter"
    apt_pkgs["python3-pip"] = "pip package manager"
    apt_pkgs["python3-venv"] = "virtual environments"
    apt_pkgs["build-essential"] = "compilation of native extensions"
    apt_pkgs["pkg-config"] = "native lib detection"
    apt_pkgs["git"] = "version control"
    apt_pkgs["ffmpeg"] = "audio/video processing (librosa, av, vision)"
    apt_pkgs["libgl1"] = "OpenCV / Qt headless rendering"
    apt_pkgs["libegl1"] = "PySide6/Qt EGL backend"
    apt_pkgs["libglib2.0-0"] = "OpenCV / GLib dependency"
    apt_pkgs["libxkbcommon0"] = "PySide6/Qt keyboard"
    apt_pkgs["libdbus-1-3"] = "PySide6/Qt D-Bus"
    apt_pkgs["libportaudio2"] = "sounddevice / PyAudio"
    apt_pkgs["portaudio19-dev"] = "sounddevice build"
    apt_pkgs["libsndfile1"] = "soundfile"
    apt_pkgs["libsndfile1-dev"] = "soundfile build"

    for imp_name in third_party:
        ppkg = pip_name(imp_name)
        cand = apt_candidates(ppkg)
        if cand:
            for a in cand.split():
                if a not in apt_pkgs:
                    apt_pkgs[a] = f"required by {ppkg}"

    # ---- Build markdown ----
    lines = []

    def w(s=""):
        lines.append(s)

    w("# 911 Fiesta V7 — Dependency Audit Report")
    w()
    w(f"> Generated: {now}")
    w(f"> Python: {py_ver} (`{sys.executable}`)")
    w(f"> Platform: {platform_info.get('platform', 'unknown')}")
    w(f"> GPU: {'Detected' if has_gpu else 'Not detected'}")
    w()

    # ----- Executive Summary -----
    w("## Executive Summary")
    w()
    w("### Minimum for base (API server, headless)")
    w()
    w("- Python 3.10+ (3.11 recommended)")
    w("- FastAPI + uvicorn + pydantic")
    w("- numpy, scipy, requests, python-dotenv")
    w("- `apt`: python3, python3-pip, python3-venv, build-essential, git")
    w()
    w("### Required for vision (camera/detection)")
    w()
    w("- opencv-python-headless (+ libgl1, libglib2.0-0)")
    w("- torch + torchvision (CPU or CUDA)")
    w("- ultralytics (YOLO)")
    w("- pillow, scikit-image")
    w("- `apt`: ffmpeg, libgl1, libglib2.0-0")
    w()
    w("### Required for audio (BPM/analysis)")
    w()
    w("- librosa, soundfile, sounddevice, audioread, aubio")
    w("- torchaudio")
    w("- `apt`: ffmpeg, libportaudio2, portaudio19-dev, libsndfile1")
    w()
    w("### Required for cameras (RTSP/streaming)")
    w()
    w("- av (PyAV) — RTSP/stream decoding")
    w("- Flask + flask-cors (legacy vision API)")
    w("- `apt`: ffmpeg, libavformat-dev, libavcodec-dev, libswscale-dev")
    w()

    # ----- Runtime Smoke Results -----
    w("## Runtime Smoke Test Results")
    w()
    ss = smoke_report.get("summary", {})
    w(f"**Total: {ss.get('total', 0)}** — "
      f"OK: {ss.get('ok', 0)} | FAIL: {ss.get('fail', 0)} | SKIPPED: {ss.get('skipped', 0)}")
    w()
    w("| Category | Name | Status | Version | Detail |")
    w("|----------|------|--------|---------|--------|")
    for r in smoke_report.get("results", []):
        status_badge = {"OK": "OK", "FAIL": "**FAIL**", "SKIPPED": "SKIP"}[r["status"]]
        w(f"| {r['category']} | {r['name']} | {status_badge} | {r.get('version', '')} | {r.get('detail', '')} |")
    w()

    # ----- Dependency Table -----
    w("## Third-Party Dependency Table")
    w()
    w(f"*{len(table_rows)} third-party packages detected via AST scan.*")
    w()
    w("| Import | pip package | Version | Tier | Refs | Used in |")
    w("|--------|-------------|---------|------|------|---------|")
    for row in sorted(table_rows, key=lambda r: (r["tier"], r["import"].lower())):
        w(f"| `{row['import']}` | {row['pip']} | {row['version']} | {row['tier']} | {row['refs']} | {row['where']} |")
    w()

    # ----- Python Version Recommendation -----
    w("## Python Version Recommendation")
    w()
    w("| Version | Status | Notes |")
    w("|---------|--------|-------|")
    w("| 3.10.x | Supported | Broadest CUDA/torch compatibility |")
    w("| **3.11.x** | **Recommended** | Good balance of speed + compatibility |")
    w("| 3.12.x | Experimental | Some packages may lack wheels |")
    w()

    # ----- APT packages -----
    w("## System (apt) Packages — Ubuntu/Debian")
    w()
    w("| Package | Reason |")
    w("|---------|--------|")
    for pkg in sorted(apt_pkgs):
        w(f"| `{pkg}` | {apt_pkgs[pkg]} |")
    w()

    # ----- Risks -----
    w("## Risks and Notes")
    w()
    w("### CUDA / PyTorch")
    w()
    w("- PyTorch GPU builds require matching CUDA toolkit version.")
    w("- Install via the PyTorch selector: `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`")
    w("- CPU-only fallback: `--index-url https://download.pytorch.org/whl/cpu`")
    w("- TensorFlow is present in requirements.txt but may not be actively used in core — verify before including in production.")
    w()
    w("### OpenCV headless")
    w()
    w("- On headless Linux, use `opencv-python-headless` instead of `opencv-python` to avoid X11 dependencies.")
    w("- Both provide the same `cv2` API; headless omits `imshow`/`waitKey`.")
    w("- Requires `libgl1` and `libglib2.0-0` at minimum.")
    w()
    w("### Audio: PortAudio / sounddevice")
    w()
    w("- `sounddevice` wraps PortAudio — requires `libportaudio2` at runtime.")
    w("- On headless servers with no audio hardware, `sd.query_devices()` may return an empty list; the library still imports fine.")
    w("- `portaudio19-dev` is only needed if building from source.")
    w()
    w("### aubio")
    w()
    w("- The pip `aubio` package often requires compilation — needs `libaubio-dev` or pre-built wheel.")
    w("- Conda alternative: `conda install -c conda-forge aubio`.")
    w()
    w("### PySide6 / Qt on headless")
    w()
    w("- PySide6 is used for the desktop UI. On headless deploy, it can be omitted if only the API server is needed.")
    w("- If imported for any reason on headless, set `QT_QPA_PLATFORM=offscreen` or install `xvfb`.")
    w()
    w("### PyAV (av)")
    w()
    w("- Requires FFmpeg development libraries (`libavformat-dev`, `libavcodec-dev`, etc.).")
    w("- Or install the pre-built wheel: `pip install av` (includes bundled FFmpeg on many platforms).")
    w()

    # ----- Static Scan Summary -----
    w("## Static Import Scan Summary")
    w()
    summary = imports_report.get("summary", {})
    w(f"- Files scanned: **{summary.get('total_files_scanned', 0)}**")
    w(f"- Unique imports: **{summary.get('total_unique_imports', 0)}**")
    w(f"  - stdlib: {summary.get('stdlib_count', 0)}")
    w(f"  - internal: {summary.get('internal_count', 0)}")
    w(f"  - third-party: {summary.get('third_party_count', 0)}")
    w()
    w("See `audit/artifacts/imports_used.json` for full details.")
    w()

    # ----- Files scanned -----
    w("## Files Scanned")
    w()
    w(f"Total: {summary.get('total_files_scanned', 0)} Python files.")
    w("See `audit/artifacts/files_scanned.txt` for the complete list.")
    w()

    w("---")
    w()
    w("*Report generated by `tools/audit/run_audit.py`*")

    return "\n".join(lines)


# ======================================================================
# 4. Main
# ======================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="911 Fiesta V7 — Full dependency audit")
    parser.add_argument("--root", default=None, help="Repository root (default: auto-detect)")
    args = parser.parse_args()

    repo_root = args.root or str(_REPO_ROOT)
    audit_dir = Path(repo_root) / "audit"
    artifacts_dir = audit_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("  911 Fiesta V7 — Dependency Audit")
    print("=" * 64)
    print()

    # 1. Collect artifacts
    print("[1/6] Collecting pip freeze ...")
    pip_text = collect_pip_freeze(artifacts_dir)

    print("[2/6] Collecting Python/platform info ...")
    py_ver = collect_python_version(artifacts_dir)
    plat_info = collect_platform_info(artifacts_dir)

    print("[3/6] Collecting GPU info ...")
    gpu_text = collect_gpu_info(artifacts_dir)

    print("[4/6] Running static import scan ...")
    imports_report = collect_static_imports(repo_root, artifacts_dir)

    print("[5/6] Running runtime smoke tests ...")
    smoke_report = collect_smoke_tests(artifacts_dir)

    # 2. Generate report
    print("[6/6] Generating REPORT.md ...")
    report_md = generate_report(
        repo_root=repo_root,
        platform_info=plat_info,
        python_version=py_ver,
        gpu_info=gpu_text,
        imports_report=imports_report,
        smoke_report=smoke_report,
        pip_freeze_text=pip_text,
    )
    (audit_dir / "REPORT.md").write_text(report_md + "\n", encoding="utf-8")

    print()
    print("Done! Outputs:")
    print(f"  Report:    {audit_dir / 'REPORT.md'}")
    print(f"  Artifacts: {artifacts_dir}/")
    for f in sorted(artifacts_dir.iterdir()):
        print(f"    - {f.name}")

    # Quick summary
    ss = smoke_report.get("summary", {})
    s = imports_report.get("summary", {})
    print()
    print(f"  Static scan: {s.get('third_party_count', '?')} third-party packages across {s.get('total_files_scanned', '?')} files")
    print(f"  Smoke tests: {ss.get('ok', 0)} OK / {ss.get('fail', 0)} FAIL / {ss.get('skipped', 0)} SKIPPED")
    print()


if __name__ == "__main__":
    main()
