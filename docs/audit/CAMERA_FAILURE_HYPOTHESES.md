# HIPÓTESIS DE FALLA DE CÁMARAS — 911 Fiesta

> Fecha: 2026-02-15
> Contexto: Las cámaras fallaron ayer. Este documento lista hipótesis con evidencia
> del código y señales para confirmar/descartar cada una.

---

## Configuración actual (evidencia)

```json
// vision_config.json:56-88
"cameras": {
    "haze":   { "type": "mjpeg", "host": "192.168.1.110", "fps_target": 11, "timeout_s": 5.0, "reconnect_s": 2.0 },
    "dj":     { "type": "mjpeg", "host": "192.168.1.110", "fps_target": 10, "timeout_s": 5.0, "reconnect_s": 2.0 },
    "artist": { "type": "mjpeg", "host": "192.168.1.110", "fps_target": 10, "timeout_s": 5.0, "reconnect_s": 2.0 }
}
```

**Dato crítico:** Las 3 cámaras apuntan a la MISMA IP (192.168.1.110). Si esa IP falla, las 3 caen juntas.

---

## H1: FREEZE DEL PIPELINE MJPEG (Probabilidad: ALTA)

### Mecanismo

MJPEGSource usa `requests.Session.get(url, stream=True)` y luego `response.iter_content(chunk_size=8192)`. Si la cámara deja de enviar datos pero no cierra la conexión TCP, `iter_content()` queda bloqueado indefinidamente en el socket read.

**Evidencia código:**
- `camera_source.py:424-516` — El loop de `_connect_and_stream()` depende de que `iter_content` produzca chunks.
- `camera_source.py:381-387` — El `timeout` del request es solo para el connect, no para reads intermedios: `response = self._session.get(url, stream=True, timeout=self.connect_timeout)`
- `camera_source.py:308-317` — Stall detection existe en `read()` (retorna False si frame_age > 5s), pero NO mata el thread de captura.

### Señales para confirmar

1. **En logs (journalctl):**
   ```
   grep -i "stall detected" /var/log/journal/...
   # o
   journalctl -u 911fiesta --since "yesterday" | grep -i "stall\|freeze\|timeout\|camera"
   ```

2. **En runtime (si está corriendo):**
   ```python
   # Verificar frame age de cada cámara
   curl http://127.0.0.1:5000/vision/status
   # Buscar fps=0 y/o online=false
   ```

3. **Thread dump:**
   ```bash
   # Ver si hay threads bloqueados en recv/read
   kill -USR1 $(pgrep -f main.py)  # si hay signal handler
   # o
   ps -eLf | grep main.py | wc -l  # contar threads
   ```

### Mitigación propuesta

- **P0:** Agregar `socket timeout` al request de streaming: `self._session.get(url, stream=True, timeout=(connect_timeout, read_timeout))` con `read_timeout=10s`.
- **P1:** Implementar watchdog thread que mata el capture thread si no produce frame en 2x timeout_s.

---

## H2: RECONEXIÓN FALLIDA / THREADS DUPLICADOS (Probabilidad: MEDIA-ALTA)

### Mecanismo

Cuando MJPEGSource pierde conexión, el thread intenta reconectarse con backoff exponencial. Pero CameraLoop (el coordinador) también tiene lógica de reconexión. Si ambos corren simultáneamente, pueden crear threads duplicados o dejar threads zombie.

**Evidencia código:**
- `camera_loop.py:199-232` — CameraLoop tiene su propio loop de retry con `_open_camera()` y `_close_source()`.
- `camera_source.py:351-379` — MJPEGSource tiene backoff interno en `_capture_loop()`.
- `camera_source.py:263-289` — `stop()` hace `_stop_event.set()` + `thread.join(0.5s)`. Si el join falla, el thread queda como zombie daemon.

**Escenario de falla:**
1. MJPEGSource pierde conexión → entra en backoff interno.
2. CameraLoop detecta `read() → (False, None)` → llama `_close_source()` → `source.stop()`.
3. `stop()` intenta join con timeout 0.5s. Si `iter_content()` está bloqueado, el join falla.
4. CameraLoop crea nueva source → nuevo thread. Thread viejo sigue vivo en background.
5. Repetir → acumulación de threads zombie.

### Señales para confirmar

```bash
# Contar threads del proceso
ps -eLf | grep main.py | wc -l
# Si el número crece con el tiempo → leak de threads

# Buscar en logs
journalctl -u 911fiesta --since "yesterday" | grep -i "thread\|orphan\|zombie\|didn't stop"
```

### Mitigación propuesta

- **P0:** En `MJPEGSource.stop()`, si el thread no muere en 0.5s, forzar cierre del socket subyacente (`self._session.close()`) antes del join.
- **P1:** CameraLoop debe verificar que el thread anterior murió antes de crear nueva source.
- **P1:** Agregar contador de threads activos al health.

---

## H3: MEMORY LEAK POR FRAMES (Probabilidad: MEDIA)

### Mecanismo

Cada `read()` retorna `frame.copy()` — un nuevo numpy array BGR. Si el consumer (CameraLoop → detector) procesa más lento que la fuente produce, los frames se acumulan en variables intermedias.

**Evidencia código:**
- `camera_source.py:317` — `return True, self._last_frame.copy()`
- `camera_loop.py:290-294` — `_read_frame()` retorna el copy.
- `camera_loop.py:239-260` — Frame se pasa a detector. Si detector es lento, frame vive más.
- `yolo_roi_detector.py:485-638` — YOLO inference puede tardar 50-250ms. Frame vive durante toda la inference.

**Cálculo de memoria:**
- Frame 640x480 BGR = 921,600 bytes ≈ 0.9 MB
- Frame 1920x1080 BGR = 6,220,800 bytes ≈ 6 MB
- 3 cámaras × 10 FPS × 6 MB × buffer = potencialmente 100+ MB si hay backlog

### Señales para confirmar

```bash
# Monitorear RSS del proceso
while true; do ps -o rss= -p $(pgrep -f main.py); sleep 5; done
# Si crece monotónicamente → leak

# O usar:
python3 -c "import psutil; p=psutil.Process($(pgrep -f main.py)); print(p.memory_info())"
```

### Mitigación propuesta

- **P1:** Agregar métrica de memory RSS al health endpoint.
- **P2:** Limitar frame queue size y drop agresivo (ya está en maxsize=1, pero verificar que no hay colas intermedias).

---

## H4: GPU OVERLOAD / THROTTLING (Probabilidad: MEDIA)

### Mecanismo

La GTX 1080 Ti corre YOLO V8 con fp16 para hasta 3 detectores simultáneamente (haze contraste + DJ YOLO + artist YOLO). Si la GPU se sobrecalienta o satura la VRAM, la inference se frena y las cámaras "freezan" porque el pipeline de detección bloquea el loop.

**Evidencia código:**
- `yolo_roi_detector.py:571-596` — Inference con `torch.no_grad()` y fp16.
- `yolo_roi_detector.py:614-615` — Si `infer_ms > max_infer_ms (250ms)`, activa backoff adaptativo.
- `dj_detector.py:137` / `artist_detector.py:156` — Ambos usan `process_frame_sync()` (síncrono, bloquea el loop).
- `camera_loop.py:239-260` — Detectors se ejecutan secuencialmente en el loop de la cámara.

**Escenario de falla:**
1. GPU temp > 83°C → throttling automático (NVIDIA).
2. Inference time sube de 50ms a 500ms+.
3. CameraLoop se frena — frame backlog crece.
4. Frame age > 5s → stall detection → cámara reporta offline.
5. Pero no es la cámara ni la red — es la GPU.

### Señales para confirmar

```bash
# Estado GPU en tiempo real
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory,power.draw,clocks.sm,clocks.mem --format=csv,noheader,nounits
# Si temp > 80 o utilization > 95% → throttling

# Buscar throttling
nvidia-smi -q -d PERFORMANCE
# "SW Thermal Slowdown: Active" → confirmado

# En logs de 911 Fiesta
journalctl -u 911fiesta --since "yesterday" | grep -i "backoff\|infer.*ms\|slow\|gpu"
```

### Mitigación propuesta

- **P0:** Agregar GPU temp + utilization al health endpoint.
- **P1:** Alertar si GPU temp > 80°C o utilization > 90%.
- **P2:** Reducir target_fps de YOLO si GPU está caliente (adaptive throttle ya existe pero solo por inference time).

---

## H5: TIMEOUT DE RED (Probabilidad: MEDIA)

### Mecanismo

Las 3 cámaras están en 192.168.1.110. Si el switch, el cable, o la interfaz de red del server tiene un micro-corte, las 3 streams MJPEG se cortan simultáneamente.

**Evidencia código:**
- `vision_config.json:59,70,81` — Todas IP=192.168.1.110.
- `camera_source.py:381` — Connect timeout para MJPEG.
- `camera_source.py:490-503` — Catch de `ReadTimeout` y `ConnectionError`.

**Escenario de falla:**
1. Micro-corte de red (switch, cable, NIC).
2. Las 3 conexiones MJPEG se cortan.
3. `iter_content()` lanza `ReadTimeout` o `ConnectionError`.
4. MJPEGSource entra en backoff exponencial (2s, 3s, 4.5s, 6.75s, 10s).
5. Las 3 cámaras intentan reconectar simultáneamente → posible saturación de la cámara Axis.

### Señales para confirmar

```bash
# Verificar reachability desde el server
ping -c 10 192.168.1.110

# Verificar si hubo packet loss
journalctl -u 911fiesta --since "yesterday" | grep -iE "connection.*error\|read.*timeout\|reconnect"

# Verificar estado de la interfaz
ip -s link show eth0
# Buscar: RX errors, TX errors, carrier changes
```

### Mitigación propuesta

- **P0:** Agregar ping al gateway y a cada cámara IP al health.
- **P1:** Agregar jitter de reconexión (random 0-2s) para no saturar la cámara con 3 reconnects simultáneos.
- **P2:** Considerar cámaras en IPs distintas si son dispositivos separados.

---

## H6: WATCHDOG INEXISTENTE (Probabilidad: CERTEZA — es un hecho)

### Mecanismo

No hay ningún componente que periódicamente:
1. Verifique que los threads de cámara siguen vivos.
2. Verifique que los frames son recientes.
3. Mate y reinicie un pipeline que se trabó.
4. Alerte al operador antes de que el show se vea afectado.

**Evidencia código:**
- `camera_loop.py` — No hay timer de watchdog.
- `vision_manager.py` — No hay health check periódico de camera loops.
- `core/http_snapshot.py:148-161` — Solo lee `is_running` y `current_fps` del handler, pero no hay acción correctiva.

### Lo que falta

```
Watchdog ideal:
  cada 5s:
    for cam in [haze, dj, artist]:
      if cam.thread_alive AND cam.last_frame_age < 10s:
        status = OK
      elif cam.thread_alive AND cam.last_frame_age >= 10s:
        status = STALLED → force_reconnect()
      elif NOT cam.thread_alive:
        status = DEAD → restart_camera_loop()
      log(cam, status)
      update_health(cam, status)
```

### Mitigación propuesta

- **P0:** Implementar watchdog como método periódico en VisionManager.
- **P0:** Exponer estado detallado de cada cámara en health (thread_alive, frame_age, drops, reconnects).

---

## RESUMEN DE HIPÓTESIS

| # | Hipótesis | Probabilidad | Severidad | Prioridad |
|---|-----------|-------------|-----------|-----------|
| H1 | Freeze del pipeline MJPEG (blocking read) | ALTA | ALTA | P0 |
| H2 | Threads duplicados por reconexión mal coordinada | MEDIA-ALTA | ALTA | P0 |
| H3 | Memory leak por acumulación de frames | MEDIA | MEDIA | P1 |
| H4 | GPU overload / throttling | MEDIA | ALTA | P0 (diagnostic) |
| H5 | Timeout de red (micro-corte) | MEDIA | ALTA | P1 |
| H6 | Watchdog inexistente | CERTEZA | ALTA | P0 |

### Orden de acción recomendado

1. **Primero:** Agregar GPU temp + cámara frame_age al health (confirma H4, H1).
2. **Segundo:** Implementar watchdog de cámaras (mitiga H1, H2, H6).
3. **Tercero:** Agregar socket timeout al streaming MJPEG (mitiga H1).
4. **Cuarto:** Métricas de red en health (confirma H5).
5. **Quinto:** Memory tracking (confirma H3).

---

## COMANDOS DE DIAGNÓSTICO PARA EL SERVER

```bash
# === Ejecutar estos en el server real ===

# 1. Estado general de cámaras (si API está corriendo)
curl -s http://127.0.0.1:5000/vision/status | python3 -m json.tool

# 2. GPU
nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits

# 3. Threads del proceso
ps -eLf | grep -c "main.py"

# 4. Memoria del proceso
ps -o pid,rss,vsz,pcpu,comm -p $(pgrep -f "main.py")

# 5. Red hacia cámara
ping -c 5 -W 1 192.168.1.110

# 6. Logs de cámaras
journalctl -u 911fiesta --since "24 hours ago" --no-pager | grep -iE "camera|vision|stall|reconnect|mjpeg|frame|yolo"

# 7. Conexiones TCP abiertas a cámara
ss -tnp | grep 192.168.1.110
```
