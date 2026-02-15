# RUNBOOK — Auditoría Runtime 911 Fiesta

> Para: Tom (operador server)
> Fecha: 2026-02-15
> Versión: 1.0

---

## Prerequisitos

- Acceso SSH al server Linux (`/opt/911fiesta`)
- El servicio `911fiesta` puede estar corriendo o parado
- Los scripts NO modifican nada — solo lectura

---

## 1. SNAPSHOT COMPLETO DEL SISTEMA

Captura estado de hardware, red, GPU, audio, cámaras, procesos, logs.

```bash
cd /opt/911fiesta

# Ejecutar y guardar output
bash tools/audit/collect_system_snapshot.sh > /tmp/snapshot_$(date +%Y%m%d_%H%M).txt 2>&1

# Ver resultado
cat /tmp/snapshot_*.txt
```

**Qué captura:**
- Fecha, uptime, kernel
- Top 10 procesos por CPU y RAM
- Memoria (free -h) + swap
- Disco (df -h) + tamaño de /opt/911fiesta
- Red: interfaces, rutas, puertos, sockets a Avolites y cámaras
- systemd service status + últimas 300 líneas de journal
- USB devices + ALSA audio devices
- **GPU NVIDIA**: temp, utilization, memory, power, throttling, procesos GPU
- Sensores de temperatura
- Conectividad a cámaras (ping + TCP + ffprobe)
- File descriptors y threads del proceso
- Endpoints API (health, unified, CORE snapshot, vision)

---

## 2. PROBE DE RUNTIME (30 segundos de métricas)

Conecta a los endpoints locales y captura samples cada 1 segundo.

```bash
cd /opt/911fiesta

# Probe estándar (30s)
python3 tools/audit/collect_runtime_probe.py

# Probe extendido (60s, cada 2s)
python3 tools/audit/collect_runtime_probe.py --duration 60 --interval 2

# Guardar resultado
python3 tools/audit/collect_runtime_probe.py --output /tmp/probe_result.json
```

**Qué mide:**
- Connectivity check a 4 endpoints (API, CORE, Vision)
- Latencia SSE (5 samples)
- Cada segundo: CPU%, RAM%, GPU temp/util, estado CORE, cámaras online/fps, Avolites conectado/latencia
- Resumen: promedios, máximos, % de disponibilidad

**Output:** JSON con todos los samples + summary. Se guarda en `/tmp/911fiesta_probe_*.json`

---

## 3. ENDPOINT DE HEALTH COMPLETO (nuevo)

Si la API está corriendo en puerto 8000:

```bash
# Health completo del sistema
curl -s http://127.0.0.1:8000/api/v1/status/system | python3 -m json.tool

# Solo los últimos errores
curl -s http://127.0.0.1:8000/api/v1/status/system/errors | python3 -m json.tool
```

**Respuesta de `/api/v1/status/system`:**

```json
{
  "ts": 1739612345,
  "cpu": { "percent": 23.5, "load_avg": [1.2, 0.8, 0.6], "cores": 8 },
  "ram": { "total_mb": 32768, "used_mb": 8192, "percent": 25.0 },
  "disk": { "path": "/opt/911fiesta", "total_gb": 500.0, "used_gb": 120.0, "percent": 24.0 },
  "gpu": {
    "name": "NVIDIA GeForce GTX 1080 Ti",
    "driver": "535.183.01",
    "temp_c": 62,
    "gpu_util_pct": 45,
    "mem_util_pct": 30,
    "mem_used_mb": 3200,
    "mem_total_mb": 11264,
    "power_draw_w": 120.5,
    "power_limit_w": 250.0,
    "pstate": "P2"
  },
  "network": {
    "interfaces": [
      { "name": "eth0", "state": "UP", "ips": ["192.168.0.100/24"] }
    ],
    "sockets_listen": ["..."]
  },
  "audio_devices": ["card 1: PS22 [Maono PS22], device 0: USB Audio [USB Audio]"],
  "cameras": {
    "configured": 3,
    "cameras": {
      "haze": { "online": true, "fps": 10, "ip": "192.168.1.110", "status": "ok" },
      "dj": { "online": true, "fps": 9, "ip": "192.168.1.110", "status": "ok" },
      "artist": { "online": false, "fps": 0, "ip": "192.168.1.110", "status": "down" }
    }
  },
  "avolites": {
    "connected": true,
    "host": "192.168.0.3",
    "port": 4430,
    "latency_ms": 12,
    "last_error": null
  },
  "process": {
    "pid": 12345,
    "threads": 18,
    "fds": 45,
    "rss_mb": 512.3,
    "cpu_pct": 15.2,
    "uptime_s": 86400
  },
  "last_errors": [],
  "collection_ms": 45.2
}
```

Si `gpu` es `null` → nvidia-smi no está instalado o no hay GPU.

---

## 4. DIAGNÓSTICO RÁPIDO (COPYPASTE)

### Ver todo de un vistazo

```bash
# 1. ¿Está corriendo?
systemctl status 911fiesta --no-pager

# 2. ¿GPU está bien?
nvidia-smi

# 3. ¿Hay errores recientes?
journalctl -u 911fiesta --since "1 hour ago" --no-pager | grep -iE "error|fail|exception|traceback" | tail -20

# 4. ¿Cámaras conectadas?
curl -s http://127.0.0.1:8000/api/v1/status/system | python3 -c "
import json, sys
d = json.load(sys.stdin)
for cam, info in d.get('cameras', {}).get('cameras', {}).items():
    status = 'OK' if info.get('online') else 'DOWN'
    print(f'  {cam}: {status} ({info.get(\"fps\", 0)} fps)')
"

# 5. ¿Avolites conectado?
curl -s http://127.0.0.1:8000/api/v1/status/system | python3 -c "
import json, sys
d = json.load(sys.stdin)
avo = d.get('avolites', {})
print(f'  Connected: {avo.get(\"connected\")}')
print(f'  Host: {avo.get(\"host\")}:{avo.get(\"port\")}')
print(f'  Latency: {avo.get(\"latency_ms\")}ms')
"

# 6. ¿Audio device presente?
arecord -l | grep -i "maono\|ps22\|usb"
```

### Si las cámaras fallaron

```bash
# 1. ¿La cámara responde?
ping -c 3 -W 1 192.168.1.110

# 2. ¿TCP :80 abierto?
timeout 3 bash -c "echo >/dev/tcp/192.168.1.110/80" && echo OK || echo FALLO

# 3. ¿Cuántos threads tiene el proceso?
ps -eLf | grep -c "main.py"
# Si es >> 20 → posible leak de threads

# 4. ¿Memoria del proceso?
ps -o pid,rss,vsz,%cpu -p $(pgrep -f "main.py")
# Si RSS crece cada vez → memory leak

# 5. ¿GPU throttling?
nvidia-smi -q -d PERFORMANCE | grep -i "slowdown"
# "SW Thermal Slowdown : Active" → GPU está frenando

# 6. ¿Logs de cámaras?
journalctl -u 911fiesta --since "2 hours ago" --no-pager | grep -iE "camera|vision|stall|reconnect|mjpeg|frame|yolo" | tail -50

# 7. ¿Conexiones TCP a la cámara?
ss -tnp | grep 192.168.1.110
# Si hay muchas → reconexiones acumuladas
```

### Si Avolites no conecta

```bash
# 1. ¿El server ve la consola?
ping -c 3 -W 1 192.168.0.3

# 2. ¿Puerto 4430 abierto?
timeout 3 bash -c "echo >/dev/tcp/192.168.0.3/4430" && echo OK || echo FALLO

# 3. ¿Titan responde?
curl -s --connect-timeout 3 http://192.168.0.3:4430/titan/get/System/SoftwareVersion

# 4. ¿Errores de Avolites?
journalctl -u 911fiesta --since "1 hour ago" --no-pager | grep -iE "avolites|titan|circuit.breaker|fire|kill" | tail -30
```

### Si no hay audio

```bash
# 1. ¿USB conectado?
lsusb | grep -i "audio\|maono"

# 2. ¿ALSA lo ve?
arecord -l

# 3. ¿El usuario está en grupo audio?
id fiesta911 | grep audio

# 4. ¿PortAudio funciona?
/opt/911fiesta/.venv/bin/python3 -c "import sounddevice; print(sounddevice.query_devices())"
```

---

## 5. CHECKLIST POST-INCIDENTE

Después de una falla, ejecutar en este orden:

```
[ ] bash tools/audit/collect_system_snapshot.sh > /tmp/postmortem_$(date +%Y%m%d_%H%M).txt
[ ] python3 tools/audit/collect_runtime_probe.py --duration 60 --output /tmp/postmortem_probe.json
[ ] journalctl -u 911fiesta --since "4 hours ago" --no-pager > /tmp/postmortem_journal.txt
[ ] nvidia-smi -q > /tmp/postmortem_gpu.txt
[ ] ss -tnp > /tmp/postmortem_sockets.txt
[ ] ps -eLf | grep 911 > /tmp/postmortem_threads.txt
```

Guardar todos los archivos `/tmp/postmortem_*` para análisis.

---

## 6. NOTA IMPORTANTE

Estos scripts son **read-only**. No reinician servicios, no matan procesos, no modifican configuración. Es seguro ejecutarlos en cualquier momento, incluso durante un show en vivo.
