"""
HazeDetector PRO - Phase 6.4 Complete
Detector de humo/neblina con integración a FamilyManager
Estados: LOW, MEDIUM, HIGH
Cues: C64-C66 via canonical cue_map
"""
import cv2
import numpy as np
import time
import random
from typing import Optional, Dict, Any, TYPE_CHECKING

# Canonical cue map - single source of truth
from core.cues import FAMILIA_HAZE, HAZE_CUE_MAP

if TYPE_CHECKING:
    from core.cues import FamilyManager


class HazeDetector:
    """
    Detector PRO de haze integrado con FamilyManager.

    Responsabilidades:
    - Detectar densidad de humo (LOW, MEDIUM, HIGH)
    - Calcular baseline y contraste
    - Disparar cues según nivel detectado via FamilyManager
    - Cooldown configurable (1-5 min)
    - Duración de fire configurable (1-10s)
    - Estados: READY, SHOOTING, COOLDOWN

    Integración FamilyManager (canonical cues C64-C66):
    - Dispara C64 cuando nivel LOW
    - Dispara C65 cuando nivel MEDIUM
    - Dispara C66 cuando nivel HIGH
    """

    def __init__(self, config, vision_state, cue_engine=None):
        """
        Inicializa el detector de haze.

        Args:
            config (VisionConfig): Configuración del sistema
            vision_state (VisionState): Estado compartido
            cue_engine (CueEngine, optional): Motor de cues (legacy)
        """
        self.config = config
        self.vision_state = vision_state
        self.cue_engine = cue_engine

        # FamilyManager for canonical cue firing
        self._family_manager: Optional["FamilyManager"] = None

        # Cargar configuración
        haze_config = config.get_haze_config()
        self.threshold_low = haze_config.get("threshold_low", 30)
        self.threshold_med = haze_config.get("threshold_med", 50)
        self.threshold_high = haze_config.get("threshold_high", 70)
        self.baseline_frames = haze_config.get("baseline_frames", 30)
        self.smooth_factor = haze_config.get("smooth_factor", 0.2)
        self.cooldown_min = haze_config.get("cooldown_min", 60)
        self.cooldown_max = haze_config.get("cooldown_max", 300)
        self.fire_duration = haze_config.get("fire_duration", 3.0)
        self.target_density = haze_config.get("target_density", "LOW")

        # Estado interno
        self.baseline_contrast = None
        self.baseline_samples = []
        self.contrast_history = []
        self.haze_level = 0.0
        self.haze_state = "NONE"  # NONE, LOW, MEDIUM, HIGH
        self.frame_count = 0

        # Control de disparos - REFIRE FIX (Phase 6.12)
        self.last_fire_time = 0.0
        self.cooldown_until = 0.0
        self.current_cue = None
        self._last_fire_state = None  # Estado cuando se disparó (debug)
        self._armed = True  # Puede disparar (se re-arma cuando baja a NONE)

        # ON/OFF cycle control (Phase 6.13)
        self._fire_end_time = 0.0  # Cuándo hacer OFF (0 = no hay cue activo)
        self._cue_is_on = False  # True si hay cue activo que necesita OFF

        # Refire config
        self._refire_mode = haze_config.get("refire_mode", "edge_or_refire")
        self._refire_min_s = haze_config.get("refire_min_s", 60.0)
        self._debug_enabled = haze_config.get("debug_log", False)

        print("[HazeDetector] Inicializado con thresholds LOW={}, MED={}, HIGH={}, target_density={}".format(
            self.threshold_low, self.threshold_med, self.threshold_high, self.target_density))

    def process_frame(self, frame) -> Dict[str, Any]:
        """
        Procesa un frame de cámara para detectar haze.

        Args:
            frame: Frame de OpenCV (numpy array BGR)

        Returns:
            dict: Estado de detección
        """
        if frame is None:
            return self.get_state()

        # Check if active cue needs to be turned OFF (timer expired)
        self._check_fire_off()

        # Solo procesar si está habilitado
        if not self.vision_state.is_haze_ready() and self.vision_state.haze_enabled:
            # Actualizar estado de cooldown
            self._update_cooldown_status()
            return self.get_state()

        # 1. Conversión a escala de grises
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # 2. Cálculo de contraste (desviación estándar)
        # Phase 6.10: Use cv2.meanStdDev instead of np.std (thread-safe, no BLAS)
        _, stddev = cv2.meanStdDev(gray)
        contrast = float(stddev[0][0])

        # 3. Baseline dinámico (aprendizaje inicial)
        if self.baseline_contrast is None:
            self.baseline_samples.append(contrast)

            if len(self.baseline_samples) >= self.baseline_frames:
                self.baseline_contrast = np.mean(self.baseline_samples)
                self.vision_state.update_haze(baseline=self.baseline_contrast)
                print(f"[HazeDetector] Baseline establecido: {self.baseline_contrast:.2f}")
                self.baseline_samples = []
            else:
                # Aún aprendiendo
                return self.get_state()

        # 4. Suavizado temporal (EMA)
        if self.contrast_history:
            smoothed_contrast = (
                self.smooth_factor * contrast +
                (1 - self.smooth_factor) * self.contrast_history[-1]
            )
        else:
            smoothed_contrast = contrast

        self.contrast_history.append(smoothed_contrast)
        if len(self.contrast_history) > 100:
            self.contrast_history.pop(0)

        # 5. Cálculo de nivel de haze (0-100)
        if self.baseline_contrast > 0:
            contrast_reduction = (
                (self.baseline_contrast - smoothed_contrast) / self.baseline_contrast
            )
            self.haze_level = np.clip(contrast_reduction * 200, 0, 100)
        else:
            self.haze_level = 0.0

        # 6. Determinar estado (LOW, MEDIUM, HIGH)
        old_state = self.haze_state
        if self.haze_level >= self.threshold_high:
            self.haze_state = "HIGH"
        elif self.haze_level >= self.threshold_med:
            self.haze_state = "MEDIUM"
        elif self.haze_level >= self.threshold_low:
            self.haze_state = "LOW"
        else:
            self.haze_state = "NONE"

        state_changed = (old_state != self.haze_state)

        # Re-arm cuando baja a NONE (permite disparar de nuevo cuando suba)
        if self.haze_state == "NONE" and old_state != "NONE":
            self._armed = True
            if self._debug_enabled:
                print(f"[HAZE] RE-ARMED: dropped to NONE from {old_state}")

        # 7. Actualizar VisionState
        self.vision_state.update_haze(
            level=self.haze_level,
            baseline=self.baseline_contrast,
            contrast=smoothed_contrast,
            state=self.haze_state
        )

        # 8. Disparar cue si aplica (transición o refire)
        self._trigger_cue_if_needed(state_changed, old_state)

        # 9. Actualizar estado de UI
        self._update_cooldown_status()

        self.frame_count += 1
        return self.get_state()

    def _trigger_cue_if_needed(self, state_changed: bool, old_state: str):
        """
        Dispara cue basado en transiciones de estado y/o refire periódico.

        Lógica (Phase 6.12 REFIRE FIX):
        - edge_only: Solo dispara en transición NONE→LOW/MED/HIGH
        - edge_or_refire: Dispara en transición O si pasó refire_min_s

        Args:
            state_changed: True si el estado cambió
            old_state: Estado anterior
        """
        now = time.time()

        # === CONDICIONES DE NO-DISPARO ===
        if not self.vision_state.haze_enabled:
            return

        if self.haze_state == "NONE":
            return

        # Verificar cooldown
        cooldown_remaining = self.cooldown_until - now
        if cooldown_remaining > 0:
            if self._debug_enabled and state_changed:
                print(f"[HAZE] NO FIRE: cooldown {cooldown_remaining:.1f}s")
            return

        # Verificar target_density
        if not self._meets_target_density():
            if self._debug_enabled and state_changed:
                print(f"[HAZE] NO FIRE: {self.haze_state} < target {self.target_density}")
            return

        # === DECISIÓN DE DISPARO ===
        should_fire = False
        fire_reason = ""

        # Caso 1: Transición desde NONE (edge trigger)
        if state_changed and old_state == "NONE" and self._armed:
            should_fire = True
            fire_reason = f"EDGE: {old_state}→{self.haze_state}"
            self._armed = False

        # Caso 2: Transición entre niveles activos
        elif state_changed and old_state != "NONE":
            should_fire = True
            fire_reason = f"LEVEL: {old_state}→{self.haze_state}"

        # Caso 3: Refire periódico
        elif self._refire_mode == "edge_or_refire":
            time_since = now - self.last_fire_time if self.last_fire_time > 0 else float('inf')
            if time_since >= self._refire_min_s:
                should_fire = True
                fire_reason = f"REFIRE: {time_since:.0f}s"

        if not should_fire:
            if self._debug_enabled and state_changed:
                print(f"[HAZE] NO FIRE: armed={self._armed}, mode={self._refire_mode}")
            return

        # === DISPARAR ===
        cue_to_fire = HAZE_CUE_MAP.get(self.haze_state)
        if not cue_to_fire:
            return

        if self._family_manager:
            try:
                # === ON: Fire the cue ===
                print(f"[VISION_HAZE] ON C{cue_to_fire} ({self.haze_state}) {fire_reason}")
                self._family_manager.activate_state(FAMILIA_HAZE, self.haze_state)

                self.current_cue = cue_to_fire
                self.last_fire_time = now
                self._last_fire_state = self.haze_state
                self.vision_state.set_haze_fire()

                # Schedule OFF after fire_duration
                self._fire_end_time = now + self.fire_duration
                self._cue_is_on = True
                print(f"[VISION_HAZE] Scheduled OFF in {self.fire_duration:.1f}s")

                cooldown_duration = random.uniform(self.cooldown_min, self.cooldown_max)
                self.cooldown_until = now + cooldown_duration
                self.vision_state.set_haze_cooldown(cooldown_duration)

                print(f"[HazeDetector] Cooldown: {cooldown_duration:.1f}s")
            except Exception as e:
                print(f"[HazeDetector] ERROR: {e}")
        else:
            if self._debug_enabled:
                print("[HAZE] NO FIRE: FamilyManager not connected")

    def _check_fire_off(self):
        """
        Verifica si el timer de fire expiró y apaga el cue (OFF).

        Ciclo ON→OFF:
        1. ON: _trigger_cue_if_needed() dispara cue y setea _fire_end_time
        2. OFF: Cuando now > _fire_end_time, llama deactivate_family()

        Esto permite que el cue se apague automáticamente después de fire_duration,
        habilitando refires posteriores sin bloqueo por dedupe.
        """
        if not self._cue_is_on:
            return

        now = time.time()
        if now < self._fire_end_time:
            return

        # Timer expired - turn OFF
        if self._family_manager:
            cue_off = self.current_cue
            print(f"[VISION_HAZE] OFF C{cue_off} (timer expired after {self.fire_duration:.1f}s)")
            try:
                self._family_manager.deactivate_family(FAMILIA_HAZE)
            except Exception as e:
                print(f"[VISION_HAZE] OFF ERROR: {e}")

        # Reset state
        self._cue_is_on = False
        self._fire_end_time = 0.0

    def _meets_target_density(self) -> bool:
        """
        Verifica si el nivel actual cumple o supera el target_density.
        Orden: NONE < LOW < MEDIUM < HIGH

        Returns:
            bool: True si nivel_actual >= target_density
        """
        density_order = ["NONE", "LOW", "MEDIUM", "HIGH"]

        try:
            current_level = density_order.index(self.haze_state)
            target_level = density_order.index(self.target_density)
            return current_level >= target_level
        except ValueError:
            # Si algún valor es inválido, permitir disparo por seguridad
            return True

    def _update_cooldown_status(self):
        """Actualiza el estado de UI (READY/SHOOTING/COOLDOWN)."""
        now = time.time()

        # SHOOTING: durante fire_duration después de disparar
        if now - self.last_fire_time < self.fire_duration:
            self.vision_state.set_haze_status("SHOOTING")
        # COOLDOWN: durante cooldown
        elif now < self.cooldown_until:
            self.vision_state.set_haze_status("COOLDOWN")
        # READY: listo para disparar
        else:
            self.vision_state.set_haze_status("READY")

    def get_state(self) -> Dict[str, Any]:
        """
        Retorna el estado actual del detector.

        Returns:
            dict: Estado completo para integración
        """
        return {
            "level": float(self.haze_level),
            "baseline": float(self.baseline_contrast) if self.baseline_contrast else 0.0,
            "contrast": float(self.contrast_history[-1]) if self.contrast_history else 0.0,
            "state": self.haze_state,
            "status": self.vision_state.haze_status,
            "cooldown_remaining": max(0, self.cooldown_until - time.time()),
            "last_fire": self.last_fire_time,
            "current_cue": self.current_cue,
            "learning": self.baseline_contrast is None,
            "frame_count": self.frame_count,
            "target_density": self.target_density,
        }

    def reset_baseline(self):
        """Resetea el baseline para recalibración."""
        self.baseline_contrast = None
        self.baseline_samples = []
        self.contrast_history = []
        print("[HazeDetector] Baseline reseteado, iniciando recalibración...")

    def set_cue_engine(self, cue_engine):
        """Establece el CueEngine para disparar cues (legacy)."""
        self.cue_engine = cue_engine
        print("[HazeDetector] CueEngine conectado (legacy)")

    def set_family_manager(self, family_manager: "FamilyManager"):
        """
        Establece el FamilyManager para disparar cues canónicos.

        Args:
            family_manager: FamilyManager para activación exclusiva
        """
        self._family_manager = family_manager
        print("[HazeDetector] FamilyManager conectado (canonical cues C64-C66)")

    def disable_by_mode(self):
        """
        Desactiva el detector por modo calendario.
        Resetea estado y limpia cooldown.
        """
        self.haze_state = "DISABLED"
        self.haze_level = 0.0
        self.vision_state.update_haze(level=0.0, state="DISABLED")

    def set_enabled(self, enabled: bool, persist: bool = None):
        """
        Habilita/deshabilita el detector.

        Args:
            enabled: True para habilitar, False para deshabilitar
            persist: Ignored (handled by VisionManager). Kept for API compatibility.
        """
        print(f"[HazeDetector] set_enabled({enabled}) called")
        self.vision_state.set_haze_enabled(enabled)
        print(f"[HazeDetector] vision_state.haze_enabled is now: {self.vision_state.haze_enabled}")
        if not enabled:
            self.disable_by_mode()

    def _test_fire(self, cue_id: int = 64, force_fire: bool = False) -> Dict[str, Any]:
        """
        Diagnóstico completo del pipeline de FIRE para verificar wiring.

        Verifica todos los puntos de conexión:
        1. HazeDetector → FamilyManager
        2. FamilyManager → CueEngine
        3. CueEngine → AvolitesBridge
        4. AvolitesBridge → TitanQueue
        5. TitanQueue → TitanTransport
        6. TitanTransport → Titan HTTP API

        Args:
            cue_id: ID del cue a verificar (default C64 = HAZE LOW)
            force_fire: Si True, fuerza un disparo real de prueba

        Returns:
            dict: Estado de cada punto del pipeline
        """
        print("\n" + "=" * 60)
        print("[HazeDetector] _test_fire() DIAGNOSTIC")
        print("=" * 60)

        result = {
            "cue_id": cue_id,
            "timestamp": time.time(),
            "connections": {},
            "ready_to_fire": False,
            "force_fire_result": None,
        }

        # 1. Check FamilyManager connection
        print(f"\n[1] HazeDetector → FamilyManager")
        if self._family_manager:
            print(f"    ✓ FamilyManager CONNECTED")
            result["connections"]["family_manager"] = True
        else:
            print(f"    ✗ FamilyManager NOT CONNECTED")
            result["connections"]["family_manager"] = False
            return result

        # 2. Check CueEngine in FamilyManager
        print(f"\n[2] FamilyManager → CueEngine")
        cue_engine = getattr(self._family_manager, "_cue_engine", None)
        if cue_engine:
            print(f"    ✓ CueEngine CONNECTED")
            result["connections"]["cue_engine"] = True
        else:
            print(f"    ⚠ CueEngine NOT CONNECTED (will use direct Avolites)")
            result["connections"]["cue_engine"] = False

        # 3. Check AvolitesBridge in CueEngine (or FamilyManager)
        print(f"\n[3] CueEngine/FamilyManager → AvolitesBridge")
        avolites = None
        if cue_engine:
            avolites = getattr(cue_engine, "av", None)
        if not avolites:
            avolites = getattr(self._family_manager, "_av", None)
        if avolites:
            print(f"    ✓ AvolitesBridge CONNECTED")
            result["connections"]["avolites"] = True
        else:
            print(f"    ✗ AvolitesBridge NOT CONNECTED")
            result["connections"]["avolites"] = False
            return result

        # 4. Check TitanQueue in AvolitesBridge
        print(f"\n[4] AvolitesBridge → TitanQueue")
        titan_queue = getattr(avolites, "_titan_queue", None)
        if titan_queue:
            print(f"    ✓ TitanQueue CONNECTED (qlen={titan_queue._queue.qsize() if hasattr(titan_queue, '_queue') else '?'})")
            result["connections"]["titan_queue"] = True
        else:
            print(f"    ✗ TitanQueue NOT CONNECTED")
            result["connections"]["titan_queue"] = False
            return result

        # 5. Check TitanTransport in TitanQueue
        print(f"\n[5] TitanQueue → TitanTransport")
        titan_transport = getattr(titan_queue, "_transport", None)
        if titan_transport:
            print(f"    ✓ TitanTransport CONNECTED")
            result["connections"]["titan_transport"] = True
        else:
            print(f"    ✗ TitanTransport NOT CONNECTED")
            result["connections"]["titan_transport"] = False
            return result

        # 6. Check Titan HTTP connectivity
        print(f"\n[6] TitanTransport → Titan HTTP API")
        base_url = getattr(titan_transport, "_base_url", None)
        if base_url:
            print(f"    ✓ Titan URL configured: {base_url}")
            result["connections"]["titan_url"] = base_url
        else:
            print(f"    ⚠ Titan URL not configured")
            result["connections"]["titan_url"] = None

        # Summary
        all_connected = all([
            result["connections"].get("family_manager"),
            result["connections"].get("avolites"),
            result["connections"].get("titan_queue"),
            result["connections"].get("titan_transport"),
        ])
        result["ready_to_fire"] = all_connected

        print(f"\n{'=' * 60}")
        print(f"[RESULT] Pipeline ready: {all_connected}")
        print(f"{'=' * 60}")

        # Force fire if requested
        if force_fire and all_connected:
            print(f"\n[FORCE FIRE] Attempting C{cue_id}...")
            print("[Expected log chain:]")
            print("  → [FamilyManager] FIRE C{cue_id}")
            print("  → [CueEngine] *** FIRE C{cue_id} ***")
            print("  → [AvolitesBridge] FIRE cue={cue_id}")
            print("  → [TitanQueue] ENQUEUE FIRE cue={cue_id}")
            print("  → [TitanTransport] SEND FIRE cue={cue_id}")
            print("")

            try:
                success = self._family_manager.activate_state(
                    FAMILIA_HAZE, "LOW", force=True, source="test_fire"
                )
                result["force_fire_result"] = success
                print(f"\n[FORCE FIRE] Result: {'SUCCESS' if success else 'FAILED'}")
            except Exception as e:
                result["force_fire_result"] = False
                result["force_fire_error"] = str(e)
                print(f"\n[FORCE FIRE] ERROR: {e}")

        print("")
        return result
