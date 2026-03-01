# state_manager.py - V13 FAST BASELINE + Override ATAQUE 80% + CALIBRACIÓN DE PRECISIÓN + FEED STATE/ENERGY
# ========================================================================================================
# V13 CHANGES:
# - FAST BASELINE: Default values optimized for low-latency state changes
# - Lag instrumentation (t_score, t_candidate, t_commit)
# - Optional PRESETS for tuning (STABLE for slower/safer, FAST for default behavior)
# V12 CHANGES:
# - Increased BASE_GOLPE threshold to 40% (4/10 votes minimum)
# - Added stability window before state changes
# - Improved hysteresis to prevent false transitions
# ========================================================================================================
import time
from collections import deque


# V13: Presets for optional tuning (FAST is now the default baseline)
PRESETS = {
    "FAST": {
        "min_hold_seconds": 0.8,
        "cooldown_seconds": 0.2,
        "hysteresis_margin": 0.04,
        "stability_window_ms": 120,
        "inter_state_cooldown_ms": 0,
        "ema_alpha": 0.5,
        "buffer_size": 2,
    },
    "STABLE": {
        "min_hold_seconds": 1.2,
        "cooldown_seconds": 2.0,
        "hysteresis_margin": 0.07,
        "stability_window_ms": 180,
        "inter_state_cooldown_ms": 0,
        "ema_alpha": 0.3,
        "buffer_size": 4,
    },
}

class StateManager:
    """
    Gestor de estados V12 optimizado con estabilidad mejorada.

    V12 Features:
    - Override ATAQUE ≥80% (2 frames, elapsed≥0.20s, hold≤0.20s)
    - BASE_GOLPE requires 4/10 votes (40% threshold)
    - 350ms stability window before state changes
    - 500ms cooldown between states
    - Improved hysteresis for clean transitions

    Expone get_state() y get_energy() para CueEngine.
    """

    # Constantes de estado
    STATE_BAJADA = "BAJADA"
    STATE_BASE_GOLPE = "BASE_GOLPE"
    STATE_ATAQUE = "ATAQUE"
    STATE_BRAKE = "BRAKE"

    # V13: FAST BASELINE - stability parameters for low-latency response
    STABILITY_WINDOW_MS = 120  # V13: Fast baseline (was 180)
    INTER_STATE_COOLDOWN_MS = 0  # No cooldown for musical flow

    # V13: ATAQUE margin requirement (prevent false ATAQUE when close to BAJADA)
    ATAQUE_MARGIN_MIN = 0.12  # ATAQUE needs 12% margin over second score

    def __init__(self, energy_detector, min_hold_seconds=0.8, hysteresis_margin=0.04, cooldown_seconds=0.2):
        """
        V13: Inicializa con FAST BASELINE por defecto (sin necesidad de preset).
        Lag típico esperado: 120-250ms.
        """
        self.min_hold_seconds = min_hold_seconds
        self.hysteresis_margin = hysteresis_margin
        self.cooldown_seconds = cooldown_seconds

        # ✅ SPRINT 1: Energía Interna + EMA smoothing
        self._energy_detector = energy_detector
        self._energy_history = deque(maxlen=3)
        self._current_energy = "MEDIA"
        self._scores_smooth = {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}
        self._ema_alpha = 0.5  # V13: Fast baseline (was 0.3)

        # ✅ SPRINT 2: Histéresis adaptativa + BRAKE real + Holds
        self._hysteresis_matrix = {
            "BAJADA": {"BAJADA": 0.0, "BASE_GOLPE": 0.08, "ATAQUE": 0.12, "BRAKE": 0.10},
            "BASE_GOLPE": {"BAJADA": 0.05, "BASE_GOLPE": 0.0, "ATAQUE": 0.10, "BRAKE": 0.08},
            "ATAQUE": {"BAJADA": 0.08, "BASE_GOLPE": 0.08, "ATAQUE": 0.0, "BRAKE": 0.05},
            "BRAKE": {"BAJADA": 0.18, "BASE_GOLPE": 0.15, "ATAQUE": 0.12, "BRAKE": 0.0},
        }

        self.BRAKE_ENTRY_THRESHOLD = 0.52
        self.BRAKE_SUSTAINED_THRESHOLD = 0.48
        self.BRAKE_EXIT_THRESHOLD = 0.35

        self._hold_config = {
            "BAJADA": {"hard": 0.3, "priority": {"ATAQUE", "BRAKE"}},
            "BASE_GOLPE": {"hard": 0.6, "priority": {"ATAQUE", "BRAKE"}},
            "ATAQUE": {"hard": 0.8, "priority": {"BRAKE"}},
            "BRAKE": {"hard": 1.5, "priority": set()},
        }

        # ✅ SPRINT 3: Persistencia de ATAQUE (3 frames)
        self._atk_persistence = deque(maxlen=3)

        # ✅ SPRINT 4: Clean Rise + Peak Lock + Anti-rebote
        self._atk_rise_buffer = deque(maxlen=5)
        self._atk_peak_lock = 0.0

        # ✅ SPRINT 5: BASE_GOLPE estable + BAJADA real
        self._golpe_persistence = deque(maxlen=3)
        self._bajada_persistence = deque(maxlen=3)

        # ✅ SPRINT 6: Ultra Stability Layer
        self._global_state_buffer = deque(maxlen=4)
        self._global_lock = 0.0

        # V12: Pending state tracker for stability window (350ms)
        self._pending_state = None
        self._pending_state_since = 0.0

        # Estados posibles
        self.STATES = [self.STATE_BAJADA, self.STATE_BASE_GOLPE, self.STATE_ATAQUE, self.STATE_BRAKE]
        
        # Estado actual
        self.current_state = self.STATE_BAJADA
        self.previous_state = None
        self.state_start_time = time.time()
        self.last_transition_time = 0.0
        
        # Timers y holds
        self.hold_remaining = 0.0
        self.cooldown_remaining = 0.0
        self.ataque_timer = 0.0
        self.brake_timer = 0.0
        
        # V13: Sistema de estabilización FAST BASELINE
        self.stability_buffer = []
        self.buffer_size = 2  # V13: Fast baseline (was 4)
        self.min_confidence = 0.50
        
        # Historial para tie-breaker
        self.recent_picks = deque(maxlen=3)
        
        # Parámetros de override SOLO ATAQUE
        self.atk_override_threshold = 0.80
        self.atk_override_min_frames = 2
        self.atk_override_min_elapsed = 0.20
        self.atk_override_cooldown = 0.35
        
        self._atk_over80_count = 0
        self._last_change_ts = 0.0

        # Estadísticas
        self.stats = {
            "transitions": 0,
            "ataque_interrupts": 0,
            "brake_interrupts": 0,
            "blocked_by_hold": 0,
            "blocked_by_cooldown": 0,
            "blocked_by_confidence": 0,
            "ataque_overrides": 0,
            "last_scores": {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}
        }
        
        # Control manual
        self.force_state = None
        self.bypass_hold = False

        # ✅ CALENDAR BRIDGE: Estados deshabilitados por calendario (para decisión)
        # Cuando un estado está aquí, su score efectivo = 0.0 para la selección
        self._disabled_states: set = set()

        # MIL-Lite: Pesos por categoria (default 1.0 = sin efecto)
        self._mil_weights = {"bajada": 1.0, "base_golpe": 1.0, "ataque": 1.0, "brake": 1.0}
        self._mil_profile = ""  # Nombre de perfil activo (vacio = MIL inactivo)

        # Cache
        self._last_update_time = time.time()
        self._last_scores = {}

        # V13: Lag instrumentation
        self._t_score = 0.0       # When scores were calculated
        self._t_candidate = 0.0   # When candidate was determined
        self._t_commit = 0.0      # When state change was committed
        self._lag_stats = {
            "last_lag_candidate_ms": 0.0,
            "last_lag_commit_ms": 0.0,
            "last_lag_total_ms": 0.0,
            "avg_lag_total_ms": 0.0,
            "samples": 0,
        }

        # V13: Current preset name (FAST is default baseline)
        self._current_preset = "FAST"

        print(f"[StateManager] V13 FAST BASELINE - hold={min_hold_seconds}s, cooldown={cooldown_seconds}s, hysteresis={hysteresis_margin}, stability={self.STABILITY_WINDOW_MS}ms, ema={self._ema_alpha}, buffer={self.buffer_size}")
    
    # ✅ ====== NUEVO: MÉTODOS PÚBLICOS PARA CUEENGINE ======
    def get_state(self) -> str:
        """
        Retorna el estado actual del StateManager.

        Returns:
            str: Nombre del estado actual ("BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE")
        """
        return getattr(self, "current_state", "UNKNOWN")

    def get_energy(self) -> str:
        """
        Retorna el nombre de energía en {"BAJA", "MEDIA", "ALTA"}.

        ✅ SPRINT 1: Ahora usa EnergyDetector con moda de últimos 3 frames.

        Returns:
            str: Nombre de energía ("BAJA", "MEDIA", "ALTA")
        """
        return getattr(self, "_current_energy", "MEDIA")

    def get_lag_stats(self) -> dict:
        """
        V13: Retorna estadísticas de lag de decisión de estados.

        Returns:
            dict: {last_lag_candidate_ms, last_lag_commit_ms, last_lag_total_ms, avg_lag_total_ms, samples}
        """
        return self._lag_stats.copy()

    def apply_preset(self, preset_name: str) -> bool:
        """
        V13: Aplica un preset de configuración (opcional, FAST ya es default).

        Args:
            preset_name: Nombre del preset ("FAST" o "STABLE")
                        "FAST_BOLICHE" es alias de "FAST"

        Returns:
            bool: True si se aplicó correctamente
        """
        preset_name = preset_name.upper()
        # Alias for backwards compatibility
        if preset_name == "FAST_BOLICHE":
            preset_name = "FAST"
        if preset_name not in PRESETS:
            print(f"[StateManager] PRESET desconocido: {preset_name}")
            return False

        preset = PRESETS[preset_name]
        old_preset = self._current_preset

        # Apply preset values
        self.min_hold_seconds = preset["min_hold_seconds"]
        self.cooldown_seconds = preset["cooldown_seconds"]
        self.hysteresis_margin = preset["hysteresis_margin"]
        self.STABILITY_WINDOW_MS = preset["stability_window_ms"]
        self.INTER_STATE_COOLDOWN_MS = preset["inter_state_cooldown_ms"]
        self._ema_alpha = preset["ema_alpha"]
        self.buffer_size = preset["buffer_size"]
        self._current_preset = preset_name

        print(f"[StateManager] PRESET {old_preset}->{preset_name}: hold={self.min_hold_seconds}s, cooldown={self.cooldown_seconds}s, hysteresis={self.hysteresis_margin}, stability={self.STABILITY_WINDOW_MS}ms, ema={self._ema_alpha}, buffer={self.buffer_size}")
        return True

    def get_current_preset(self) -> str:
        """V13: Retorna el nombre del preset actual."""
        return self._current_preset

    # ====== MIL-LITE: PESOS ADAPTATIVOS ======
    def set_mil_weights(self, weights: dict, profile: str = "") -> None:
        """
        MIL-Lite: Establece pesos por categoria para ponderar scores.
        Todos los valores se clamean a [0.8, 1.2].
        Con pesos en 1.0 el comportamiento es identico al original.
        """
        for k in ("bajada", "base_golpe", "ataque", "brake"):
            v = float(weights.get(k, 1.0))
            self._mil_weights[k] = max(0.8, min(1.2, v))
        self._mil_profile = str(profile)

    def get_mil_weights(self) -> dict:
        """Retorna pesos MIL-Lite actuales."""
        return self._mil_weights.copy()

    # ====== CALENDAR BRIDGE: CONTROL DE ESTADOS ======
    def set_disabled_states(self, states: list) -> None:
        """
        Establece los estados deshabilitados por el calendario.

        Cuando un estado está deshabilitado:
        - Su score efectivo = 0.0 para la selección de winner
        - NUNCA puede ser elegido como next_state
        - Los raw scores siguen mostrándose en logs

        Args:
            states: Lista de estados a deshabilitar (ej: ["ATAQUE", "BRAKE"])
        """
        old_disabled = self._disabled_states.copy()
        self._disabled_states = set(s.upper() for s in states)

        # Log solo cuando cambia
        if self._disabled_states != old_disabled:
            if self._disabled_states:
                print(f"[StateManager] 📅 Estados DESHABILITADOS para decisión: {sorted(self._disabled_states)}")
            else:
                print("[StateManager] 📅 Todos los estados HABILITADOS para decisión")

    def get_disabled_states(self) -> list:
        """Retorna lista de estados deshabilitados."""
        return sorted(list(self._disabled_states))
    # ✅ ====== FIN MÉTODOS PÚBLICOS ======
    
    def update(self, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """
        Actualiza el estado con override para ATAQUE ≥80% y calibración de precisión.
        """
        try:
            current_time = time.time()
            dt = current_time - self._last_update_time
            self._last_update_time = current_time
            
            # Actualizar timers
            self.hold_remaining = max(0.0, self.hold_remaining - dt)
            self.cooldown_remaining = max(0.0, self.cooldown_remaining - dt)
            self.ataque_timer = max(0.0, self.ataque_timer - dt)
            self.brake_timer = max(0.0, self.brake_timer - dt)
            
            # Estado forzado manual (bypass de todo)
            if self.force_state and self.force_state in self.STATES:
                if self.force_state != self.current_state:
                    self._change_state(self.force_state, reason="MANUAL_FORCE")
                self.force_state = None
                return

            # ✅ SPRINT 1: Moda de energía de últimos 3 frames
            raw_energy = self._energy_detector.get_energy_name()
            self._energy_history.append(raw_energy)
            self._current_energy = max(set(self._energy_history), key=self._energy_history.count)

            # V13: Calcular puntuaciones + timestamp
            self._t_score = time.perf_counter()
            scores = self._calculate_scores_responsive(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            self._last_scores = scores.copy()

            # ✅ SPRINT 1: Aplicar EMA smoothing a los scores
            for k, v in scores.items():
                prev = self._scores_smooth.get(k, 0.0)
                self._scores_smooth[k] = (self._ema_alpha * v) + ((1 - self._ema_alpha) * prev)

            # ✅ SPRINT 3: Tracking de persistencia de ATAQUE
            current_atk = 1 if self._scores_smooth["ataque"] >= 0.68 else 0
            self._atk_persistence.append(current_atk)

            # ✅ SPRINT 4: Tracking clean rise + decrementar peak lock
            self._atk_rise_buffer.append(self._scores_smooth["ataque"])
            if self._atk_peak_lock > 0:
                self._atk_peak_lock -= dt

            # ✅ SPRINT 5: Tracking de persistencia de BASE_GOLPE y BAJADA
            self._golpe_persistence.append(1 if self._scores_smooth["base_golpe"] >= 0.52 else 0)
            self._bajada_persistence.append(1 if self._scores_smooth["bajada"] >= 0.38 else 0)

            # ✅ SPRINT 6: Tracking global de estado + decrementar global lock
            self._global_state_buffer.append(self.current_state)
            if self._global_lock > 0:
                self._global_lock -= dt

            # Tracking para override SOLO ATAQUE
            if scores.get("ataque", 0.0) >= self.atk_override_threshold:
                self._atk_over80_count += 1
            else:
                self._atk_over80_count = 0
            
            # Guardar en estadísticas
            self.stats["last_scores"] = {
                "bajada": scores.get("bajada", 0.0),
                "base_golpe": scores.get("base_golpe", 0.0), 
                "ataque": scores.get("ataque", 0.0),
                "brake": scores.get("brake", 0.0)
            }
            
            # V13: Determinar próximo estado + timestamp
            next_state = self._determine_next_state_responsive(scores)
            self._t_candidate = time.perf_counter()

            # Cambiar estado si pasa validaciones
            if next_state != self.current_state:
                change_reason = self._get_change_reason(next_state, scores)
                if self._can_change_state_responsive(next_state, scores):
                    self._change_state(next_state, reason=change_reason)
                else:
                    # Estadísticas de bloqueos
                    if self.hold_remaining > 0:
                        self.stats["blocked_by_hold"] += 1
                    elif self.cooldown_remaining > 0:
                        self.stats["blocked_by_cooldown"] += 1
                    else:
                        self.stats["blocked_by_confidence"] += 1
            
        except Exception as e:
            print(f"[StateManager] Error en update: {e}")
    
    def _calculate_scores_responsive(self, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Calcula puntuaciones con mínimo filtering para respuesta rápida."""
        scores = {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}
        
        # Votos de bajada
        if modules_bajada:
            active_bajada = sum(1 for m in modules_bajada if self._is_module_active(m))
            scores["bajada"] = active_bajada / len(modules_bajada)
        
        # Votos de golpe
        if modules_golpe:
            active_golpe = sum(1 for m in modules_golpe if self._is_module_active(m))
            scores["base_golpe"] = active_golpe / len(modules_golpe)
        
        # Votos de ataque
        if modules_ataque:
            active_ataque = sum(1 for m in modules_ataque if self._is_module_active(m))
            scores["ataque"] = active_ataque / len(modules_ataque)
        
        # Votos de brake
        if modules_brake:
            active_brake = sum(1 for m in modules_brake if self._is_module_active(m))
            scores["brake"] = active_brake / len(modules_brake)

        # MIL-Lite: aplicar pesos por categoria (default 1.0 = sin efecto)
        for k in scores:
            scores[k] = min(1.0, scores[k] * self._mil_weights.get(k, 1.0))

        return self._apply_light_smoothing(scores)
    
    def _apply_light_smoothing(self, new_scores):
        """Aplica smoothing ligero para evitar jitter sin lag."""
        self.stability_buffer.append(new_scores.copy())
        
        if len(self.stability_buffer) > self.buffer_size:
            self.stability_buffer.pop(0)
        
        if len(self.stability_buffer) >= self.buffer_size:
            smoothed_scores = {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}
            
            for state in smoothed_scores.keys():
                total = sum(scores.get(state, 0.0) for scores in self.stability_buffer)
                smoothed_scores[state] = total / len(self.stability_buffer)
            
            return smoothed_scores
        else:
            return new_scores
    
    def _is_module_active(self, module):
        """
        Determina si un módulo está activo con normalización robusta.
        """
        try:
            if not hasattr(module, 'card') or not module.card:
                return False
            
            # Estrategia 1: usar is_on()
            if hasattr(module.card, 'is_on') and callable(module.card.is_on):
                try:
                    return bool(module.card.is_on())
                except Exception as e:
                    module_name = getattr(module, 'name', 'Unknown')
                    print(f"[StateManager] Warning: is_on() falló para {module_name}: {e}")
            
            # Estrategia 2: acceso directo a _on
            if hasattr(module.card, '_on'):
                return bool(getattr(module.card, '_on', False))
            
            # Estrategia 3: cálculo basado en valor/thresholds/match
            try:
                if (hasattr(module.card, 'get_value') and 
                    hasattr(module.card, 'get_thresholds') and 
                    hasattr(module.card, 'get_match')):
                    
                    current_value = module.card.get_value()
                    if current_value is None:
                        return False
                    
                    lo, hi = module.card.get_thresholds()
                    match = module.card.get_match()
                    
                    # Convertir a float
                    current_value = float(current_value)
                    lo = float(lo) if lo is not None else 0.0
                    hi = float(hi) if hi is not None else 1.0
                    match = float(match) if match is not None else 0.0
                    
                    # Normalización robusta
                    if current_value > 1.0 or current_value < 0.0:
                        if current_value > 1.0:
                            current_value = current_value / 100.0
                        current_value = max(0.0, min(1.0, current_value))
                    
                    if lo > 1.0 or lo < 0.0:
                        if lo > 1.0:
                            lo = lo / 100.0
                        lo = max(0.0, min(1.0, lo))
                    
                    if hi > 1.0 or hi < 0.0:
                        if hi > 1.0:
                            hi = hi / 100.0
                        hi = max(0.0, min(1.0, hi))
                    
                    if match > 1.0 or match < 0.0:
                        if match > 1.0:
                            match = match / 100.0
                        match = max(0.0, min(1.0, match))
                    
                    # Validación: asegurar lo <= hi
                    if lo > hi:
                        lo, hi = hi, lo
                    
                    threshold_ok = (lo <= current_value <= hi)
                    match_ok = (current_value >= match)
                    
                    return threshold_ok and match_ok
                    
            except Exception as e:
                module_name = getattr(module, 'name', 'Unknown')
                print(f"[StateManager] Warning: Error calculando estado de {module_name}: {e}")
            
            return False
            
        except Exception as e:
            module_name = getattr(module, 'name', 'Unknown')
            print(f"[StateManager] Error general verificando {module_name}: {e}")
            return False
    
    def _atk_has_clean_rise(self):
        """
        ✅ SPRINT 4: Verifica si ATAQUE tiene una subida limpia (últimos 4 valores crecientes).
        """
        if len(self._atk_rise_buffer) < 4:
            return False
        b = list(self._atk_rise_buffer)
        return b[-1] > b[-2] > b[-3]

    def _bajada_has_clean_drop(self):
        """
        ✅ SPRINT 5: Verifica si BAJADA tiene caída sostenida (≥2 frames de últimos 3).
        """
        if len(self._bajada_persistence) < 3:
            return False
        return sum(self._bajada_persistence) >= 2

    def _determine_next_state_responsive(self, scores):
        """
        V12: Decisor con umbrales estables y tie-breaker.
        Orden de prioridad: BRAKE > ATAQUE > BASE_GOLPE > BAJADA

        V12 Thresholds:
        - BRAKE: 65% (unchanged)
        - ATAQUE: 68% (unchanged, but with clean rise)
        - BASE_GOLPE: 40% (4/10 votes minimum, was 52%)
        - BAJADA: 35% (was 38%, more stable entry)

        CALENDAR BRIDGE:
        - Estados en _disabled_states tienen effective_score = 0.0
        - NUNCA pueden ser elegidos como winner
        """
        BRAKE_THRESHOLD = 0.65
        ATAQUE_THRESHOLD = 0.68
        GOLPE_THRESHOLD = 0.30  # V12.1: Lowered to 3/10 votes for better sensitivity
        BAJADA_THRESHOLD = 0.35  # V12: Slightly lowered for stability

        # ✅ CALENDAR BRIDGE: Crear effective_scores (disabled = 0.0)
        effective_scores = scores.copy()
        state_key_map = {
            "BRAKE": "brake",
            "ATAQUE": "ataque",
            "BASE_GOLPE": "base_golpe",
            "BAJADA": "bajada"
        }
        for disabled_state in self._disabled_states:
            key = state_key_map.get(disabled_state.upper())
            if key:
                effective_scores[key] = 0.0

        # Logging de scores altos (RAW + disabled info)
        max_score = max(scores.values())
        if max_score > 0.7:
            disabled_str = f" disabled={sorted(self._disabled_states)}" if self._disabled_states else ""
            print(f"[StateManager] HIGH_SCORES: Brake={scores['brake']:.2f}, Ataque={scores['ataque']:.2f}, Golpe={scores['base_golpe']:.2f}, Bajada={scores['bajada']:.2f}{disabled_str}")

        # ✅ SPRINT 3: Mantener ATAQUE si hay persistencia (≥2 frames activos de últimos 3)
        # PERO solo si ATAQUE no está deshabilitado
        if self.current_state == self.STATE_ATAQUE and "ATAQUE" not in self._disabled_states:
            if sum(self._atk_persistence) >= 2:
                return self.STATE_ATAQUE

        # Decisión por prioridad (usando effective_scores)
        if effective_scores["brake"] >= BRAKE_THRESHOLD:
            return self.STATE_BRAKE
        elif effective_scores["ataque"] >= ATAQUE_THRESHOLD:
            # ✅ SPRINT 4: Requerir clean rise o estar ya en ATAQUE
            if self._atk_has_clean_rise() or self.current_state == self.STATE_ATAQUE:
                return self.STATE_ATAQUE
        elif effective_scores["base_golpe"] >= GOLPE_THRESHOLD:
            # ✅ SPRINT 5: BASE_GOLPE requiere persistencia (≥2 frames)
            if sum(self._golpe_persistence) >= 2:
                return self.STATE_BASE_GOLPE
        elif effective_scores["bajada"] >= BAJADA_THRESHOLD:
            # ✅ SPRINT 5: BAJADA requiere caída sostenida
            if self._bajada_has_clean_drop():
                return self.STATE_BAJADA

        # Tie-breaker: si hay empate técnico, favorecer el menos usado
        # (usando effective_scores para excluir disabled)
        candidates = []
        for state_name, threshold in [
            (self.STATE_BRAKE, BRAKE_THRESHOLD),
            (self.STATE_ATAQUE, ATAQUE_THRESHOLD),
            (self.STATE_BASE_GOLPE, GOLPE_THRESHOLD),
            (self.STATE_BAJADA, BAJADA_THRESHOLD)
        ]:
            score_key = self._state_to_score_key(state_name)
            if effective_scores.get(score_key, 0.0) >= threshold - 0.03:
                candidates.append((state_name, effective_scores.get(score_key, 0.0)))

        if len(candidates) > 1:
            # Ordenar por score descendente
            candidates.sort(key=lambda x: x[1], reverse=True)
            best_score = candidates[0][1]
            second_score = candidates[1][1]

            # Si diferencia <= 0.03, usar tie-breaker
            if abs(best_score - second_score) <= 0.03:
                for state_name, _ in candidates:
                    if state_name not in self.recent_picks:
                        return state_name

        return self.current_state
    
    def _can_change_state_responsive(self, new_state, scores):
        """
        V12: Validación con stability window (350ms) y inter-state cooldown (500ms).
        Override para ATAQUE ≥80% estable.
        """
        current_time = time.time()

        # V12: Inter-state cooldown check (500ms minimum between changes)
        time_since_last_change = (current_time - self._last_change_ts) * 1000  # ms
        if time_since_last_change < self.INTER_STATE_COOLDOWN_MS:
            # Allow BRAKE to bypass cooldown (emergency priority)
            if new_state != self.STATE_BRAKE:
                return False

        # V12: Stability window check (350ms minimum consistency)
        if new_state != self.STATE_BRAKE:  # BRAKE bypasses stability window
            if self._pending_state != new_state:
                # New pending state detected, start tracking
                self._pending_state = new_state
                self._pending_state_since = current_time
                return False  # Not stable yet
            else:
                # Same pending state, check if stable for 350ms
                pending_duration_ms = (current_time - self._pending_state_since) * 1000
                if pending_duration_ms < self.STABILITY_WINDOW_MS:
                    return False  # Not stable long enough

        # V13: ATAQUE margin check - require clear margin over second score
        if new_state == self.STATE_ATAQUE:
            ataque_score = scores.get("ataque", 0.0)
            # Find second highest score (excluding ataque)
            other_scores = [(k, v) for k, v in scores.items() if k != "ataque"]
            other_scores.sort(key=lambda x: x[1], reverse=True)
            if other_scores:
                second_name, second_score = other_scores[0]
                margin = ataque_score - second_score
                if margin < self.ATAQUE_MARGIN_MIN:
                    print(f"[StateManager] ATAQUE_BLOCKED margin={margin:.2f} < {self.ATAQUE_MARGIN_MIN} winner={ataque_score:.2f} second={second_name.upper()[:2]} {second_score:.2f}")
                    return False

        # --- OVERRIDE SOLO ATAQUE (estable) ---
        if new_state == self.STATE_ATAQUE:
            new_score = scores.get("ataque", 0.0)
            
            # Brake tiene prioridad absoluta si también está ≥0.80
            if scores.get("brake", 0.0) >= self.atk_override_threshold:
                pass  # no permitir override si Brake ≥ 0.80
            else:
                if new_score >= self.atk_override_threshold:
                    over80_ok = (self._atk_over80_count >= self.atk_override_min_frames)
                    elapsed = time.time() - (self._last_change_ts or 0.0)
                    hold_ok = (self.hold_remaining <= 0.20)
                    
                    # Validación adicional: bajada no debe estar muy alta
                    bajada_score = scores.get("bajada", 0.0)
                    bajada_ok = (bajada_score < 0.55) or ((new_score - bajada_score) >= 0.15)
                    
                    if over80_ok and elapsed >= self.atk_override_min_elapsed and hold_ok and bajada_ok:
                        # Cooldown extra para evitar rebote inmediato
                        self.cooldown_remaining = max(self.cooldown_remaining, self.atk_override_cooldown)
                        self.stats["ataque_overrides"] += 1
                        print(f"[StateManager] 🔥 OVERRIDE ATAQUE activado (score={new_score:.2f}, frames={self._atk_over80_count})")
                        return True
        # --- FIN OVERRIDE SOLO ATAQUE ---

        # ✅ SPRINT 3: Bloqueo de salida de ATAQUE si hay persistencia (excepto a BRAKE)
        if self.current_state == self.STATE_ATAQUE:
            if sum(self._atk_persistence) >= 2 and new_state != self.STATE_BRAKE:
                return False

        # ✅ SPRINT 4: Bloqueo peak lock - evitar rebote inmediato post-ATAQUE
        if self.current_state == self.STATE_ATAQUE and self._atk_peak_lock > 0:
            if new_state != self.STATE_BRAKE:
                return False

        # ✅ SPRINT 6: Ultra Stability Layer - TEMPORALMENTE DESACTIVADO
        # MOTIVO: Los bloqueos globales causan retención falsa del estado BAJADA
        # cuando los scores reales indican GOLPE/ATAQUE (scores 0.60-0.90).
        # La exigencia de count >= 2 en historial de 4 frames impide transiciones
        # legítimas, especialmente cuando BAJADA tiene smoothing alto.
        # Sprints 1-5 ya proveen suficiente estabilidad (EMA, persistencia, clean rise).

        # Bloqueo 1: Global lock activo (post-cambio de estado)
        # if self._global_lock > 0 and new_state != self.STATE_BRAKE:
        #     return False

        # Bloqueo 2: El nuevo estado debe aparecer al menos 2 veces en el historial de 4
        # if len(self._global_state_buffer) == 4:
        #     if self._global_state_buffer.count(new_state) < 2 and new_state != self.STATE_BRAKE:
        #         return False

        # Validación normal para todos los estados
        if self.bypass_hold:
            return True
        
        if self.hold_remaining > 0:
            return False
            
        if self.cooldown_remaining > 0:
            return False
        
        # Histéresis CALIBRADA
        current_score = scores.get(self._state_to_score_key(self.current_state), 0.0)
        new_score = scores.get(self._state_to_score_key(new_state), 0.0)
        
        if (new_score < current_score + self.hysteresis_margin and 
            current_score > 0.4 and new_score > 0.4):
            return False
        
        if new_score < self.min_confidence:
            return False
        
        return True
    
    def _state_to_score_key(self, state):
        """Convierte nombre de estado a clave de score."""
        mapping = {
            self.STATE_BAJADA: "bajada",
            self.STATE_BASE_GOLPE: "base_golpe", 
            self.STATE_ATAQUE: "ataque",
            self.STATE_BRAKE: "brake"
        }
        return mapping.get(state, "bajada")
    
    def _get_change_reason(self, new_state, scores):
        """Determina la razón del cambio de estado."""
        score_key = self._state_to_score_key(new_state)
        score = scores.get(score_key, 0.0)
        
        if score >= 0.80:
            return "HIGH_SCORE"
        elif score >= 0.65:
            return "THRESHOLD"
        else:
            return "DEFAULT"
    
    def _change_state(self, new_state, reason="UNKNOWN"):
        """
        V13: Cambia el estado actual con stability tracking, lag instrumentation y logging.
        """
        if new_state == self.current_state:
            return

        # V13: Record commit timestamp and calculate lag
        self._t_commit = time.perf_counter()
        lag_candidate_ms = (self._t_candidate - self._t_score) * 1000.0 if self._t_score > 0 else 0.0
        lag_commit_ms = (self._t_commit - self._t_candidate) * 1000.0 if self._t_candidate > 0 else 0.0
        lag_total_ms = (self._t_commit - self._t_score) * 1000.0 if self._t_score > 0 else 0.0

        # Update lag stats
        self._lag_stats["last_lag_candidate_ms"] = lag_candidate_ms
        self._lag_stats["last_lag_commit_ms"] = lag_commit_ms
        self._lag_stats["last_lag_total_ms"] = lag_total_ms
        n = self._lag_stats["samples"]
        if n == 0:
            self._lag_stats["avg_lag_total_ms"] = lag_total_ms
        else:
            self._lag_stats["avg_lag_total_ms"] = (self._lag_stats["avg_lag_total_ms"] * n + lag_total_ms) / (n + 1)
        self._lag_stats["samples"] += 1

        self.previous_state = self.current_state
        old_state = self.current_state
        self.current_state = new_state

        current_time = time.time()
        self.state_start_time = current_time
        self.last_transition_time = current_time

        # Registrar timestamp del cambio real
        self._last_change_ts = current_time

        # V12: Clear pending state after successful transition
        self._pending_state = None
        self._pending_state_since = 0.0

        # Actualizar historial para tie-breaker
        self.recent_picks.append(new_state)

        self.stats["transitions"] += 1

        # ✅ SPRINT 6: Establecer global lock al cambiar de estado
        if new_state != old_state:
            self._global_lock = 0.12
        
        # Holds diferenciados CALIBRADOS
        if new_state == self.STATE_ATAQUE:
            self.hold_remaining = self.min_hold_seconds * 1.2
            self.ataque_timer = 8.0
            # ✅ SPRINT 4: Establecer peak lock al entrar a ATAQUE
            self._atk_peak_lock = 0.18
        elif new_state == self.STATE_BRAKE:
            self.hold_remaining = self.min_hold_seconds * 1.2
            self.brake_timer = 4.0
        elif new_state == self.STATE_BASE_GOLPE:
            self.hold_remaining = self.min_hold_seconds * 0.6
        elif new_state == self.STATE_BAJADA:
            self.hold_remaining = self.min_hold_seconds * 0.4
        
        if old_state in [self.STATE_ATAQUE, self.STATE_BRAKE]:
            self.cooldown_remaining = self.cooldown_seconds
            if old_state == self.STATE_ATAQUE:
                self.stats["ataque_interrupts"] += 1
            else:
                self.stats["brake_interrupts"] += 1
        
        self.stability_buffer.clear()

        # V13: Log compacto con lag info
        scores = self._last_scores
        print(f"[STATE] {old_state}->{new_state} | scores={{BG:{scores.get('base_golpe', 0.0):.2f}, BJ:{scores.get('bajada', 0.0):.2f}, AT:{scores.get('ataque', 0.0):.2f}, BR:{scores.get('brake', 0.0):.2f}}} | reason={reason} | lag={{cand:{lag_candidate_ms:.1f}ms, commit:{lag_commit_ms:.1f}ms, total:{lag_total_ms:.1f}ms}}")
    
    def get_status(self):
        """Retorna el estado actual completo."""
        current_time = time.time()
        time_in_state = current_time - self.state_start_time
        
        scores_ui = {}
        if self._last_scores:
            scores_ui = {
                "BAJADA": self._last_scores.get("bajada", 0.0),
                "BASE_GOLPE": self._last_scores.get("base_golpe", 0.0),
                "ATAQUE": self._last_scores.get("ataque", 0.0),
                "BRAKE": self._last_scores.get("brake", 0.0)
            }
        
        return {
            "current_state": self.current_state,
            "previous_state": self.previous_state or "—",
            "time_in_state": time_in_state,
            "holds": {
                "min_hold": self.min_hold_seconds,
                "remaining": self.hold_remaining
            },
            "timers": {
                "ataque": self.ataque_timer,
                "brake": self.brake_timer
            },
            "scores": scores_ui,
            "stats": self.stats.copy(),
            "hold_remaining": self.hold_remaining,
            "cooldown_remaining": self.cooldown_remaining,
            "ataque_timer": self.ataque_timer,
            "brake_timer": self.brake_timer,
            "responsiveness_info": {
                "buffer_size": len(self.stability_buffer),
                "buffer_capacity": self.buffer_size,
                "hysteresis_margin": self.hysteresis_margin,
                "min_confidence": self.min_confidence,
                "blocked_by_confidence": self.stats.get("blocked_by_confidence", 0)
            },
            "mil_weights": self._mil_weights.copy(),
            "mil_profile": self._mil_profile,
            "override_info": {
                "atk_over80_count": self._atk_over80_count,
                "atk_threshold": self.atk_override_threshold,
                "atk_min_frames": self.atk_override_min_frames,
                "atk_overrides_total": self.stats.get("ataque_overrides", 0)
            }
        }
    
    def reset(self):
        """Resetea el StateManager al estado inicial."""
        self.current_state = self.STATE_BAJADA
        self.previous_state = None
        current_time = time.time()
        self.state_start_time = current_time
        self.last_transition_time = current_time
        self.hold_remaining = 0.0
        self.cooldown_remaining = 0.0
        self.ataque_timer = 0.0
        self.brake_timer = 0.0
        self.force_state = None
        self.bypass_hold = False
        self.stability_buffer.clear()
        self.recent_picks.clear()
        
        # Reset override tracking
        self._atk_over80_count = 0
        self._last_change_ts = 0.0

        # ✅ SPRINT 1: Reset energía y scores smooth
        self._energy_history.clear()
        self._current_energy = "MEDIA"
        self._scores_smooth = {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}

        # ✅ SPRINT 3: Reset persistencia de ATAQUE
        self._atk_persistence.clear()

        # ✅ SPRINT 4: Reset clean rise buffer y peak lock
        self._atk_rise_buffer.clear()
        self._atk_peak_lock = 0.0

        # ✅ SPRINT 5: Reset persistencia de BASE_GOLPE y BAJADA
        self._golpe_persistence.clear()
        self._bajada_persistence.clear()

        # ✅ SPRINT 6: Reset global stability layer
        self._global_state_buffer.clear()
        self._global_lock = 0.0

        # V12: Reset pending state tracker
        self._pending_state = None
        self._pending_state_since = 0.0

        # ✅ CALENDAR BRIDGE: NO resetear _disabled_states (controlado externamente)
        # El calendario mantiene su propio estado

        for key in self.stats:
            if key == "last_scores":
                self.stats[key] = {"bajada": 0.0, "base_golpe": 0.0, "ataque": 0.0, "brake": 0.0}
            else:
                self.stats[key] = 0
        
        self._last_scores = {}
        print("[StateManager] RESET - CALIBRADO con Override ATAQUE>=80% + feed state/energy")

    def get_performance_metrics(self):
        """Métricas de performance para debugging"""
        current_time = time.time()
        
        return {
            "buffer_fill": len(self.stability_buffer) / self.buffer_size,
            "hold_active": self.hold_remaining > 0,
            "cooldown_active": self.cooldown_remaining > 0,
            "time_since_transition": current_time - self.last_transition_time,
            "current_state": self.current_state,
            "thresholds": {
                "min_hold": self.min_hold_seconds,
                "hysteresis": self.hysteresis_margin,
                "cooldown": self.cooldown_seconds,
                "min_confidence": self.min_confidence
            },
            "blocks": {
                "hold": self.stats.get("blocked_by_hold", 0),
                "cooldown": self.stats.get("blocked_by_cooldown", 0),
                "confidence": self.stats.get("blocked_by_confidence", 0)
            },
            "override": {
                "atk_over80_count": self._atk_over80_count,
                "atk_threshold": self.atk_override_threshold,
                "atk_overrides_total": self.stats.get("ataque_overrides", 0),
                "elapsed_since_change": current_time - self._last_change_ts
            }
        }


# StateMonitorWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QGroupBox, QGridLayout, QMessageBox
)

class StateMonitorWidget(QWidget):
    """Widget que muestra el estado actual del StateManager"""
    
    def __init__(self, state_manager):
        super().__init__()
        self.state_manager = state_manager
        
        self.setMinimumWidth(450)
        self.setMinimumHeight(450)

        # Cache
        self._last_state = None
        self._last_color = None
        self._last_time = None
        self._last_scores = None
        self._last_transitions = None
        self._last_interrupts = None
        
        self._setup_ui()
        
        # Timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(100)
        
        self.update_display()

    def _setup_ui(self):
        """Construye toda la UI del widget"""
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        
        # Header: estado principal grande
        self.state_main = QLabel("—")
        self.state_main.setAlignment(Qt.AlignCenter)
        self.state_main.setStyleSheet(
            "color:#ccc; font-weight:700; font-size:24px; "
            "background:#0a0a0a; border:1px solid #333; border-radius:6px; padding:12px;"
        )
        root.addWidget(self.state_main)

        # Info box: tiempo / anterior / holds / timers
        info_box = QGroupBox("STATE MANAGER - CALIBRADO + OVERRIDE ATAQUE 80%")
        info_box.setStyleSheet("QGroupBox { font-weight: bold; color: #ddd; font-size:11px; }")
        info_lay = QGridLayout(info_box)
        info_lay.setContentsMargins(12, 10, 12, 10)
        info_lay.setHorizontalSpacing(18)
        info_lay.setVerticalSpacing(8)
        
        label_style = "font-size:11px; color:#aaa;"
        value_style = "color:#ddd; font-size:11px;"
        
        tiempo_lbl = QLabel("Tiempo:")
        tiempo_lbl.setStyleSheet(label_style)
        anterior_lbl = QLabel("Anterior:")
        anterior_lbl.setStyleSheet(label_style)
        holds_lbl = QLabel("Holds:")
        holds_lbl.setStyleSheet(label_style)
        timers_lbl = QLabel("Timers:")
        timers_lbl.setStyleSheet(label_style)
        
        info_lay.addWidget(tiempo_lbl, 0, 0)
        info_lay.addWidget(anterior_lbl, 1, 0)
        info_lay.addWidget(holds_lbl, 2, 0)
        info_lay.addWidget(timers_lbl, 3, 0)
        
        self.time_label = QLabel("—")
        self.prev_label = QLabel("—")
        self.holds_label = QLabel("—")
        self.timers_label = QLabel("—")
        
        for w in (self.time_label, self.prev_label, self.holds_label, self.timers_label):
            w.setStyleSheet(value_style)
        
        info_lay.addWidget(self.time_label, 0, 1)
        info_lay.addWidget(self.prev_label, 1, 1)
        info_lay.addWidget(self.holds_label, 2, 1)
        info_lay.addWidget(self.timers_label, 3, 1)
        
        root.addWidget(info_box)

        # Votación box
        vote_box = QGroupBox("ANALIZADORES - ESTADO ACTIVO")
        vote_box.setStyleSheet("QGroupBox { font-weight: bold; color: #ddd; font-size:11px; }")
        vb = QGridLayout(vote_box)
        vb.setContentsMargins(12, 10, 12, 10)
        vb.setHorizontalSpacing(12)
        vb.setVerticalSpacing(6)

        # Crear barras de progreso
        self.bar_bajada = self._make_responsive_bar()
        self.bar_base_golpe = self._make_responsive_bar()
        self.bar_ataque = self._make_responsive_bar()
        self.bar_brake = self._make_responsive_bar()
        
        bar_label_style = "font-size:11px; color:#ccc;"
        
        bajada_lbl = QLabel("Bajada:")
        bajada_lbl.setStyleSheet(bar_label_style)
        golpe_lbl = QLabel("Base Golpe:")
        golpe_lbl.setStyleSheet(bar_label_style)
        ataque_lbl = QLabel("Ataque:")
        ataque_lbl.setStyleSheet(bar_label_style)
        brake_lbl = QLabel("Brake:")
        brake_lbl.setStyleSheet(bar_label_style)
        
        vb.addWidget(bajada_lbl, 0, 0)
        vb.addWidget(self.bar_bajada, 0, 1)
        vb.addWidget(golpe_lbl, 1, 0)
        vb.addWidget(self.bar_base_golpe, 1, 1)
        vb.addWidget(ataque_lbl, 2, 0)
        vb.addWidget(self.bar_ataque, 2, 1)
        vb.addWidget(brake_lbl, 3, 0)
        vb.addWidget(self.bar_brake, 3, 1)

        # Contadores
        cnt_row = QHBoxLayout()
        self.lbl_transitions = QLabel("Trans: 0")
        self.lbl_transitions.setStyleSheet("color:#aaa; font-size:10px;")
        self.lbl_interrupts = QLabel("Int: 0")
        self.lbl_interrupts.setStyleSheet("color:#aaa; margin-left:16px; font-size:10px;")
        self.lbl_override = QLabel("Override ATQ: 0")
        self.lbl_override.setStyleSheet("color:#FF5722; margin-left:16px; font-weight:bold; font-size:10px;")
        
        cnt_row.addWidget(self.lbl_transitions)
        cnt_row.addWidget(self.lbl_interrupts)
        cnt_row.addWidget(self.lbl_override)
        cnt_row.addStretch()
        
        vb.addLayout(cnt_row, 4, 0, 1, 2)
        root.addWidget(vote_box)

        # MIL-Lite section (visible only when active)
        self._mil_box = QGroupBox("MUSIC INTELLIGENCE")
        self._mil_box.setStyleSheet("QGroupBox { font-weight: bold; color: #4fc3f7; font-size:11px; }")
        mil_lay = QGridLayout(self._mil_box)
        mil_lay.setContentsMargins(12, 10, 12, 10)
        mil_lay.setHorizontalSpacing(18)
        mil_lay.setVerticalSpacing(6)

        mil_lbl_style = "font-size:11px; color:#aaa;"
        mil_val_style = "color:#ddd; font-size:11px;"

        lbl_profile = QLabel("Perfil:")
        lbl_profile.setStyleSheet(mil_lbl_style)
        lbl_weights = QLabel("Pesos:")
        lbl_weights.setStyleSheet(mil_lbl_style)

        mil_lay.addWidget(lbl_profile, 0, 0)
        mil_lay.addWidget(lbl_weights, 1, 0)

        self._mil_profile_label = QLabel("--")
        self._mil_profile_label.setStyleSheet("color:#4fc3f7; font-weight:700; font-size:11px;")
        self._mil_weights_label = QLabel("--")
        self._mil_weights_label.setStyleSheet(mil_val_style)

        mil_lay.addWidget(self._mil_profile_label, 0, 1)
        mil_lay.addWidget(self._mil_weights_label, 1, 1)

        self._mil_box.setVisible(False)  # Oculto hasta que MIL-Lite este activo
        root.addWidget(self._mil_box)

        # Botones de control
        btn_row = QHBoxLayout()
        self.btn_reset = QPushButton("Reset")
        self.btn_force_bajada = QPushButton("→ Bajada")
        self.btn_force_golpe = QPushButton("→ Golpe")
        self.btn_responsive = QPushButton("Performance Info")
        
        btn_style = (
            "QPushButton { background:#181818; color:#ddd; border:1px solid #333; "
            "padding:8px; border-radius:4px; font-size:10px; } "
            "QPushButton:hover { background:#333; }"
        )
        
        for b in (self.btn_reset, self.btn_force_bajada, self.btn_force_golpe, self.btn_responsive):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(btn_style)
            btn_row.addWidget(b)
        
        root.addLayout(btn_row)

        # Conectar señales
        self.btn_reset.clicked.connect(self.reset_state)
        self.btn_force_bajada.clicked.connect(lambda: self.force_state("BAJADA"))
        self.btn_force_golpe.clicked.connect(lambda: self.force_state("BASE_GOLPE"))
        self.btn_responsive.clicked.connect(self.show_responsive_info)

        # Estilo general
        self.setStyleSheet(
            "QWidget { background:#151515; border:1px solid #333; border-radius:6px; } "
            "QLabel { color:#ccc; }"
        )

    def _make_responsive_bar(self):
        """Crea una barra de progreso responsive"""
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setFormat("%p%")
        bar.setTextVisible(True)
        bar.setMinimumHeight(24)
        bar.setMaximumHeight(26)
        bar.setStyleSheet("""
            QProgressBar {
                background:#131313; 
                border:1px solid #333; 
                border-radius:4px; 
                color:#ddd; 
                text-align: center;
                font-size:10px;
            }
            QProgressBar::chunk {
                background:#2ea043;
                border-radius:4px;
            }
        """)
        return bar

    def reset_state(self):
        """Reset del StateManager"""
        try:
            if hasattr(self.state_manager, 'reset'):
                self.state_manager.reset()
            print("[StateMonitorWidget] Estado reseteado")
        except Exception as e:
            print(f"[StateMonitorWidget] Error en reset_state: {e}")

    def force_state(self, state_name: str):
        """Fuerza un estado específico"""
        try:
            state_name = state_name.upper()
            if state_name not in ("BAJADA", "BASE_GOLPE", "ATAQUE", "BRAKE"):
                return
            self.state_manager.force_state = state_name
            print(f"[StateMonitorWidget] Forzando estado: {state_name}")
        except Exception as e:
            print(f"[StateMonitorWidget] Error en force_state: {e}")

    def show_responsive_info(self):
        """Muestra información de performance y optimización"""
        try:
            status = self.state_manager.get_status()
            perf = self.state_manager.get_performance_metrics()
            
            override_info = status.get('override_info', {})
            override_perf = perf.get('override', {})
            
            info_text = f"""INFORMACIÓN DE PERFORMANCE:

ESTADO ACTUAL: {status.get('current_state', 'UNKNOWN')}
Tiempo en Estado: {status.get('time_in_state', 0):.2f}s

OVERRIDE ATAQUE ≥80%:
• Contador 80%: {override_info.get('atk_over80_count', 0)}/{override_info.get('atk_min_frames', 2)} frames
• Threshold: {override_info.get('atk_threshold', 0.80):.2f}
• Total Overrides: {override_info.get('atk_overrides_total', 0)}
• Tiempo desde cambio: {override_perf.get('elapsed_since_change', 0):.2f}s

MÉTRICAS CALIBRADAS:
• Buffer Fill: {perf.get('buffer_fill', 0):.1%} ({status.get('responsiveness_info', {}).get('buffer_size', 0)}/{status.get('responsiveness_info', {}).get('buffer_capacity', 4)})
• Hold Activo: {'Sí' if perf.get('hold_active') else 'NO'}
• Cooldown Activo: {'Sí' if perf.get('cooldown_active') else 'NO'}
• Tiempo desde transición: {perf.get('time_since_transition', 0):.2f}s

PARÁMETROS:
• Min Hold: {perf.get('thresholds', {}).get('min_hold', 0):.2f}s
• Hysteresis: {perf.get('thresholds', {}).get('hysteresis', 0):.2f}
• Cooldown: {perf.get('thresholds', {}).get('cooldown', 0):.2f}s
• Min Confidence: {perf.get('thresholds', {}).get('min_confidence', 0):.2f}

BLOQUEOS:
• Por Hold: {perf.get('blocks', {}).get('hold', 0)}
• Por Cooldown: {perf.get('blocks', {}).get('cooldown', 0)}
• Por Confianza: {perf.get('blocks', {}).get('confidence', 0)}

TRANSICIONES:
• Total: {status.get('stats', {}).get('transitions', 0)}
• Interrupciones Ataque: {status.get('stats', {}).get('ataque_interrupts', 0)}
• Interrupciones Brake: {status.get('stats', {}).get('brake_interrupts', 0)}
"""
            
            msg = QMessageBox(self)
            msg.setWindowTitle("StateManager - Performance Metrics")
            msg.setText(info_text)
            msg.exec()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error mostrando info:\n{e}")

    def update_display(self):
        """Actualiza la UI"""
        try:
            st = self.state_manager.get_status() if self.state_manager else {}
        except Exception:
            st = {}

        # Estado principal
        cur = st.get("current_state", "BAJADA")
        
        try:
            t_elapsed = float(st.get("time_in_state", 0.0))
        except Exception:
            t_elapsed = 0.0

        # Colores por estado
        colors = {
            "BAJADA": "#4CAF50",
            "BASE_GOLPE": "#2196F3", 
            "ATAQUE": "#FF5722",
            "BRAKE": "#9C27B0",
        }
        color = colors.get(cur, "#cccccc")

        # Actualizar estado principal
        if cur != self._last_state or color != self._last_color:
            self._last_state, self._last_color = cur, color
            self.state_main.setText(cur)
            self.state_main.setStyleSheet(
                f"color:{color}; font-weight:700; font-size:24px; "
                "background:#0a0a0a; border:1px solid #333; "
                "border-radius:6px; padding:12px;"
            )

        # Tiempo
        t_txt = f"{t_elapsed:.1f}s"
        if t_txt != self._last_time:
            self._last_time = t_txt
            self.time_label.setText(t_txt)
        
        # Estado anterior
        prev = st.get("previous_state", "—")
        self.prev_label.setText(str(prev))

        # Holds
        holds = st.get("holds", {}) or {}
        try:
            min_hold = float(holds.get("min_hold", 0.0))
            rem_hold = float(holds.get("remaining", 0.0))
            self.holds_label.setText(f"min {min_hold:.1f}s | resta {rem_hold:.1f}s")
        except Exception:
            self.holds_label.setText("—")

        # Timers
        timers = st.get("timers", {}) or {}
        try:
            atq = float(timers.get("ataque", 0.0))
            brk = float(timers.get("brake", 0.0))
            if atq > 0.0 or brk > 0.0:
                self.timers_label.setText(f"ATQ {atq:.1f}s | BRK {brk:.1f}s")
            else:
                self.timers_label.setText("—")
        except Exception:
            self.timers_label.setText("—")

        # Votación
        scores = st.get("scores", {})
        
        if scores != self._last_scores:
            self._last_scores = scores.copy() if scores else {}
            
            def pct(key):
                try:
                    v = float(scores.get(key, 0.0))
                    return int(max(0.0, min(1.0, v)) * 100)
                except Exception:
                    return 0

            self.bar_bajada.setValue(pct("BAJADA"))
            self.bar_base_golpe.setValue(pct("BASE_GOLPE"))
            self.bar_ataque.setValue(pct("ATAQUE"))
            self.bar_brake.setValue(pct("BRAKE"))

        # Contadores
        stats = st.get("stats", {}) or {}
        
        try:
            trans = int(stats.get("transitions", 0))
        except Exception:
            trans = 0
        
        try:
            intr = int(stats.get("ataque_interrupts", 0)) + int(stats.get("brake_interrupts", 0))
        except Exception:
            intr = 0
        
        try:
            overrides = int(stats.get("ataque_overrides", 0))
        except Exception:
            overrides = 0

        trans_text = f"Trans: {trans}"
        if self._last_transitions != trans_text:
            self._last_transitions = trans_text
            self.lbl_transitions.setText(trans_text)
        
        intr_text = f"Int: {intr}"
        if self._last_interrupts != intr_text:
            self._last_interrupts = intr_text
            self.lbl_interrupts.setText(intr_text)
        
        self.lbl_override.setText(f"Override ATQ: {overrides}")

        # MIL-Lite section
        mil_profile = st.get("mil_profile", "")
        mil_weights = st.get("mil_weights", {})
        if mil_profile:
            if not self._mil_box.isVisible():
                self._mil_box.setVisible(True)
            profile_colors = {
                "CALM": "#4CAF50", "RHYTHMIC": "#2196F3",
                "INTENSE": "#FF5722", "NEUTRAL": "#aaa",
            }
            p_color = profile_colors.get(mil_profile, "#aaa")
            self._mil_profile_label.setText(mil_profile)
            self._mil_profile_label.setStyleSheet(f"color:{p_color}; font-weight:700; font-size:11px;")
            w = mil_weights
            self._mil_weights_label.setText(
                f"BJ:{w.get('bajada', 1):.2f}  BG:{w.get('base_golpe', 1):.2f}  "
                f"AT:{w.get('ataque', 1):.2f}  BR:{w.get('brake', 1):.2f}"
            )

    def closeEvent(self, event):
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        event.accept()