# analyzers/pulse_finder_wrapper.py — PULSE FINDER ANALYZER WRAPPER V10
# Wrapper profesional que adapta PulseFinder al sistema moderno de analizadores
# Expone .value, .score, .detected para compatibilidad con UI y flags

from typing import Optional, Dict, Any

try:
    from analyzers.pulse_finder import PulseFinder
    PULSE_FINDER_AVAILABLE = True
except ImportError:
    try:
        from pulse_finder import PulseFinder
        PULSE_FINDER_AVAILABLE = True
    except ImportError:
        PulseFinder = None
        PULSE_FINDER_AVAILABLE = False


class PulseFinderAnalyzer:
    """
    Wrapper profesional para PulseFinder legacy.

    Adapta la interfaz legacy a la interfaz moderna del sistema:
    - Expone .value, .score, .detected para UI
    - Mantiene compatibilidad con mark_analyzer_flags()
    - Forward transparente de .card para UI widgets
    - Compatible con process(block, sr)

    Uso:
        analyzer = PulseFinderAnalyzer()
        analyzer.process(block, sr)
        print(analyzer.value, analyzer.detected)
    """

    name = "PULSE FINDER"  # Nombre para UI y registro
    flag_name = "PULSE_FINDER"  # Flag para votación en BaseGolpe

    def __init__(self):
        """Inicializa el wrapper con PulseFinder legacy."""
        # Estado expuesto para UI y flags
        self.value: float = 0.0
        self.score: float = 0.0
        self.detected: bool = False

        # Instancia del analizador legacy
        self._pf: Optional[PulseFinder] = None
        self.card = None

        if PULSE_FINDER_AVAILABLE and PulseFinder is not None:
            try:
                self._pf = PulseFinder()
                self.card = self._pf.card  # Forward card para UI
            except Exception as e:
                print(f"[PulseFinderAnalyzer] Error instanciando PulseFinder: {e}")
                self._pf = None

    def process(self, block, sr: int) -> bool:
        """
        Procesa bloque de audio con PulseFinder legacy.

        Args:
            block: numpy array con samples de audio
            sr: sample rate

        Returns:
            bool: True si se detectó pulso constante
        """
        # Resetear estado
        self.detected = False
        self.value = 0.0
        self.score = 0.0

        if self._pf is None:
            return False

        try:
            # Ejecutar analizador legacy
            result = self._pf.process(block, sr)

            # Normalizar salida según tipo de resultado
            if isinstance(result, dict):
                # Si el legacy devuelve dict
                self.score = float(result.get("score", 0.0))
                self.value = float(result.get("value", self.score))
                self.detected = bool(result.get("detected", self.score > 0.5))
            elif isinstance(result, bool):
                # Si devuelve bool directo
                self.detected = result
                self.score = 1.0 if result else 0.0
                self.value = self.score
            elif isinstance(result, (int, float)):
                # Si devuelve número
                self.score = float(result)
                self.value = self.score
                self.detected = self.score > 0.5
            else:
                # Extraer estado interno del legacy
                self.value = float(getattr(self._pf, '_vu', 0.0))
                self.score = self.value
                self.detected = bool(getattr(self._pf, '_on', False))

            # Si no obtuvimos valor del resultado, intentar del estado interno
            if self.value == 0.0 and hasattr(self._pf, '_vu'):
                self.value = float(self._pf._vu)
                self.score = self.value

            # Detectar patrón constante desde estado interno
            if hasattr(self._pf, '_constant_pattern'):
                constant = bool(self._pf._constant_pattern)
                # Solo detected=True si hay patrón constante Y VU alto
                if constant and self.value > 0.4:
                    self.detected = True
                elif hasattr(self._pf, '_on'):
                    self.detected = bool(self._pf._on)

            return self.detected

        except Exception as e:
            # Silenciar errores para no interrumpir pipeline
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Retorna estado completo del analizador.

        Returns:
            Dict con value, score, detected, y estado interno
        """
        status = {
            "value": self.value,
            "score": self.score,
            "detected": self.detected,
            "available": self._pf is not None,
        }

        if self._pf is not None:
            status.update({
                "vu": float(getattr(self._pf, '_vu', 0.0)),
                "on": bool(getattr(self._pf, '_on', False)),
                "constant_pattern": bool(getattr(self._pf, '_constant_pattern', False)),
                "last_bpm": float(getattr(self._pf, '_last_bpm', 0.0)),
            })

        return status

    def __repr__(self) -> str:
        return f"<PulseFinderAnalyzer value={self.value:.2f} detected={self.detected}>"
