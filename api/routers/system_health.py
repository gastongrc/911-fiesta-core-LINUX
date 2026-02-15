"""
System Health Router — Métricas REALES del server.

GET /api/v1/status/system

Retorna estado completo: CPU, RAM, disco, GPU (NVIDIA), red, audio, cámaras, Avolites, errores.
NO inventa datos. Si algo no está disponible → null con motivo.
NO rompe endpoints existentes (se suma a status.py).
"""

import os
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

router = APIRouter()

# Ring buffer de errores en memoria
_error_ring: List[Dict[str, Any]] = []
_error_ring_max = 50


def log_error(source: str, message: str):
    """Registra un error en el ring buffer."""
    _error_ring.append({
        "ts": time.time(),
        "time": datetime.now().strftime("%H:%M:%S"),
        "source": source,
        "message": str(message)[:500],
    })
    if len(_error_ring) > _error_ring_max:
        _error_ring.pop(0)


def _run_cmd(cmd: List[str], timeout: float = 5.0) -> Optional[str]:
    """Ejecuta comando y retorna stdout. None si falla."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _safe_float(s: str) -> Optional[float]:
    try:
        return round(float(s), 1)
    except (ValueError, TypeError):
        return None


def _safe_int(s: str) -> Optional[int]:
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _get_cpu() -> dict:
    """CPU metrics from /proc."""
    result: Dict[str, Any] = {"percent": None, "load_avg": None, "cores": None}
    try:
        result["cores"] = os.cpu_count()
    except Exception:
        pass
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            result["load_avg"] = [float(parts[0]), float(parts[1]), float(parts[2])]
    except Exception:
        pass
    try:
        import psutil
        result["percent"] = psutil.cpu_percent(interval=None)
    except ImportError:
        # Fallback: parse /proc/stat (snapshot, not interval)
        try:
            with open("/proc/stat") as f:
                line = f.readline()
                parts = line.split()
                if parts[0] == "cpu" and len(parts) >= 5:
                    user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                    total = user + nice + system + idle
                    if total > 0:
                        result["percent"] = round(100 * (total - idle) / total, 1)
        except Exception:
            pass
    return result


def _get_ram() -> dict:
    """RAM metrics from /proc/meminfo."""
    result: Dict[str, Any] = {"total_mb": None, "used_mb": None, "percent": None}
    try:
        import psutil
        mem = psutil.virtual_memory()
        result["total_mb"] = round(mem.total / (1024 * 1024))
        result["used_mb"] = round(mem.used / (1024 * 1024))
        result["percent"] = mem.percent
    except ImportError:
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(":")] = int(parts[1])
                total = meminfo.get("MemTotal", 0)
                avail = meminfo.get("MemAvailable", 0)
                if total > 0:
                    result["total_mb"] = total // 1024
                    result["used_mb"] = (total - avail) // 1024
                    result["percent"] = round(100 * (total - avail) / total, 1)
        except Exception:
            pass
    return result


def _get_disk() -> dict:
    """Disk usage of /opt/911fiesta (or current working dir)."""
    result: Dict[str, Any] = {"path": None, "total_gb": None, "used_gb": None, "percent": None}
    check_path = "/opt/911fiesta" if os.path.exists("/opt/911fiesta") else os.getcwd()
    result["path"] = check_path
    try:
        import shutil
        usage = shutil.disk_usage(check_path)
        result["total_gb"] = round(usage.total / (1024 ** 3), 1)
        result["used_gb"] = round(usage.used / (1024 ** 3), 1)
        if usage.total > 0:
            result["percent"] = round(100 * usage.used / usage.total, 1)
    except Exception:
        pass
    return result


def _get_gpu() -> Optional[dict]:
    """GPU NVIDIA via nvidia-smi. Retorna null si no hay GPU."""
    output = _run_cmd([
        "nvidia-smi",
        "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,"
        "utilization.memory,memory.used,memory.total,power.draw,power.limit,pstate",
        "--format=csv,noheader,nounits",
    ])
    if output is None:
        return None

    parts = [p.strip() for p in output.split(",")]
    if len(parts) < 10:
        return None

    return {
        "name": parts[0],
        "driver": parts[1],
        "temp_c": _safe_int(parts[2]),
        "gpu_util_pct": _safe_int(parts[3]),
        "mem_util_pct": _safe_int(parts[4]),
        "mem_used_mb": _safe_int(parts[5]),
        "mem_total_mb": _safe_int(parts[6]),
        "power_draw_w": _safe_float(parts[7]),
        "power_limit_w": _safe_float(parts[8]),
        "pstate": parts[9],
    }


def _get_network() -> dict:
    """Network interfaces and status."""
    result: Dict[str, Any] = {
        "interfaces": [],
        "sockets_listen": [],
    }

    # Interfaces via ip -brief addr
    output = _run_cmd(["ip", "-brief", "addr"])
    if output:
        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                state = parts[1]
                ips = parts[2:] if len(parts) > 2 else []
                result["interfaces"].append({
                    "name": name,
                    "state": state,
                    "ips": ips,
                })

    # Listening sockets for relevant ports
    output = _run_cmd(["ss", "-lntup"])
    if output:
        for line in output.split("\n"):
            if any(p in line for p in [":8000", ":8010", ":5000", "uvicorn", "python"]):
                result["sockets_listen"].append(line.strip())

    return result


def _get_audio_devices() -> list:
    """USB audio devices via arecord -l."""
    output = _run_cmd(["arecord", "-l"])
    if output is None:
        return []
    devices = []
    for line in output.split("\n"):
        if "card" in line.lower():
            devices.append(line.strip())
    return devices


def _get_cameras_summary() -> dict:
    """Camera status from CORE snapshot or config."""
    result: Dict[str, Any] = {"configured": 0, "cameras": {}}

    # Try CORE snapshot first
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:8010/core/snapshot")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            snapshot = json.loads(resp.read().decode())
            cameras = snapshot.get("cameras", {})
            for cam_name, cam_data in cameras.items():
                if isinstance(cam_data, dict):
                    result["configured"] += 1
                    result["cameras"][cam_name] = {
                        "online": cam_data.get("online", False),
                        "fps": cam_data.get("fps", 0),
                        "ip": cam_data.get("ip", ""),
                        "status": "ok" if cam_data.get("online") else "down",
                    }
            return result
    except Exception:
        pass

    # Fallback: read config file
    config_paths = [
        "/etc/911fiesta/vision_config.json",
        "/opt/911fiesta/vision_config.json",
        os.path.join(os.getcwd(), "vision_config.json"),
    ]
    for path in config_paths:
        try:
            import json
            with open(path) as f:
                cfg = json.load(f)
            for cam_name, cam_data in cfg.get("cameras", {}).items():
                if cam_data.get("enabled", False):
                    result["configured"] += 1
                    result["cameras"][cam_name] = {
                        "online": None,  # Can't determine without CORE
                        "fps": None,
                        "ip": cam_data.get("host", ""),
                        "status": "unknown",
                    }
            break
        except Exception:
            continue

    return result


def _get_avolites_summary() -> dict:
    """Avolites status from CORE snapshot."""
    result: Dict[str, Any] = {
        "connected": None,
        "host": None,
        "port": None,
        "latency_ms": None,
        "last_error": None,
    }

    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://127.0.0.1:8010/core/snapshot")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            snapshot = json.loads(resp.read().decode())
            avo = snapshot.get("avolites", {})
            result["connected"] = avo.get("connected", False)
            result["host"] = avo.get("ip", "")
            result["port"] = avo.get("port", 4430)
            result["latency_ms"] = avo.get("latency_ms")
            result["last_error"] = avo.get("last_error")
    except Exception:
        pass

    # Fallback: read config
    if result["host"] is None:
        config_paths = [
            "/etc/911fiesta/avolites_config.json",
            "/opt/911fiesta/avolites_config.json",
            os.path.join(os.getcwd(), "avolites_config.json"),
        ]
        for path in config_paths:
            try:
                import json
                with open(path) as f:
                    cfg = json.load(f)
                result["host"] = cfg.get("console_ip", "")
                result["port"] = cfg.get("console_port", 4430)
                break
            except Exception:
                continue

    return result


def _get_process_info() -> Optional[dict]:
    """Process info for the main 911fiesta process."""
    try:
        import psutil
        # Find our own process or main.py / uvicorn
        current = psutil.Process()
        return {
            "pid": current.pid,
            "threads": current.num_threads(),
            "fds": current.num_fds() if hasattr(current, 'num_fds') else None,
            "rss_mb": round(current.memory_info().rss / (1024 * 1024), 1),
            "cpu_pct": current.cpu_percent(interval=None),
            "uptime_s": round(time.time() - current.create_time(), 0),
        }
    except ImportError:
        # Fallback without psutil
        pid = os.getpid()
        result: Dict[str, Any] = {"pid": pid}
        try:
            result["threads"] = len(os.listdir(f"/proc/{pid}/task"))
        except Exception:
            pass
        try:
            with open(f"/proc/{pid}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        result["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
                    elif line.startswith("FDSize:"):
                        result["fds"] = int(line.split()[1])
        except Exception:
            pass
        return result
    except Exception:
        return None


@router.get("/status/system")
async def get_system_health():
    """
    GET /api/v1/status/system

    Métricas REALES del sistema. Sin inventar, sin dependencias raras.
    Si nvidia-smi no existe → gpu: null.
    Si psutil no existe → fallback a /proc.
    """
    t0 = time.time()

    result = {
        "ts": int(time.time()),
        "collected_at": datetime.now().isoformat(),
        "cpu": _get_cpu(),
        "ram": _get_ram(),
        "disk": _get_disk(),
        "gpu": _get_gpu(),
        "network": _get_network(),
        "audio_devices": _get_audio_devices(),
        "cameras": _get_cameras_summary(),
        "avolites": _get_avolites_summary(),
        "process": _get_process_info(),
        "last_errors": list(_error_ring[-20:]),  # últimos 20
        "collection_ms": None,
    }

    result["collection_ms"] = round((time.time() - t0) * 1000, 1)
    return result


@router.get("/status/system/errors")
async def get_system_errors():
    """
    GET /api/v1/status/system/errors

    Ring buffer de últimos errores capturados.
    """
    return {
        "count": len(_error_ring),
        "max": _error_ring_max,
        "errors": list(_error_ring),
    }
