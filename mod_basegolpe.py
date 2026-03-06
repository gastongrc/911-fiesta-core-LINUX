# mod_basegolpe.py — BASE_GOLPE: EVENT-DRIVEN CANONICAL IMPLEMENTATION
# ===========================================================================
# BIBLIA 911 FIESTA — CANON ABSOLUTO
#
# NATURALEZA:
#   - BASE_GOLPE es EVENTO, NO es STATEFUL
#   - Dispara UNA VEZ al ENTRY y termina
#   - NO mantiene estado entre ticks
#   - NO reassert
#   - NO polling de is_active()
#   - NO cleanup propio (CueEngine lo hace via off_now_for_state)
#
# RANGOS CANÓNICOS:
#   FX_DIMMER (ALTA)  = C1, C2, C3, C51, C52, C53
#   FX_BEAM   (MEDIA) = C4, C5, C6, C54, C55, C56
#   FX_COLOR  (BAJA)  = C7, C8, C9, C57, C58, C59
#
# SELECCIÓN DE CUE:
#   - Determinística basada en timestamp (sin memoria)
#   - idx = int(time.time() * 10) % len(cues)
#
# C41 (DIMMER):
#   - SOLO FX_DIMMER puede solicitar dim_off
#   - En ENTRY: request_dim_off(REASON_FX_DIMMER)
#   - En EXIT: release_dim_off(REASON_FX_DIMMER)
#
# EXCLUSIONES:
#   - CueEngine maneja TODA exclusión via off_now_for_state()
#   - BASE_GOLPE NO mata otras familias
# ===========================================================================

import time
import numpy as np
from typing import Dict, Any, List, Optional, Set
from mod_control_dimmer import REASON_FX_DIMMER

# =========================================================================
# SETS CANÓNICOS POR SUBFAMILIA (VERIFICACIÓN DIRECTA POR CUE)
# =========================================================================
FX_DIMMER_CUES: Set[int] = {1, 2, 3, 51, 52, 53}    # ALTA - APAGA C41
FX_BEAM_CUES: Set[int] = {4, 5, 6, 54, 55, 56}       # MEDIA - NO TOCA C41
FX_COLOR_CUES: Set[int] = {7, 8, 9, 57, 58, 59}      # BAJA - NO TOCA C41


class BaseGolpeModule:
    """
    BASE_GOLPE: Disparador EVENT-DRIVEN canónico.

    - Dispara 1 cue al ENTRY basado en energía
    - NO mantiene estado musical
    - NO reassert
    - NO mata otras familias
    - Solo tracking técnico mínimo (_last_state_seen)

    V11: Voting system for kick detection
    - 10 flags from analyzer modules
    - get_votes() counts True flags for AutoClock feeding
    """

    # =========================================================================
    # RANGOS CANÓNICOS (BIBLIA 911 — NO MODIFICAR)
    # =========================================================================
    FAMILIES = {
        "FX_DIMMER": [1, 2, 3, 51, 52, 53],      # ALTA
        "FX_BEAM":   [4, 5, 6, 54, 55, 56],      # MEDIA
        "FX_COLOR":  [7, 8, 9, 57, 58, 59],      # BAJA
    }

    ENERGY_TO_FAMILY = {
        "ALTA":  "FX_DIMMER",
        "MEDIA": "FX_BEAM",
        "BAJA":  "FX_COLOR",
    }

    # V11: Mapping from analyzer flag_name to short flag key
    FLAG_NAME_MAP = {
        "YES_HITS": "hits",
        "ACCENT_CATCHER": "accent",
        "GROOVE_KEEPER": "groove",
        "PATTERN_LOCK": "pattern",
        "CADENCE_SPOTTER": "cadence",
        "FLOW_MONITOR": "flow",
        "DYNAMIC_PULSE": "dynamic",
        "PULSE_FINDER": "pulse",
        "RHYTHM_HIGHLIGHTER": "rhythm",
        "BURST_SHARPNESS": "burst",
    }

    def __init__(self, avolites, dimmer_ctrl, aux_manager=None):
        """
        Inicializa módulo BASE_GOLPE.

        Args:
            avolites: Controller Titan para fire_cue
            dimmer_ctrl: ControlDimmerModule para C41
            aux_manager: No usado (compatibilidad)
        """
        self.av = avolites
        self.dim = dimmer_ctrl

        # ÚNICO estado permitido: tracking técnico para detectar ENTRY
        self._last_state_seen: Optional[str] = None

        # Flag interno para saber si estamos en BASE_GOLPE (para release en EXIT)
        self._dimmer_requested: bool = False

        # Round-robin index per energy level (replaces timestamp-based selection)
        self._rr_index: Dict[str, int] = {
            "BAJA": 0,
            "MEDIA": 0,
            "ALTA": 0,
        }

        # V11: Voting flags for kick detection (10 flags)
        self.flags: Dict[str, bool] = {
            "hits": False,
            "accent": False,
            "groove": False,
            "pattern": False,
            "cadence": False,
            "flow": False,
            "dynamic": False,
            "pulse": False,
            "rhythm": False,
            "burst": False,
        }

        # V11: Reference to analyzer modules
        self._modules_golpe: List = []

        # V12: Kick pulse detector (real onset detection)
        self._kick_pulse = False          # One-shot pulse, consumed on read
        self._kick_last_ts = 0.0          # Last kick timestamp (monotonic)
        self._kick_baseline = 0.0         # Moving baseline for adaptive threshold
        self._kick_peak = 0.0             # Peak value for threshold calc
        self._kick_debounce_ms = 150.0    # Min interval between kicks (150ms = 400 BPM max)
        self._kick_threshold_k = 2.5      # Threshold = baseline + k * (peak - baseline)
        self._kick_baseline_alpha = 0.02  # Slow baseline adaptation
        self._kick_peak_alpha = 0.1       # Faster peak tracking

        print("[BASE_GOLPE] init (EVENT-DRIVEN canonical + V11 voting + V12 kick_pulse)")

    def _select_cue(self, cues: List[int], energy: str) -> int:
        """
        Selección round-robin con memoria por energía.
        Garantiza rotación C1→C2→C3→C1 sin repetición inmediata.

        Args:
            cues: Lista de cues disponibles
            energy: Nivel de energía para tracking RR

        Returns:
            int: Cue seleccionado
        """
        if not cues:
            return None
        idx = self._rr_index.get(energy, 0) % len(cues)
        cue = cues[idx]
        self._rr_index[energy] = idx + 1
        return cue

    def _get_family_for_energy(self, energy: str) -> str:
        """
        Mapea energía a nombre de familia.

        Args:
            energy: "ALTA", "MEDIA", "BAJA"

        Returns:
            str: "FX_DIMMER", "FX_BEAM", "FX_COLOR"
        """
        return self.ENERGY_TO_FAMILY.get(energy.upper(), "FX_BEAM")

    def _get_cues_for_energy(self, energy: str) -> List[int]:
        """
        Obtiene cues canónicos para una energía.

        Args:
            energy: "ALTA", "MEDIA", "BAJA"

        Returns:
            List[int]: Cues de la familia correspondiente
        """
        family = self._get_family_for_energy(energy)
        return self.FAMILIES.get(family, self.FAMILIES["FX_BEAM"])

    def run(self, state: str, energy: str) -> Optional[int]:
        """
        Ciclo principal — EVENT-DRIVEN.

        ENTRY a BASE_GOLPE:
            1. Mapear energía → familia
            2. Seleccionar cue (timestamp-based)
            3. Disparar cue
            4. Si FX_DIMMER: request_dim_off

        Dentro de BASE_GOLPE:
            - NO-OP (no reassert, no polling)

        EXIT de BASE_GOLPE:
            - release_dim_off si estaba activo

        Args:
            state: Estado actual del sistema
            energy: Energía actual

        Returns:
            Optional[int]: Cue disparado en ENTRY, None en otros casos
        """
        state = (state or "").upper()
        energy = (energy or "MEDIA").upper()

        # Normalizar energía
        energy = {"LOW": "BAJA", "MEDIUM": "MEDIA", "HIGH": "ALTA"}.get(energy, energy)
        if energy not in ("BAJA", "MEDIA", "ALTA"):
            energy = "MEDIA"

        # =====================================================================
        # DETECCIÓN DE TRANSICIONES
        # =====================================================================
        prev_state = self._last_state_seen
        self._last_state_seen = state

        is_entry = (prev_state != "BASE_GOLPE" and state == "BASE_GOLPE")
        is_exit = (prev_state == "BASE_GOLPE" and state != "BASE_GOLPE")

        # =====================================================================
        # EXIT: Solo release_dim_off
        # =====================================================================
        if is_exit:
            if self._dimmer_requested and self.dim is not None:
                self.dim.release_dim_off(REASON_FX_DIMMER)
                self._dimmer_requested = False
            return None

        # =====================================================================
        # NO ESTAMOS EN BASE_GOLPE: No hacer nada
        # =====================================================================
        if state != "BASE_GOLPE":
            return None

        # =====================================================================
        # ENTRY: Disparar evento
        # =====================================================================
        if is_entry:
            family = self._get_family_for_energy(energy)
            cues = self._get_cues_for_energy(energy)
            cue = self._select_cue(cues, energy)

            if cue is None:
                print(f"[BASE_GOLPE] ENTRY energy={energy} family={family} — NO CUES")
                return None

            # FIRE
            self.av.fire_cue(cue)
            print(f"[BASE_GOLPE] ENTRY energy={energy} family={family} cue=C{cue}")

            # C41: SOLO cues de FX_DIMMER solicitan dim_off (verificación directa)
            if cue in FX_DIMMER_CUES and self.dim is not None:
                self.dim.request_dim_off(REASON_FX_DIMMER)
                self._dimmer_requested = True
                print(f"[BASE_GOLPE] C41 OFF (cue C{cue} in FX_DIMMER_CUES)")

            return cue

        # =====================================================================
        # DENTRO DE BASE_GOLPE: NO-OP (event-driven, no reassert)
        # =====================================================================
        return None

    def get_active_cues(self) -> List[int]:
        """
        Retorna cues activos de BASE_GOLPE.
        Consulta estado real de Titan.
        """
        active = []
        for family_cues in self.FAMILIES.values():
            for cue in family_cues:
                try:
                    if self.av.is_active(cue):
                        active.append(cue)
                except:
                    pass
        return active

    def get_status(self) -> Dict[str, Any]:
        """Telemetría mínima."""
        return {
            "mode": "EVENT-DRIVEN",
            "last_state_seen": self._last_state_seen,
            "dimmer_requested": self._dimmer_requested,
            "families": {
                "FX_DIMMER": self.FAMILIES["FX_DIMMER"],
                "FX_BEAM": self.FAMILIES["FX_BEAM"],
                "FX_COLOR": self.FAMILIES["FX_COLOR"],
            },
            "active_cues": self.get_active_cues(),
        }

    def reset(self) -> None:
        """Reset del módulo."""
        if self._dimmer_requested and self.dim is not None:
            self.dim.release_dim_off(REASON_FX_DIMMER)

        self._last_state_seen = None
        self._dimmer_requested = False
        # Reset RR indices
        self._rr_index = {"BAJA": 0, "MEDIA": 0, "ALTA": 0}
        # V11: Reset flags
        for key in self.flags:
            self.flags[key] = False
        print("[BASE_GOLPE] Reset")

    # =========================================================================
    # V11: VOTING SYSTEM FOR KICK DETECTION
    # =========================================================================

    def set_modules_golpe(self, modules: List) -> None:
        """
        V11: Connect analyzer modules for flag reading.

        Args:
            modules: List of analyzer objects with .flag_name and .detected
        """
        self._modules_golpe = modules if modules else []

    def update_analyzer_flags(self) -> Dict[str, bool]:
        """
        V11: Update flags from connected analyzer modules.

        Reads .detected from each module and maps to our 10 flags.

        Returns:
            Dict[str, bool]: Current flag values
        """
        # Reset all flags
        for key in self.flags:
            self.flags[key] = False

        # Read from modules
        for module in self._modules_golpe:
            flag_name = getattr(module, 'flag_name', None)
            if flag_name and flag_name in self.FLAG_NAME_MAP:
                key = self.FLAG_NAME_MAP[flag_name]
                detected = getattr(module, 'detected', False)
                self.flags[key] = bool(detected)

        return self.flags.copy()

    def get_votes(self) -> int:
        """
        V11: Count how many flags are True.

        Returns:
            int: Number of True flags (0-10)
        """
        return sum(1 for v in self.flags.values() if v)

    # =========================================================================
    # V12: KICK PULSE DETECTOR (REAL ONSET FOR TAPTEMPO)
    # =========================================================================

    def process_audio(self, block: np.ndarray, sr: int) -> None:
        """
        V12: Process audio block to detect kick onsets.

        Uses low-band energy with adaptive threshold + debounce.
        Sets _kick_pulse=True on detection (one-shot, consumed by get_kick_pulse).

        Args:
            block: Audio samples (mono or stereo)
            sr: Sample rate
        """
        if block is None or len(block) == 0:
            return

        # Convert to mono float32
        x = np.asarray(block, dtype=np.float32)
        if x.ndim == 2:
            x = x.mean(axis=1)

        # Simple low-pass for kick detection (< 150Hz energy)
        # Use RMS of low-passed signal as energy measure
        # Quick low-pass: moving average with window ~150Hz cutoff
        win_samples = max(1, int(sr / 150))  # ~6.6ms at 44100Hz
        if len(x) < win_samples:
            return

        # Compute envelope: abs + smoothing
        env = np.abs(x)
        # Simple moving average for low-pass effect
        kernel = np.ones(win_samples) / win_samples
        if len(env) > len(kernel):
            env_smooth = np.convolve(env, kernel, mode='valid')
            energy = float(np.max(env_smooth))  # Peak energy in block
        else:
            energy = float(np.max(env))

        # Update adaptive baseline (slow)
        if self._kick_baseline == 0:
            self._kick_baseline = energy
        else:
            self._kick_baseline = (1 - self._kick_baseline_alpha) * self._kick_baseline + \
                                   self._kick_baseline_alpha * energy

        # Update peak tracker (faster)
        if energy > self._kick_peak:
            self._kick_peak = energy
        else:
            self._kick_peak = (1 - self._kick_peak_alpha) * self._kick_peak + \
                               self._kick_peak_alpha * energy

        # Adaptive threshold
        threshold = self._kick_baseline + self._kick_threshold_k * (self._kick_peak - self._kick_baseline)

        # Check for kick (energy above threshold)
        now = time.monotonic()
        dt_ms = (now - self._kick_last_ts) * 1000.0 if self._kick_last_ts > 0 else 9999

        if energy > threshold and dt_ms >= self._kick_debounce_ms:
            self._kick_pulse = True
            self._kick_last_ts = now
            print(f"[BaseGolpe] KICK_PULSE t={now:.3f} val={energy:.4f} thr={threshold:.4f}")

    def get_kick_pulse(self) -> bool:
        """
        V12: Get and consume kick pulse.

        Returns True once per detected kick, then resets to False.

        Returns:
            bool: True if kick was detected since last call
        """
        pulse = self._kick_pulse
        self._kick_pulse = False
        return pulse

    def get_kick_timestamp(self) -> float:
        """
        V12: Get timestamp of last kick pulse.

        Returns:
            float: Monotonic timestamp of last kick, 0 if none
        """
        return self._kick_last_ts
