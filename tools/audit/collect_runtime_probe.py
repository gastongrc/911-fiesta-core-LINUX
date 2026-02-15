#!/usr/bin/env python3
"""
911 Fiesta — Runtime Probe

Conecta a los endpoints locales del sistema y captura métricas durante 30 segundos.
NO modifica nada. Solo lectura.

Uso:
    python3 tools/audit/collect_runtime_probe.py
    python3 tools/audit/collect_runtime_probe.py --duration 60 --interval 2
    python3 tools/audit/collect_runtime_probe.py --output /tmp/probe_result.json
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional


def http_get(url: str, timeout: float = 2.0) -> Optional[dict]:
    """GET a un endpoint local. Retorna dict o None."""
    try:
        import urllib.request
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def measure_sse_latency(url: str, samples: int = 5, timeout: float = 5.0) -> Optional[dict]:
    """Mide latencia del stream SSE tomando N samples."""
    try:
        import urllib.request
        req = urllib.request.Request(url)
        latencies = []
        start = time.time()

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            buf = b""
            count = 0
            while count < samples and (time.time() - start) < timeout:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n\n" in buf:
                    event, buf = buf.split(b"\n\n", 1)
                    t_recv = time.time()
                    # Parse SSE data
                    for line in event.decode(errors="replace").split("\n"):
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                ts_server = data.get("ts", 0)
                                if ts_server:
                                    latencies.append(round((t_recv - ts_server) * 1000, 1))
                                count += 1
                            except (json.JSONDecodeError, TypeError):
                                pass

        if not latencies:
            return None
        return {
            "samples": len(latencies),
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "avg_ms": round(sum(latencies) / len(latencies), 1),
        }
    except Exception as e:
        return {"error": str(e)}


def get_gpu_metrics() -> Optional[dict]:
    """Obtiene métricas GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu,utilization.memory,"
                "memory.used,memory.total,power.draw,power.limit,pstate",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        if len(parts) < 8:
            return None
        return {
            "temp_c": _safe_int(parts[0]),
            "gpu_util_pct": _safe_int(parts[1]),
            "mem_util_pct": _safe_int(parts[2]),
            "mem_used_mb": _safe_int(parts[3]),
            "mem_total_mb": _safe_int(parts[4]),
            "power_draw_w": _safe_float(parts[5]),
            "power_limit_w": _safe_float(parts[6]),
            "pstate": parts[7],
        }
    except FileNotFoundError:
        return None
    except Exception:
        return None


def get_system_metrics() -> dict:
    """Obtiene CPU/RAM/disk sin psutil (para máxima portabilidad)."""
    metrics: Dict[str, Any] = {}

    # CPU load
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            metrics["load_1m"] = float(parts[0])
            metrics["load_5m"] = float(parts[1])
            metrics["load_15m"] = float(parts[2])
    except Exception:
        pass

    # CPU percent (simple, from /proc/stat)
    try:
        result = subprocess.run(
            ["grep", "^cpu ", "/proc/stat"], capture_output=True, text=True, timeout=2
        )
        parts = result.stdout.split()
        if len(parts) >= 8:
            user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
            total = user + nice + system + idle
            if total > 0:
                metrics["cpu_pct"] = round(100 * (total - idle) / total, 1)
    except Exception:
        pass

    # RAM
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
                metrics["ram_total_mb"] = total // 1024
                metrics["ram_used_mb"] = (total - avail) // 1024
                metrics["ram_pct"] = round(100 * (total - avail) / total, 1)
    except Exception:
        pass

    # Disk
    try:
        result = subprocess.run(
            ["df", "-B1", "/opt/911fiesta"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 4:
                total = int(parts[1])
                used = int(parts[2])
                if total > 0:
                    metrics["disk_total_gb"] = round(total / (1024 ** 3), 1)
                    metrics["disk_used_gb"] = round(used / (1024 ** 3), 1)
                    metrics["disk_pct"] = round(100 * used / total, 1)
    except Exception:
        pass

    return metrics


def _safe_int(s: str) -> Optional[int]:
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _safe_float(s: str) -> Optional[float]:
    try:
        return round(float(s), 1)
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description="911 Fiesta Runtime Probe")
    parser.add_argument("--duration", type=int, default=30, help="Duración en segundos (default: 30)")
    parser.add_argument("--interval", type=float, default=1.0, help="Intervalo entre muestras (default: 1.0s)")
    parser.add_argument("--output", type=str, default=None, help="Archivo de salida JSON")
    parser.add_argument("--api-port", type=int, default=8000, help="Puerto de la API (default: 8000)")
    parser.add_argument("--core-port", type=int, default=8010, help="Puerto del CORE (default: 8010)")
    args = parser.parse_args()

    api_base = f"http://127.0.0.1:{args.api_port}"
    core_base = f"http://127.0.0.1:{args.core_port}"

    print(f"=== 911 Fiesta Runtime Probe ===")
    print(f"Fecha:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duración:  {args.duration}s (intervalo {args.interval}s)")
    print(f"API:       {api_base}")
    print(f"CORE:      {core_base}")
    print()

    # --- Paso 1: Connectivity check ---
    print("--- Connectivity Check ---")
    endpoints = {
        "api_health": f"{api_base}/health",
        "api_unified": f"{api_base}/api/v1/status/unified",
        "core_snapshot": f"{core_base}/core/snapshot",
        "vision_status": "http://127.0.0.1:5000/vision/status",
    }

    connectivity = {}
    for name, url in endpoints.items():
        t0 = time.time()
        result = http_get(url, timeout=3.0)
        latency = round((time.time() - t0) * 1000, 1)
        ok = result is not None
        connectivity[name] = {"reachable": ok, "latency_ms": latency if ok else None}
        status = "OK" if ok else "FAIL"
        print(f"  {name}: {status} ({latency}ms)")

    print()

    # --- Paso 2: SSE latency ---
    print("--- SSE Latency ---")
    sse_url = f"{api_base}/api/v1/stream"
    sse_result = measure_sse_latency(sse_url, samples=5, timeout=8.0)
    if sse_result and "error" not in sse_result:
        print(f"  SSE: {sse_result['samples']} samples, avg={sse_result['avg_ms']}ms, "
              f"min={sse_result['min_ms']}ms, max={sse_result['max_ms']}ms")
    elif sse_result:
        print(f"  SSE: Error - {sse_result.get('error', 'unknown')}")
    else:
        print(f"  SSE: No data received")
    print()

    # --- Paso 3: Periodic sampling ---
    print(f"--- Sampling ({args.duration}s) ---")
    samples: List[dict] = []
    start_time = time.time()
    sample_count = 0

    while (time.time() - start_time) < args.duration:
        t0 = time.time()
        sample: Dict[str, Any] = {
            "ts": time.time(),
            "elapsed_s": round(time.time() - start_time, 1),
        }

        # System metrics
        sample["system"] = get_system_metrics()

        # GPU
        sample["gpu"] = get_gpu_metrics()

        # CORE snapshot
        snapshot = http_get(f"{core_base}/core/snapshot", timeout=1.5)
        if snapshot:
            sample["core_online"] = True
            sample["state"] = snapshot.get("state")
            sample["energy"] = snapshot.get("energy")

            audio = snapshot.get("audio", {})
            if audio:
                sample["audio_running"] = audio.get("running", False)
                sample["audio_level"] = audio.get("level", 0)
                sample["audio_silence"] = audio.get("silence", True)

            avolites = snapshot.get("avolites", {})
            if avolites:
                sample["avolites_connected"] = avolites.get("connected", False)
                sample["avolites_latency_ms"] = avolites.get("latency_ms")

            cameras = snapshot.get("cameras", {})
            if cameras:
                cam_summary = {}
                for cam_name, cam_data in cameras.items():
                    if isinstance(cam_data, dict):
                        cam_summary[cam_name] = {
                            "online": cam_data.get("online", False),
                            "fps": cam_data.get("fps", 0),
                        }
                sample["cameras"] = cam_summary

            sys_data = snapshot.get("system", {})
            if sys_data:
                sample["snapshot_cpu"] = sys_data.get("cpu", 0)
                sample["snapshot_ram"] = sys_data.get("ram", 0)
        else:
            sample["core_online"] = False

        samples.append(sample)
        sample_count += 1

        # Progress
        elapsed = round(time.time() - start_time, 1)
        cpu = sample.get("system", {}).get("cpu_pct", "?")
        ram = sample.get("system", {}).get("ram_pct", "?")
        gpu_t = sample.get("gpu", {}).get("temp_c", "?") if sample.get("gpu") else "n/a"
        core = "ON" if sample.get("core_online") else "OFF"
        print(f"  [{elapsed:>5.1f}s] CPU={cpu}% RAM={ram}% GPU={gpu_t}°C CORE={core}")

        # Wait for next interval
        sleep_time = args.interval - (time.time() - t0)
        if sleep_time > 0:
            time.sleep(sleep_time)

    print()

    # --- Paso 4: Summary ---
    print(f"--- Summary ({sample_count} samples) ---")

    # Aggregate system metrics
    cpu_values = [s["system"].get("cpu_pct") for s in samples if s.get("system", {}).get("cpu_pct") is not None]
    ram_values = [s["system"].get("ram_pct") for s in samples if s.get("system", {}).get("ram_pct") is not None]
    gpu_temp_values = [s["gpu"]["temp_c"] for s in samples if s.get("gpu") and s["gpu"].get("temp_c") is not None]
    gpu_util_values = [s["gpu"]["gpu_util_pct"] for s in samples if s.get("gpu") and s["gpu"].get("gpu_util_pct") is not None]

    if cpu_values:
        print(f"  CPU:      avg={round(sum(cpu_values)/len(cpu_values),1)}% "
              f"max={max(cpu_values)}% min={min(cpu_values)}%")
    if ram_values:
        print(f"  RAM:      avg={round(sum(ram_values)/len(ram_values),1)}% "
              f"max={max(ram_values)}% min={min(ram_values)}%")
    if gpu_temp_values:
        print(f"  GPU temp: avg={round(sum(gpu_temp_values)/len(gpu_temp_values),1)}°C "
              f"max={max(gpu_temp_values)}°C min={min(gpu_temp_values)}°C")
    if gpu_util_values:
        print(f"  GPU util: avg={round(sum(gpu_util_values)/len(gpu_util_values),1)}% "
              f"max={max(gpu_util_values)}% min={min(gpu_util_values)}%")

    # CORE availability
    core_online = sum(1 for s in samples if s.get("core_online"))
    print(f"  CORE:     {core_online}/{sample_count} samples online "
          f"({round(100*core_online/max(sample_count,1),1)}%)")

    # Camera availability
    cam_stats: Dict[str, int] = {}
    for s in samples:
        for cam_name, cam_data in s.get("cameras", {}).items():
            if cam_name not in cam_stats:
                cam_stats[cam_name] = 0
            if cam_data.get("online"):
                cam_stats[cam_name] += 1
    for cam_name, online_count in cam_stats.items():
        print(f"  Camera {cam_name}: {online_count}/{sample_count} online "
              f"({round(100*online_count/max(sample_count,1),1)}%)")

    # Avolites
    avo_online = sum(1 for s in samples if s.get("avolites_connected"))
    avo_latencies = [s["avolites_latency_ms"] for s in samples if s.get("avolites_latency_ms") is not None]
    print(f"  Avolites: {avo_online}/{sample_count} connected", end="")
    if avo_latencies:
        print(f" (latency avg={round(sum(avo_latencies)/len(avo_latencies),1)}ms "
              f"max={max(avo_latencies)}ms)")
    else:
        print()

    # --- Output ---
    report = {
        "probe_version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "duration_s": args.duration,
        "interval_s": args.interval,
        "sample_count": sample_count,
        "connectivity": connectivity,
        "sse_latency": sse_result,
        "samples": samples,
        "summary": {
            "cpu_avg": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None,
            "cpu_max": max(cpu_values) if cpu_values else None,
            "ram_avg": round(sum(ram_values) / len(ram_values), 1) if ram_values else None,
            "ram_max": max(ram_values) if ram_values else None,
            "gpu_temp_avg": round(sum(gpu_temp_values) / len(gpu_temp_values), 1) if gpu_temp_values else None,
            "gpu_temp_max": max(gpu_temp_values) if gpu_temp_values else None,
            "gpu_util_avg": round(sum(gpu_util_values) / len(gpu_util_values), 1) if gpu_util_values else None,
            "core_online_pct": round(100 * core_online / max(sample_count, 1), 1),
            "camera_online_pct": {k: round(100 * v / max(sample_count, 1), 1) for k, v in cam_stats.items()},
            "avolites_online_pct": round(100 * avo_online / max(sample_count, 1), 1),
        },
    }

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReporte guardado: {args.output}")
    else:
        output_path = f"/tmp/911fiesta_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nReporte guardado: {output_path}")


if __name__ == "__main__":
    main()
