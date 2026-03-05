# state_inference.py — Combine all engines into state probabilities
#
# Produces probabilities for: BASE_GOLPE, BAJADA, ATAQUE, BRAKE
# Uses energy, beat confidence, transient density, drop state, and phrase position.
# All rules are deterministic (weighted sums + clamps).


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


class MusicStructureState:
    """Immutable snapshot of the music structure engine output."""

    __slots__ = (
        "tempo", "beat_phase", "beat_confidence",
        "energy_level", "energy_trend",
        "low_energy", "mid_energy", "high_energy",
        "transient_density", "transient_spike",
        "beat_index", "bar_index", "phrase_index",
        "phrase_position", "phrase_boundary_probability",
        "drop_state", "drop_confidence",
        "P_bajada", "P_base", "P_ataque", "P_brake",
        "suggested_state", "confidence",
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k, 0))

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__slots__}


class StateInference:
    """Deterministic state inference from all sub-engine outputs."""

    def infer(self, beat: dict, energy: dict, transient: dict,
              phrase: dict, drop: dict) -> MusicStructureState:
        """Combine sub-engine states into final MusicStructureState."""

        e_level = energy.get("energy_level", 0.0)
        e_trend = energy.get("energy_trend", "STABLE")
        lo = energy.get("low_energy", 0.0)
        mid = energy.get("mid_energy", 0.0)
        hi = energy.get("high_energy", 0.0)
        t_dens = transient.get("transient_density", 0.0)
        t_spike = transient.get("transient_spike", False)
        b_conf = beat.get("beat_confidence", 0.0)
        tempo = beat.get("tempo", 0.0)
        drop_state = drop.get("drop_state", "NONE")
        phrase_pos = phrase.get("phrase_position", 0.0)
        phrase_boundary = phrase.get("phrase_boundary_probability", 0.0)

        # --- Compute raw probabilities ---

        # P_bajada: low energy, falling trend, low transients
        p_bajada = 0.0
        if e_level < 0.15:
            p_bajada += 0.4
        elif e_level < 0.25:
            p_bajada += 0.2
        if e_trend == "FALLING":
            p_bajada += 0.25
        elif e_trend == "STABLE" and e_level < 0.2:
            p_bajada += 0.15
        if t_dens < 3.0:
            p_bajada += 0.2
        if b_conf < 0.3:
            p_bajada += 0.15  # no clear beat = calm
        p_bajada = _clamp01(p_bajada)

        # P_base: moderate energy, beat present, steady rhythm
        p_base = 0.0
        if 0.08 < e_level < 0.45:
            p_base += 0.3
        if b_conf > 0.3:
            p_base += 0.25
        if e_trend == "STABLE":
            p_base += 0.2
        if 3.0 < t_dens < 15.0:
            p_base += 0.15
        if drop_state == "NONE":
            p_base += 0.1
        p_base = _clamp01(p_base)

        # P_ataque: high energy, rising/high transients, drop context
        p_ataque = 0.0
        if e_level > 0.3:
            p_ataque += 0.25
        if e_level > 0.5:
            p_ataque += 0.15
        if e_trend == "RISING":
            p_ataque += 0.2
        if t_dens > 10.0:
            p_ataque += 0.15
        if t_spike:
            p_ataque += 0.15
        if drop_state in ("BUILD", "PRE_DROP", "DROP"):
            p_ataque += 0.2
        if b_conf > 0.5 and tempo > 120:
            p_ataque += 0.1  # fast + confident beat
        p_ataque = _clamp01(p_ataque)

        # P_brake: sudden energy drop, phrase boundary, post-drop
        p_brake = 0.0
        if e_trend == "FALLING" and e_level > 0.15:
            p_brake += 0.3
        if phrase_boundary > 0.5 and e_trend == "FALLING":
            p_brake += 0.2
        if t_dens < 2.0 and e_level > 0.1:
            p_brake += 0.15
        # Post-drop cooldown looks like brake
        if drop_state == "NONE" and e_trend == "FALLING":
            p_brake += 0.1
        p_brake = _clamp01(p_brake)

        # --- Normalize to soft distribution ---
        total = p_bajada + p_base + p_ataque + p_brake
        if total > 0:
            p_bajada /= total
            p_base /= total
            p_ataque /= total
            p_brake /= total

        # Suggested state = highest probability
        probs = {
            "BAJADA": p_bajada,
            "BASE_GOLPE": p_base,
            "ATAQUE": p_ataque,
            "BRAKE": p_brake,
        }
        suggested = max(probs, key=probs.get)

        # Confidence: margin of winner over second place
        sorted_probs = sorted(probs.values(), reverse=True)
        margin = sorted_probs[0] - sorted_probs[1] if len(sorted_probs) > 1 else sorted_probs[0]
        # Also factor in beat confidence
        confidence = _clamp01(margin + 0.3 * b_conf)

        return MusicStructureState(
            tempo=beat.get("tempo", 0.0),
            beat_phase=beat.get("beat_phase", 0.0),
            beat_confidence=b_conf,
            energy_level=e_level,
            energy_trend=e_trend,
            low_energy=lo,
            mid_energy=mid,
            high_energy=hi,
            transient_density=t_dens,
            transient_spike=t_spike,
            beat_index=phrase.get("beat_index", 0),
            bar_index=phrase.get("bar_index", 0),
            phrase_index=phrase.get("phrase_index", 0),
            phrase_position=phrase_pos,
            phrase_boundary_probability=phrase_boundary,
            drop_state=drop_state,
            drop_confidence=drop.get("drop_confidence", 0.0),
            P_bajada=round(p_bajada, 4),
            P_base=round(p_base, 4),
            P_ataque=round(p_ataque, 4),
            P_brake=round(p_brake, 4),
            suggested_state=suggested,
            confidence=round(confidence, 4),
        )
