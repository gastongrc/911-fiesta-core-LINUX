# MUSIC ANALYSIS AUDIT - MIL-Lite System
## Diagnostico tecnico completo antes de reemplazo

**Fecha**: 2026-03-05
**Alcance**: Todo el sistema MIL-Lite (Music Intelligence Lite)
**Objetivo**: Explicar por que MIL-Lite no resuelve el problema musical y que debe reemplazarse

---

## 1. Resumen ejecutivo

MIL-Lite es un ponderador de scores que lee el resultado binario (`is_on()`) de los
analyzers existentes y aplica multiplicadores [0.8, 1.2] a los scores por categoria.
**No analiza audio**. No tiene memoria temporal. No entiende ritmo, tempo, ni estructura
musical.

El problema real del sistema es que los analyzers individuales fallan con:
- Kick debil o ausente
- Groove en frecuencias mid/high
- Musica latina/sincopada
- Transiciones sin transientes fuertes

MIL-Lite no puede resolver estos problemas porque opera DESPUES de que los analyzers ya
fallaron. Reponderar un score incorrecto sigue dando un resultado incorrecto.

---

## 2. Archivos del sistema MIL-Lite

### 2.1 Archivos propios

| Archivo | Funcion | Lineas |
|---------|---------|--------|
| `config/mil_lite.json` | Kill-switch JSON `{"enabled": true}` | 3 |
| `config/mil_lite_config.py` | Lectura de config (env > file > false) | 37 |
| `music_intelligence_lite/__init__.py` | Gate de import condicional | 22 |
| `music_intelligence_lite/profiler.py` | Clasifica perfil desde vote ratios | 116 |
| `music_intelligence_lite/weigher.py` | Traduce perfil a pesos [0.8, 1.2] | 82 |
| `music_intelligence_lite/logger.py` | CSV logger cada 200ms | 91 |
| `music_intelligence_lite/mil_lite.py` | Orquestador (profiler + weigher + logger) | 89 |

### 2.2 Modificaciones en archivos existentes

| Archivo | Lineas | Que hace |
|---------|--------|----------|
| `main.py:155-165` | Import condicional + flag global | Lee config, importa MILLite |
| `main.py:578-586` | Init en constructor de MainWindow | Crea instancia MILLite, setea `_mil_flag` |
| `main.py:3975-3984` | Tick en `_process_modules_limited` | Llama `mil_lite.tick()` antes de SM |
| `state_manager.py:171-174` | 3 atributos en `__init__` | `_mil_weights`, `_mil_profile`, `_mil_flag` |
| `state_manager.py:266-280` | Metodos `set_mil_weights()`, `get_mil_weights()` | Recibe pesos + profile |
| `state_manager.py:424-426` | Aplicacion de pesos en scoring | `scores[k] *= _mil_weights[k]` |
| `state_manager.py:883-885` | Exposicion en `get_status()` | Para widget UI |
| `state_manager.py:1120-1153` | Widget MUSIC INTELLIGENCE | Tarjeta en Monitor tab |
| `state_manager.py:1396-1437` | Update del widget | Lee status, muestra estado |

---

## 3. Que hace cada componente

### 3.1 Profiler (`profiler.py`)

Lee `module.card.is_on()` de cada analyzer por categoria. Calcula un vote ratio crudo
(activos/total), lo suaviza con EMA (alpha=0.15), y clasifica en 4 perfiles:

- **INTENSE**: ataque >= 0.50
- **RHYTHMIC**: golpe >= 0.40 AND ataque < 0.30
- **CALM**: bajada >= 0.40 AND golpe < 0.25
- **NEUTRAL**: default

El perfil candidato debe ser estable 1.5s antes de lockearse.

**Problema fundamental**: Lee los MISMOS datos binarios que StateManager ya consume.
Si los analyzers no detectan el golpe (porque el kick es debil), el profiler tampoco
lo detecta. No agrega informacion nueva al sistema.

### 3.2 Weigher (`weigher.py`)

Traduce el perfil a multiplicadores por categoria:

| Perfil | bajada | golpe | ataque | brake |
|--------|--------|-------|--------|-------|
| NEUTRAL | 1.00 | 1.00 | 1.00 | 1.00 |
| CALM | 1.10 | 0.92 | 0.85 | 1.05 |
| RHYTHMIC | 0.90 | 1.12 | 1.05 | 0.95 |
| INTENSE | 0.85 | 0.95 | 1.15 | 1.00 |

Pesos clampeados a [0.8, 1.2], suavizados con EMA (alpha=0.10).

**Problema**: El peso maximo es 1.20 (20% de boost). Si el score crudo es 0.10
(solo 1 de 10 analyzers detecto golpe), el score pesado es 0.12. Sigue sin cruzar
ningun umbral util. La reponderacion no puede compensar un fallo masivo de deteccion.

### 3.3 Logger (`logger.py`)

CSV logger que escribe profile, ratios, weights y estado cada 200ms.
Util para diagnostico post-sesion. Sin problemas tecnicos.

### 3.4 Orquestador (`mil_lite.py`)

Conecta profiler -> weigher -> SM.set_mil_weights() -> logger.
Tick unico en el hilo principal, ~40ms.

---

## 4. Por que NO resuelve el problema musical

### 4.1 No analiza audio

MIL-Lite **nunca toca el audio**. No recibe `block` ni `sr`. Solo lee `is_on()` de
analyzers existentes. Es un post-procesador de resultados, no un analizador.

```
Audio -> [Analyzers] -> is_on() -> [MIL-Lite lee aqui] -> score * peso -> StateManager
                                         ^
                                         |
                              NO hay informacion nueva
```

### 4.2 No tiene memoria temporal

Cada tick, MIL-Lite ve un snapshot instantaneo de votos binarios. No sabe:
- Que paso hace 2 segundos
- Si hay un patron ritmico consistente
- Si la energia esta subiendo o bajando
- En que parte de la frase musical estamos

El EMA smoothing (alpha=0.15) da ~267ms de "memoria" implicita, pero esto solo
suaviza jitter. No es memoria musical real.

### 4.3 No detecta ritmo ni estructura

La musica tiene estructura: beats, compases, frases, builds, drops. MIL-Lite no tiene
concepto de ninguno de estos. Un operador humano anticipa el drop porque escucha el
build. MIL-Lite reacciona DESPUES de que los analyzers reaccionan (o fallan en reaccionar).

### 4.4 Casos especificos de fallo

| Escenario musical | Por que falla el sistema actual | MIL-Lite ayuda? |
|-------------------|--------------------------------|-----------------|
| Kick debil / ausente | Analyzers de golpe no se activan, score bajo | NO. 1.12 * 0.10 = 0.112 |
| Groove en mid/high | Analyzers esperan energia en low freq | NO. El voto binario ya fallo |
| Musica latina sincopada | Patrones no alineados con ventanas de analisis | NO. Sin tracking de beat/fase |
| Transicion suave | No hay pico de energia, analyzers de ataque no votan | NO. 1.15 * 0.0 = 0.0 |
| Build-up gradual | Energia sube lentamente, sin evento discreto | NO. Sin memoria de tendencia |

### 4.5 El rango [0.8, 1.2] es insuficiente

Incluso si el profiler funcionara perfectamente, un ajuste de +/-20% no puede:
- Crear un voto donde no hay ninguno
- Compensar un score de 0.0 (multiplicar por 1.2 sigue siendo 0.0)
- Cambiar la tendencia cuando 8 de 10 analyzers dicen "no"

---

## 5. Problemas que introduce

### 5.1 Complejidad sin beneficio

7 archivos nuevos, modificaciones en 2 archivos criticos (`main.py`, `state_manager.py`),
un sistema de config dedicado. Todo para un efecto de +/-15-20% en scores que ya eran
correctos o incorrectos.

### 5.2 Delay adicional

- Profiler EMA alpha=0.15: ~267ms de latencia
- Stability lock: 1.5s antes de cambiar perfil
- Weigher EMA alpha=0.10: ~400ms de latencia
- **Total**: ~2.2s desde cambio musical hasta peso a regimen

Para un sistema reactivo de iluminacion en vivo, 2.2s es una eternidad.

### 5.3 Interaccion con ATAQUE override

En perfil INTENSE, el peso de ataque (1.15) baja el umbral efectivo del override de 80%
a ~69.6%. Esto puede producir overrides falsos de ATAQUE.

### 5.4 Acoplamiento con StateManager

El acceso directo a `state_manager._mil_flag` rompe encapsulamiento. Los pesos se aplican
dentro de `_calculate_scores_responsive()` en linea 424-426, creando acoplamiento que
complica futuras modificaciones del scoring.

---

## 6. Que se debe eliminar vs mantener

### 6.1 Eliminar completamente

| Archivo/Dir | Razon |
|-------------|-------|
| `music_intelligence_lite/` (todo el directorio) | Sistema completo a reemplazar |
| `config/mil_lite.json` | Config especifica de MIL-Lite |
| `config/mil_lite_config.py` | Funcion de config MIL-Lite |

### 6.2 Revertir modificaciones en archivos existentes

| Archivo | Lineas | Que revertir |
|---------|--------|-------------|
| `main.py:155-165` | Eliminar import de MIL-Lite |
| `main.py:578-586` | Eliminar init de MIL-Lite |
| `main.py:3975-3984` | Eliminar tick de MIL-Lite, reemplazar con tick de MSE |
| `state_manager.py:171-174` | Reemplazar `_mil_*` con `_mse_*` para nuevo motor |
| `state_manager.py:266-280` | Reemplazar `set_mil_weights()` con `update_music_structure()` |
| `state_manager.py:424-426` | Reemplazar multiplicacion MIL con blend MSE |
| `state_manager.py:883-885` | Reemplazar con estado MSE en `get_status()` |
| `state_manager.py:1120-1153` | Reusar widget para MUSIC STRUCTURE |
| `state_manager.py:1396-1437` | Reusar update widget para MSE |

### 6.3 Mantener

| Archivo | Razon |
|---------|-------|
| `config/__init__.py` | Package init, util para futura config |
| Concepto de logging CSV | Reusar en nuevo motor con metricas diferentes |

---

## 7. Conclusion

MIL-Lite fue un primer intento razonable: ponderar scores existentes segun contexto.
Pero el problema real no es de ponderacion, es de **deteccion**. El sistema necesita:

1. **Analisis directo de audio** (no solo leer votos binarios)
2. **Memoria temporal** (saber que paso en los ultimos 8-16 segundos)
3. **Inferencia ritmica** (tempo, beat phase, estructura de frases)
4. **Deteccion de energia multibanda** (no depender solo del kick)
5. **Anticipacion** (predecir drops, builds, transiciones)

Esto requiere un modulo nuevo que opere sobre el audio crudo: **Music Structure Engine**.
