#!/usr/bin/env bash
# =============================================================================
# 911 Fiesta — System Snapshot Collector
# =============================================================================
#
# Captura estado real del sistema SIN modificar nada.
# Ejecutar en el server (/opt/911fiesta):
#
#   bash tools/audit/collect_system_snapshot.sh
#   bash tools/audit/collect_system_snapshot.sh > /tmp/snapshot_$(date +%Y%m%d_%H%M).txt
#
# =============================================================================
set -uo pipefail

FIESTA_HOME="${FIESTA_HOME:-/opt/911fiesta}"
VISION_CONFIG="${FIESTA_HOME}/vision_config.json"

section() { echo ""; echo "==== $1 ===="; echo ""; }
warn()    { echo "[WARN] $*"; }

# ===================================================================
section "1. FECHA / UPTIME / LOAD"
# ===================================================================
echo "Fecha:   $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Uptime:  $(uptime)"
echo "Kernel:  $(uname -r)"
echo "Hostname: $(hostname)"

# ===================================================================
section "2. TOP 10 PROCESOS POR CPU"
# ===================================================================
ps aux --sort=-%cpu | head -n 11

section "2b. TOP 10 PROCESOS POR RAM"
ps aux --sort=-%mem | head -n 11

# ===================================================================
section "3. MEMORIA"
# ===================================================================
free -h
echo ""
echo "--- Swap ---"
swapon --show 2>/dev/null || echo "(no swap activo)"

# ===================================================================
section "4. DISCO"
# ===================================================================
df -h
echo ""
echo "--- Uso de /opt/911fiesta ---"
du -sh "${FIESTA_HOME}" 2>/dev/null || echo "(directorio no accesible)"
echo ""
echo "--- Archivos de log grandes ---"
find /var/log -name "*.log" -size +50M -exec ls -lh {} \; 2>/dev/null || echo "(sin logs >50MB)"

# ===================================================================
section "5. RED"
# ===================================================================
echo "--- Interfaces ---"
ip -brief addr 2>/dev/null || ifconfig 2>/dev/null || echo "(ip/ifconfig no disponible)"
echo ""
echo "--- Rutas ---"
ip route 2>/dev/null || route -n 2>/dev/null || echo "(ip route no disponible)"
echo ""
echo "--- Puertos escuchando ---"
ss -lntup 2>/dev/null || netstat -tlnp 2>/dev/null || echo "(ss/netstat no disponible)"
echo ""
echo "--- Resumen de sockets ---"
ss -s 2>/dev/null || echo "(ss -s no disponible)"
echo ""
echo "--- Conexiones a Avolites (192.168.0.3) ---"
ss -tnp 2>/dev/null | grep "192.168.0.3" || echo "(sin conexiones activas a Avolites)"
echo ""
echo "--- Conexiones a cámaras (192.168.1.110) ---"
ss -tnp 2>/dev/null | grep "192.168.1.110" || echo "(sin conexiones activas a cámaras)"

# ===================================================================
section "6. SYSTEMD SERVICE"
# ===================================================================
if command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1; then
    systemctl status 911fiesta --no-pager -l 2>&1 || echo "(servicio no encontrado)"
    echo ""
    echo "--- Últimas 300 líneas de journal (2h) ---"
    journalctl -u 911fiesta --since "2 hours ago" --no-pager 2>/dev/null | tail -n 300 || echo "(journal no disponible)"
else
    echo "(systemd no disponible en este entorno)"
    echo ""
    echo "--- Procesos de 911fiesta ---"
    ps aux | grep -E "uvicorn|main\.py|911fiesta" | grep -v grep || echo "(no se encontraron procesos)"
fi

# ===================================================================
section "7. USB / AUDIO"
# ===================================================================
echo "--- Dispositivos USB ---"
lsusb 2>/dev/null || echo "(lsusb no disponible)"
echo ""
echo "--- ALSA playback ---"
aplay -l 2>/dev/null || echo "(aplay no disponible)"
echo ""
echo "--- ALSA capture ---"
arecord -l 2>/dev/null || echo "(arecord no disponible)"
echo ""
echo "--- /proc/asound/cards ---"
cat /proc/asound/cards 2>/dev/null || echo "(no disponible)"

# ===================================================================
section "8. GPU NVIDIA"
# ===================================================================
if command -v nvidia-smi &>/dev/null; then
    echo "--- nvidia-smi overview ---"
    nvidia-smi 2>&1
    echo ""
    echo "--- Query detallado ---"
    nvidia-smi --query-gpu=name,driver_version,temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,clocks.sm,clocks.mem,pstate --format=csv,noheader 2>&1
    echo ""
    echo "--- Throttle reasons ---"
    nvidia-smi -q -d PERFORMANCE 2>&1 | grep -A5 -i "clocks throttle\|slowdown" || echo "(sin throttle info)"
    echo ""
    echo "--- Procesos GPU ---"
    nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader 2>&1 || echo "(sin procesos GPU)"
else
    echo "[WARN] nvidia-smi no encontrado. Si hay GPU NVIDIA instalada:"
    echo "  sudo apt install nvidia-utils-535  (o versión del driver)"
fi

# ===================================================================
section "9. SENSORES DE TEMPERATURA"
# ===================================================================
if command -v sensors &>/dev/null; then
    sensors 2>&1
else
    echo "[WARN] 'sensors' no instalado. Instalar: sudo apt install lm-sensors && sudo sensors-detect"
    echo "Alternativa: cat /sys/class/thermal/thermal_zone*/temp"
    for tz in /sys/class/thermal/thermal_zone*/temp; do
        if [[ -f "$tz" ]]; then
            temp=$(cat "$tz" 2>/dev/null)
            zone=$(dirname "$tz")
            type=$(cat "${zone}/type" 2>/dev/null || echo "unknown")
            echo "  ${type}: $(( temp / 1000 ))°C"
        fi
    done
fi

# ===================================================================
section "10. CONECTIVIDAD CÁMARAS"
# ===================================================================
if [[ -f "${VISION_CONFIG}" ]]; then
    echo "Config: ${VISION_CONFIG}"
    echo ""

    # Extraer IPs de cámaras usando python o grep
    if command -v python3 &>/dev/null; then
        CAMERA_IPS=$(python3 -c "
import json
try:
    with open('${VISION_CONFIG}') as f:
        cfg = json.load(f)
    seen = set()
    for name, cam in cfg.get('cameras', {}).items():
        if not cam.get('enabled', False):
            continue
        host = cam.get('host', '')
        if host and host != '0.0.0.0' and host not in seen:
            seen.add(host)
            print(f'{name}|{host}')
except Exception as e:
    print(f'ERROR|{e}')
" 2>&1)

        while IFS='|' read -r cam_name cam_ip; do
            if [[ "${cam_name}" == "ERROR" ]]; then
                warn "No se pudo parsear vision_config: ${cam_ip}"
                continue
            fi
            echo "--- Cámara '${cam_name}' → ${cam_ip} ---"

            # Ping
            if ping -c 2 -W 2 "${cam_ip}" &>/dev/null; then
                echo "  PING: OK"
            else
                echo "  PING: FALLO"
            fi

            # TCP connect al puerto 80 (MJPEG)
            if timeout 3 bash -c "echo >/dev/tcp/${cam_ip}/80" 2>/dev/null; then
                echo "  TCP :80: OK"
            else
                echo "  TCP :80: FALLO"
            fi

            # ffprobe si existe
            if command -v ffprobe &>/dev/null; then
                echo "  ffprobe: intentando..."
                timeout 5 ffprobe -v error -print_format json -show_streams "http://${cam_ip}/axis-cgi/mjpg/video.cgi" 2>&1 | head -5
            else
                echo "  ffprobe: no instalado (apt install ffmpeg)"
            fi
            echo ""
        done <<< "${CAMERA_IPS}"
    else
        warn "python3 no disponible para parsear vision_config.json"
    fi
else
    echo "[WARN] vision_config.json no encontrado en ${VISION_CONFIG}"
fi

# ===================================================================
section "11. FILE DESCRIPTORS DEL PROCESO"
# ===================================================================
MAIN_PID=$(pgrep -f "main.py" 2>/dev/null | head -1)
if [[ -n "${MAIN_PID}" ]]; then
    echo "PID: ${MAIN_PID}"
    echo "FDs abiertos: $(ls /proc/${MAIN_PID}/fd 2>/dev/null | wc -l)"
    echo "Threads: $(ls /proc/${MAIN_PID}/task 2>/dev/null | wc -l)"
    echo ""
    echo "--- Límites ---"
    cat /proc/${MAIN_PID}/limits 2>/dev/null | grep -E "open files|processes" || echo "(no accesible)"
else
    UVICORN_PID=$(pgrep -f "uvicorn" 2>/dev/null | head -1)
    if [[ -n "${UVICORN_PID}" ]]; then
        echo "PID uvicorn: ${UVICORN_PID}"
        echo "FDs abiertos: $(ls /proc/${UVICORN_PID}/fd 2>/dev/null | wc -l)"
        echo "Threads: $(ls /proc/${UVICORN_PID}/task 2>/dev/null | wc -l)"
    else
        echo "(proceso main.py / uvicorn no encontrado)"
    fi
fi

# ===================================================================
section "12. API ENDPOINTS (si están corriendo)"
# ===================================================================
if command -v curl &>/dev/null; then
    echo "--- /health ---"
    curl -s --connect-timeout 2 http://127.0.0.1:8000/health 2>&1 || echo "(API no responde en :8000)"
    echo ""

    echo "--- /api/v1/status/unified ---"
    curl -s --connect-timeout 2 http://127.0.0.1:8000/api/v1/status/unified 2>&1 | python3 -m json.tool 2>/dev/null || echo "(no disponible)"
    echo ""

    echo "--- CORE snapshot (8010) ---"
    curl -s --connect-timeout 2 http://127.0.0.1:8010/core/snapshot 2>&1 | python3 -m json.tool 2>/dev/null || echo "(CORE no responde en :8010)"
    echo ""

    echo "--- Vision status (5000) ---"
    curl -s --connect-timeout 2 http://127.0.0.1:5000/vision/status 2>&1 | python3 -m json.tool 2>/dev/null || echo "(Vision no responde en :5000)"
else
    echo "(curl no disponible)"
fi

# ===================================================================
section "FIN DEL SNAPSHOT"
# ===================================================================
echo "Completado: $(date '+%Y-%m-%d %H:%M:%S %Z')"
