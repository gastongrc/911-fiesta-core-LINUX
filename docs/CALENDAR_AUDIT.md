# Calendar Audit — 911 Fiesta V7

**Fecha:** 2026-02-05
**Rama:** `claude/fix-calendar-sync-6ncmo`
**Alcance:** Calendar SSOT + Sync bidireccional Web↔Core↔UI (Qt)

---

## 1. SSOT — Single Source of Truth

**Path canónico:** `core/calendar/calendar.json`

| Componente | Lee de | Escribe en | Verificado |
|------------|--------|-----------|------------|
| CalendarManager | `self._config_path` → `core/calendar/calendar.json` | Mismo | OK |
| CalendarResolver | Recibe path de CalendarManager | No escribe | OK |
| http_snapshot (CORE 8010) | Usa `CalendarManager.get_schedule()` | Usa `CalendarManager.commit_from_remote()` | OK |
| UI (CalendarScheduleEditor) | Usa `CalendarManager.get_schedule()` | Usa `CalendarManager.save_schedule()` | OK |
| UI watcher | `os.path.getmtime(self._cal_json_path)` | No escribe | OK |

**Hallazgo corregido:** CalendarManager tenía fallback a `config/calendar.json` (ghost path). Eliminado. Si ese archivo existe, se emite `[CAL_BOOT] WARN legacy path exists (ignored)`.

---

## 2. Endpoints

### Web → API (puerto 8000) → CORE (puerto 8010)

| Web llama a | API router `api/routers/calendar.py` | CORE `core/http_snapshot.py` | Método CORE |
|-------------|--------------------------------------|------------------------------|-------------|
| `POST /api/v1/calendar/save` | :236 → httpx forward | :495 → `calendar_save()` | `commit_from_remote(week, "web")` |
| `GET /api/v1/calendar/week` | :220 → httpx forward | :451 → `calendar_get_week()` | `get_schedule()` |
| `GET /api/v1/calendar/status` | :54 → httpx forward | :444 → `get_snapshot()` | Snapshot completo con calendar |
| `POST /api/v1/calendar/go` | :84 → httpx forward | :479 → `calendar_go()` | `go(mode, delay)` |
| `POST /api/v1/calendar/override` | :111 → httpx forward | :482 → `calendar_override()` | `set_override(mode, dur)` |
| `POST /api/v1/calendar/override/stop` | :139 → httpx forward | :489 → `calendar_clear_override()` | `clear_override()` |
| `POST /api/v1/calendar/auto` | :162 → httpx forward | :492 → `calendar_set_auto()` | `set_auto_mode(enabled)` |

### Endpoint `/core/calendar/state`: **NO EXISTE**
- Solo documentado en `docs/audit_v6.4_plan_cierre.md`.
- Equivalente funcional: `/api/v1/calendar/status` (usa `/core/snapshot` internamente).
- **Decisión:** No implementar. No lo usa ningún código.

---

## 3. Flujo SAVE (Web → Core → UI)

```
Web Calendar.jsx:594
  │  apiPost('/calendar/save', { week: schedule.week })
  ▼
API calendar.py:249
  │  httpx.post("http://127.0.0.1:8010/core/calendar/save", json={"week": week})
  ▼
CORE http_snapshot.py:495
  │  server.calendar_save(data["week"])
  ▼
CORE http_snapshot.py:378
  │  calendar_manager.commit_from_remote(week, source="web")
  ▼
CalendarManager.commit_from_remote() [calendar_manager.py:853]
  ├── 1. Atomic write: tempfile.mkstemp + os.replace → core/calendar/calendar.json
  ├── 2. resolver.reload_schedule()
  ├── 3. _resolve_now() → determina modo actual
  ├── 4. system_bridge.apply_calendar_state() → FORZADO siempre
  └── 5. Return {ok, req_id, applied, mode, actions, reason}
  ▼
UI QTimer (500ms tick) [calendar_schedule_editor.py:1019]
  ├── os.path.getmtime() detecta cambio
  ├── _ignore_next_external es False → es cambio externo
  └── _on_external_reload() → _load_schedule() + reset dirty
```

## 4. Flujo SAVE (UI → Core → Web)

```
UI CalendarScheduleEditor._on_save() [calendar_schedule_editor.py:1140]
  ├── _ignore_next_external = True  (anti-rebote)
  ├── calendar_manager.save_schedule(schedule)  [calendar_manager.py:795]
  │     ├── Atomic write: tempfile.mkstemp + os.replace
  │     ├── resolver.reload_schedule()
  │     └── _resolve_now() → apply si modo/actions cambió
  ├── Snapshot mtime después del write
  └── Reset dirty state
  ▼
Web: próximo GET /calendar/week o SSE stream refleja el cambio
```

---

## 5. Logs esperados

### Boot
```
[CalendarManager] v6.4 Inicializado - polling cada 60s
[CAL_BOOT] app_id=140234567890 cwd=/home/user/911-fiesta-V7 cal_abs_path=/home/user/911-fiesta-V7/core/calendar/calendar.json
[CAL_UI_WATCH] watching path=/home/user/.../core/calendar/calendar.json mtime=1738789200.0
```

### Web SAVE (commit_from_remote)
```
[CAL_RECV] req_id=a1b2c3d4 source=web days=['monday', 'tuesday', ...]
[CAL_WRITE_OK] req_id=a1b2c3d4 path=/home/user/.../core/calendar/calendar.json
[CAL_RELOAD_OK] req_id=a1b2c3d4
[CAL_RESOLVE] req_id=a1b2c3d4 mode=clima_1 prev=apagado actions=['vision_dj']
[CAL_APPLY] req_id=a1b2c3d4 applied=true reason=changed bridge=true
```

### UI auto-refresh (externo)
```
[CalendarUI] [CAL_UI_WATCH] changed mtime=1738789201.5
[CalendarUI] [CAL_UI_REFRESH] source=external blocks=14 dirty_reset=true
```

### UI save local (ignorado por watcher)
```
[CalendarUI] [CAL_UI_WATCH] changed mtime=1738789202.0 (ignored: local save)
```

### Override activo (resolve skipped)
```
[CAL_RESOLVE] skip reason=override_active mode=boliche_desarrollo
```

---

## 6. Hallazgos de auditoría

### Corregidos

| # | Hallazgo | Riesgo | Fix | Archivo |
|---|----------|--------|-----|---------|
| 1 | CalendarManager buscaba `config/calendar.json` primero (ghost path) | Si alguien crea ese archivo, SSOT se bifurca silenciosamente | Eliminado fallback; siempre usa `core/calendar/calendar.json`; warn si legacy existe | `core/calendar/calendar_manager.py:147-162` |
| 2 | `save_schedule()` (UI save) usaba escritura directa (no atómica) | Corte de corriente durante write = JSON corrupto | Mismo patrón `.tmp` + `os.replace` que `commit_from_remote` | `core/calendar/calendar_manager.py:807-824` |
| 3 | UI watcher no seteaba path si archivo no existía al conectar | Si calendar.json se crea después de boot, watcher nunca arranca | Cambió `os.path.isfile(path)` por `if path:` — timer maneja OSError | `ui/calendar_schedule_editor.py:957-958` |

### Observados (NO corregidos — riesgo bajo, no aplican a configs actuales)

| # | Hallazgo | Riesgo | Decisión |
|---|----------|--------|----------|
| 4 | Overlap detection no maneja midnight-crossing blocks | False positive en bloques como 22:00→05:00 | No corregir: configs actuales no tienen midnight crossing en overlap. Warning es informativo, no bloquea save. |
| 5 | Bloques no se ordenan por hora dentro de un día | Si hay overlaps, first-match-wins es no-determinístico | No corregir: `_is_time_in_range()` es unambiguo para configs sin overlap. |
| 6 | `/core/calendar/state` da 404 | Confusión si se prueba manualmente | No implementar: ningún código lo llama. Usar `/api/v1/calendar/status` en su lugar. |

---

## 7. Schema del JSON

```json
{
  "week": {
    "monday": [
      {
        "from": "20:00",
        "to": "22:00",
        "mode": "clima_1",
        "actions": ["vision_dj"]
      }
    ],
    "tuesday": [],
    ...
  }
}
```

- `actions` es opcional. Si falta o es `[]`, se usan solo las acciones base del modo.
- Modos canónicos: `clima_1`, `clima_2`, `clima_3`, `clima_4`, `boliche_inicio`, `boliche_desarrollo`, `boliche_fin`, `apagado`.
- Acciones válidas: `vision_haze`, `vision_dj`, `vision_artista`.
- Exclusión mutua: `vision_dj` y `vision_artista` no pueden coexistir.

---

## 8. Test Plan (6 pruebas manuales)

### Test 1: Web Save → UI refleja en <1s
1. Abrir UI (Qt) con CalendarTab visible
2. Desde browser, editar schedule en Calendar page
3. Click "Guardar" en web
4. **Verificar:** UI Qt muestra los nuevos bloques en <1s
5. **Verificar:** No dice "Cambios sin guardar"
6. **Log esperado:** `[CAL_UI_WATCH] changed mtime=...` + `[CAL_UI_REFRESH] source=external`

### Test 2: UI Save → Web refleja en <1s
1. En UI Qt, editar un bloque (cambiar horario o modo)
2. Click "Guardar Cambios"
3. En browser, recargar Calendar page (o esperar SSE)
4. **Verificar:** Web muestra los cambios guardados desde UI
5. **Log esperado:** `[CALENDAR] save ok` + `[CAL_UI_WATCH] changed mtime=... (ignored: local save)`

### Test 3: Reinicio completo
1. Cerrar UI, detener CORE, detener API
2. Iniciar CORE, iniciar API, abrir UI
3. **Verificar:** Schedule cargado correctamente en los tres componentes
4. **Verificar:** `[CAL_BOOT] app_id=... cal_abs_path=.../core/calendar/calendar.json`

### Test 4: Save repetido (idempotente)
1. En web, guardar el mismo schedule 3 veces sin cambiar nada
2. **Verificar:** No hay crash, no hay loop
3. **Log esperado:** 3x `[CAL_APPLY] ... reason=forced_reapply` (re-aplica pero no cambia nada)
4. **Verificar:** UI no parpadea ni resetea innecesariamente (mtime cambia, refresh es OK)

### Test 5: Cambios rápidos (3 saves en <2s)
1. En web, hacer 3 saves rápidos (cambiar modo diferente cada vez)
2. **Verificar:** UI muestra el ÚLTIMO estado guardado
3. **Verificar:** No quedan "Cambios sin guardar" en UI
4. **Verificar:** `core/calendar/calendar.json` tiene el último save

### Test 6: Archivo borrado y recuperado
1. Renombrar `core/calendar/calendar.json` → `calendar.json.bak`
2. **Verificar:** UI no crashea. Timer sigue corriendo (OSError ignorado).
3. **Verificar:** Logs no spamean (solo un getmtime call cada 500ms, OSError es silencioso)
4. Restaurar: `mv calendar.json.bak calendar.json`
5. **Verificar:** UI detecta el archivo restaurado y carga schedule
6. **Log esperado:** `[CAL_UI_WATCH] changed mtime=...` + `[CAL_UI_REFRESH]`

---

## 9. Troubleshooting

### "Web guardó pero UI no cambió"
1. Verificar que CORE esté corriendo en puerto 8010
2. Buscar `[CAL_WRITE_OK]` en logs de CORE → confirma que el write fue OK
3. Buscar `[CAL_UI_WATCH]` en logs de UI → confirma que el watcher detectó el cambio
4. Si no aparece `[CAL_UI_WATCH]`: verificar que `[CAL_UI_WATCH] watching path=...` apareció en boot

### "UI dice Cambios sin guardar pero no edité nada"
1. Un save externo (web) debería haber limpiado este estado
2. Si persiste: verificar que `_on_external_reload()` ejecutó y `_has_changes` se puso en False
3. Buscar `[CAL_UI_REFRESH] source=external ... dirty_reset=true` en logs

### "Save desde web devuelve ok pero modo no cambió en runtime"
1. Buscar `[CAL_APPLY] req_id=... applied=true/false reason=...`
2. Si `reason=no_bridge`: CalendarManager no tiene SystemBridge conectado. Verificar boot en main.py
3. Si `reason=override_active`: hay un override activo que bloquea resolve. Limpiar override primero.
4. Si `reason=forced_reapply`: el modo no cambió, pero se re-aplicó (correcto).

---

## 10. curl de verificación

```bash
# SAVE schedule
curl -s -X POST http://127.0.0.1:8010/core/calendar/save \
  -H "Content-Type: application/json" \
  -d '{"week":{"monday":[{"from":"20:00","to":"22:00","mode":"clima_1"}]}}' | python -m json.tool

# GET week
curl -s http://127.0.0.1:8010/core/calendar/week | python -m json.tool

# GET status (via snapshot)
curl -s http://127.0.0.1:8010/core/snapshot | python -m json.tool

# Via API (puerto 8000)
curl -s http://127.0.0.1:8000/api/v1/calendar/status | python -m json.tool
curl -s http://127.0.0.1:8000/api/v1/calendar/week | python -m json.tool
```
