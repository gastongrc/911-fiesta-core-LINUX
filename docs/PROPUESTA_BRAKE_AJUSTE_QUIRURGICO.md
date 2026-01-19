# PROPUESTA: AJUSTE QUIRÚRGICO DE BRAKE (OPCIÓN A)

**Fecha:** 2025-12-16
**Branch:** claude/musical-analysis-audit-6WtQD
**Base:** Análisis forense en `AUDIT_BRAKE_FORENSIC.md`

---

## DIAGNÓSTICO RESUMIDO

| Problema | Causa en código | Latencia agregada |
|----------|-----------------|-------------------|
| BRAKE diseñado para silencio | `ok_time` requiere 1.2s sin onsets | **1200ms** |
| Confirmación bloquea entrada | `confirm_s` = 1.0s para acumular | **1000ms** |
| Histéresis excesiva | `hold_on` = 550ms consecutivos | **550ms** |
| **TOTAL estructural** | | **~2750ms** |

**Definición musical:** BRAKE = pérdida de golpe CON contenido (voz)
**Definición en código:** BRAKE = silencio prolongado sin transitorios
**→ Desalineación fundamental**

---

## AJUSTE 1: DESACOPLAR `ok_time` DEL ACUMULADOR

### Ubicación
**Archivo:** `analyzers/brake.py`
**Líneas:** 227-231

### Código Actual
```python
# L227-231
all_ok = ok_drop and ok_quiet and ok_flux and ok_time
if all_ok or v_raw > 0.7:
    self._ok_time = min(10.0, self._ok_time + dt)
else:
    self._ok_time = max(0.0, self._ok_time - 2*dt)
```

### Problema
- `all_ok` requiere `ok_time` = (since_onset >= 1.2s)
- La voz tiene consonantes → `_detect_onsets()` dispara → `since_onset` se resetea
- `ok_time` casi nunca es True cuando hay voz presente
- El bypass `v_raw > 0.7` depende de múltiples condiciones alineadas
- Resultado: el acumulador no progresa, BRAKE no entra

### Cambio Propuesto
```python
# L227-231 - MODIFICADO
# Condición de energía fuerte = BRAKE musical (acepta voz)
energy_brake = ok_drop and ok_quiet
all_ok = energy_brake and ok_flux and ok_time
if all_ok or energy_brake or v_raw > 0.7:
    self._ok_time = min(10.0, self._ok_time + dt)
else:
    self._ok_time = max(0.0, self._ok_time - 2*dt)
```

### Latencia Eliminada
- **~1200ms** (ya no espera void_s para acumular)
- El acumulador empieza a trabajar apenas hay caída de energía

### Por Qué NO Rompe Conservadurismo
1. **ok_drop** requiere 12dB de caída (medido, no arbitrario)
2. **ok_quiet** requiere RMS < 35% del baseline de 10 segundos
3. Ambas condiciones JUNTAS confirman caída real de energía musical
4. El acumulador aún requiere tiempo (`confirm_s`) antes de subir score
5. La histéresis (`hold_on`) sigue activa como última línea de defensa
6. `ok_time` sigue contribuyendo al score final vía `v_time` (L221)

### Reversibilidad
- Cambio de 1 línea (agregar `or energy_brake`)
- Revertir = quitar 3 palabras
- Sin efectos secundarios en otros módulos

---

## AJUSTE 2: REDUCIR `hold_on` PARA ENTRADA RÁPIDA

### Ubicación
**Archivo:** `analyzers/brake.py`
**Línea:** 50

### Código Actual
```python
# L50
self.card.add_slider("hold", "Hold ON (ms)", 200.0, 1200.0, 550.0)
```

### Problema
- 550ms de hold significa que el score debe mantenerse >= 0.60 por 550ms consecutivos
- Cualquier fluctuación (onset de voz, ruido) puede resetear `_t_on` a 0
- Esto añade latencia Y causa intermitencia

### Cambio Propuesto
```python
# L50 - MODIFICADO
self.card.add_slider("hold", "Hold ON (ms)", 200.0, 1200.0, 180.0)
```

### Latencia Eliminada
- **370ms** (550 - 180 = 370ms menos de espera)

### Por Qué NO Rompe Conservadurismo
1. 180ms es suficiente para filtrar ruido de 1-2 frames (~40ms cada uno)
2. El score ya pasó por:
   - Detección de energía (ok_drop + ok_quiet)
   - Acumulador de confirmación (_ok_time)
   - Suavizado EMA (smooth)
   - Umbral de histéresis (thr_on = 0.60)
3. El hold es la ÚLTIMA línea de defensa, no la principal
4. 180ms > tiempo de reacción humana (~150ms)

### Reversibilidad
- Cambio de 1 número (550.0 → 180.0)
- Ajustable via UI slider sin recompilar

---

## COMPARACIÓN DE AJUSTES

| Aspecto | Ajuste 1 | Ajuste 2 |
|---------|----------|----------|
| **Latencia eliminada** | ~1200ms | ~370ms |
| **Ataca causa raíz** | ✅ Sí (ok_time bloqueante) | ❌ No (síntoma) |
| **Elimina intermitencia** | ✅ Sí (voz ya no bloquea) | ⚠️ Parcial |
| **Líneas modificadas** | 1 | 1 |
| **Riesgo** | Bajo | Muy bajo |
| **Reversibilidad** | Inmediata | Inmediata (slider) |

---

## ✅ RECOMENDACIÓN: AJUSTE 1

### Por Qué Ajuste 1

1. **Ataca la causa raíz:**
   El análisis forense identificó que `ok_time` (void_s = 1.2s sin onsets) es el bloqueante principal. La voz tiene "onsets" (consonantes) que no son golpes musicales pero el detector los cuenta igual. Ajuste 1 desacopla esto permitiendo que energía baja = BRAKE, con o sin voz.

2. **Alinea código con definición musical:**
   - BRAKE musical = pérdida de golpe, energía cae, voz presente
   - Ajuste 1 permite esto: `energy_brake = ok_drop and ok_quiet`
   - No requiere silencio absoluto

3. **Mayor impacto:**
   - 1200ms vs 370ms de reducción
   - Latencia resultante: ~1550ms (vs ~2380ms con solo Ajuste 2)

4. **Elimina la intermitencia:**
   - Actualmente: voz resetea ok_time → acumulador no progresa → BRAKE no entra
   - Con Ajuste 1: voz no afecta acumulación si energía cayó

5. **Conservadurismo mantenido:**
   - ok_drop (12dB) es un umbral alto
   - ok_quiet (35% baseline) confirma que no es fluctuación
   - El acumulador confirm_s sigue activo
   - El hold_on sigue activo
   - Solo removemos la redundancia de ok_time en el acumulador

### Latencia Resultante Estimada

| Componente | Antes | Después |
|------------|-------|---------|
| void_s espera | 1200ms | **0ms** (desacoplado) |
| confirm_s acumulación | 1000ms | 1000ms |
| hold_on | 550ms | 550ms |
| smooth + respuesta | ~200ms | ~200ms |
| **TOTAL** | ~2950ms | **~1750ms** |

Con ambos ajustes combinados:
| Componente | Latencia |
|------------|----------|
| confirm_s | 1000ms |
| hold_on (reducido) | 180ms |
| smooth + respuesta | ~200ms |
| **TOTAL** | **~1380ms** |

### Si Se Quiere <500ms

Para lograr <500ms, además de Ajuste 1, se necesitaría:
- Reducir `confirm_s` de 1.0s a ~0.2s (slider L48)
- Reducir `hold_on` a 100-150ms

Esto daría: 200ms + 150ms + 150ms ≈ **500ms**

Pero esto excede "ajuste quirúrgico" y entra en "retuneo de parámetros".

---

## IMPLEMENTACIÓN PROPUESTA

### Paso 1: Aplicar Ajuste 1 (recomendado)

```python
# analyzers/brake.py L227-231
# ANTES:
all_ok = ok_drop and ok_quiet and ok_flux and ok_time
if all_ok or v_raw > 0.7:
    self._ok_time = min(10.0, self._ok_time + dt)
else:
    self._ok_time = max(0.0, self._ok_time - 2*dt)

# DESPUÉS:
energy_brake = ok_drop and ok_quiet
all_ok = energy_brake and ok_flux and ok_time
if all_ok or energy_brake or v_raw > 0.7:
    self._ok_time = min(10.0, self._ok_time + dt)
else:
    self._ok_time = max(0.0, self._ok_time - 2*dt)
```

### Paso 2 (opcional): Aplicar Ajuste 2

```python
# analyzers/brake.py L50
# ANTES:
self.card.add_slider("hold", "Hold ON (ms)", 200.0, 1200.0, 550.0)

# DESPUÉS:
self.card.add_slider("hold", "Hold ON (ms)", 200.0, 1200.0, 180.0)
```

### Verificación

1. Probar con pista conocida que tiene BRAKEs
2. Verificar que BRAKE entra en <2s después del corte musical
3. Verificar que no hay falsos positivos en secciones energéticas
4. El flag status mostrará `DQ--` (drop+quiet sin time) cuando entre por energy_brake

---

## RESUMEN EJECUTIVO

| Métrica | Estado Actual | Con Ajuste 1 | Con Ajuste 1+2 |
|---------|---------------|--------------|----------------|
| Latencia típica | ~3100ms | ~1750ms | ~1380ms |
| Intermitencia | Alta | Baja | Baja |
| Falsos positivos | Muy raros | Raros | Raros |
| Líneas cambiadas | - | 2 | 3 |
| Reversibilidad | - | Inmediata | Inmediata |

**Recomendación final:** Implementar Ajuste 1. Si la latencia de ~1.7s sigue siendo inaceptable, agregar Ajuste 2. Si se necesita <500ms, ajustar `confirm_s` via slider (sin cambio de código).

---

*Propuesta quirúrgica — Mínimo cambio, máximo impacto*
