# 🚀 911 Fiesta – Sistema Inteligente de Control de Shows

**Versión:** v6.3 (async + force_guard_kill + cache_sync)  
**Arquitectura:** Modular, escalable y lista para ejecución headless  
**Autor:** Gastón Claver — *Todo Música / 911 Fiesta*  
**Estado general:** Sistema fluido, sin delays críticos. Auditoría en curso.

---

## 🧱 ESTRUCTURA DE SEGUIMIENTO (FASES + OBJETIVOS)

### 🩵 FASE 1 – AUDITORÍA Y SANIDAD GENERAL
**Objetivo:** asegurar que el núcleo funcione limpio, sin residuos de parches.

**Tareas**
- [ ] Ejecutar *Full System Health Check* en Claude  
- [ ] Verificar integridad de analizadores (`bajada`, `golpe`, `ataque`, `brake`)  
- [ ] Validar consistencia de `state_manager` y flujo de estados  
- [ ] Confirmar que `cue_engine` no repita transiciones  
- [ ] Confirmar que logs `[ENGINE]` / `[DRV]` estén balanceados  

**Resultado esperado:**  
✅ Sistema sano, sin errores, sin loops, sin leaks.

---

### 💠 FASE 2 – API + BACKEND
**Objetivo:** exponer el motor 911 como servicio HTTP.

**Tareas**
- [ ] Implementar API con **FastAPI** (`localhost:9111/api/v1/...`)  
- [ ] Endpoints: `/status`, `/config`, `/analyzers`, `/cues`, `/network`  
- [ ] Integrar control de licencias (`license_manager`)  
- [ ] Exponer métricas (`/metrics`) para Prometheus o panel externo  

**Resultado esperado:**  
✅ Motor accesible y monitoreable vía red.

---

### 💠 FASE 3 – FRONTEND WEB
**Objetivo:** construir panel de control visual profesional.

**Tareas**
- [ ] Crear WebApp con **React + Tailwind + ShadCN/UI + Recharts**  
- [ ] Dashboard principal: estado, cues activos, red, backup, alertas  
- [ ] Pestañas:  
  - Estado general  
  - Configuración de red  
  - Analizadores / calibración  
  - Backup & Licencia  
  - Calendario / programación  
- [ ] Integrar comunicación API (`fetch` o `WebSocket`)  

**Resultado esperado:**  
✅ Control total desde navegador, sin GUI local.

---

### 💠 FASE 4 – ALERTAS Y MONITOREO DE AUDIO
**Objetivo:** detección preventiva de problemas de línea.

**Tareas**
- [ ] Crear módulo `audio_monitor.py` (clipping, ausencia, ruido)  
- [ ] Mostrar alertas visuales en panel y logs  
- [ ] Calibración automática de umbrales  

**Resultado esperado:**  
✅ Notificación inmediata ante fallas de audio.

---

### 💠 FASE 5 – BACKUP Y RESTORE AUTOMÁTICO
**Objetivo:** nunca perder configuraciones.

**Tareas**
- [ ] Crear sistema de backup comprimido (`/config/backup/*.zip`)  
- [ ] Implementar restauración instantánea (`--restore-backup`)  
- [ ] Cifrado AES + hash de integridad  

**Resultado esperado:**  
✅ Restauración completa en segundos.

---

### 💠 FASE 6 – CÁMARAS INTELIGENTES
**Objetivo:** automatizar el show según entorno visual.

**Tareas**
- [ ] `camera_haze.py` → control de humo (densidad + PID)  
- [ ] `camera_people.py` → detección de presencia (DJ / bailarinas)  
- [ ] Asociar detecciones a cues específicos  

**Resultado esperado:**  
✅ Show dinámico adaptado a la escena.

---

### 💠 FASE 7 – BPM MASTER / SYNC
**Objetivo:** sincronizar luces y efectos con el tempo real.

**Tareas**
- [ ] `bpm_detector.py` con FFT + onset tracking  
- [ ] Broadcast vía OSC / HTTP  
- [ ] PLL con “elastic smoothing”  

**Resultado esperado:**  
✅ Sincronía total con BPM del track.

---

### 💠 FASE 8 – LICENCIA Y ANTICOPIA
**Objetivo:** blindar el sistema a nivel hardware.

**Tareas**
- [ ] `license_manager.py`: generar hash único (MAC + UUID + salt)  
- [ ] Cifrar con AES-GCM + firma ECDSA  
- [ ] Bloquear si se clona disco o cambia hardware  
- [ ] CLI de activación (`--install-license`)  

**Resultado esperado:**  
✅ Sistema atado a motherboard. Copia imposible.

---

### 💠 FASE 9 – ACTUALIZACIÓN SEGURA
**Objetivo:** mantener versiones actualizadas de forma controlada.

**Tareas**
- [ ] `updater.py`: actualización online HTTPS o USB  
- [ ] Validación de firma digital antes de aplicar  
- [ ] Rollback automático si falla  

**Resultado esperado:**  
✅ Actualización segura y verificada.

---

### 💠 FASE 10 – LINUX HEADLESS FINAL
**Objetivo:** operación industrial 24/7 sin GUI local.

**Tareas**
- [ ] Crear servicio `911fiesta.service` (systemd)  
- [ ] Log JSON estructurado (journalctl)  
- [ ] Watchdog + control remoto  

**Resultado esperado:**  
✅ Sistema autónomo, estable y sin interfaz local.

---

## 🔒 PRIORIDADES ACTUALES

| Prioridad | Fase | Estado | Responsable |
|------------|------|--------|-------------|
| 🔵 Alta | Fase 1 – Auditoría | 🟡 En proceso | Claude |
| 🟣 Media | Fase 2 – API Backend | 🔴 Pendiente | Gas |
| 🟢 Media | Fase 3 – WebApp | 🔴 Pendiente | Gas + IA Frontend |
| 🔵 Alta | Fase 8 – Licencia | 🔴 Planificada | Gas |
| 🟢 Media | Fase 9 – Updater | 🔴 Planificada | Gas |
| ⚪ Baja | Fase 10 – Linux Headless | 🔴 Final futura | Gas |

---

## 🧭 FLUJO DE TRABAJO IA

| Rol | Herramienta | Función |
|-----|--------------|---------|
| **Director técnico** | ChatGPT | Planificación y documentación |
| **Ingeniero de código** | Claude | Implementación y refactorización |
| **Especialista analítico** | DeepSeek | Optimización BPM y rendimiento |
| **Auditor técnico** | Claude | Verificación de integridad |
| **Frontend Designer** | ChatGPT / IA Web | Desarrollo UI y panel web |

---

## 📊 ESTADO DEL PROYECTO
**Versión estable:** `v6.3`  
**En progreso:** Auditoría completa de analizadores.  
**Próximo paso:** Confirmar sistema sano → iniciar Fase 2 (API).

---

## 🔗 Seguimiento y control
Cada entrega o corrección de Claude se registra con:
