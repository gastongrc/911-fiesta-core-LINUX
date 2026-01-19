"""
AnalyzerService - Read-only service para acceder al estado de analyzers
"""
from typing import Dict, List, Any, Optional
from services.app_state import AppState


class AnalyzerService:
    """
    Servicio para acceder al estado de los analyzers de forma estructurada.
    Read-only: NO modifica estado, solo lee.
    """

    def __init__(self, app_state: AppState):
        self.app_state = app_state

    def get_all_analyzers(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Obtener estado de TODOS los analyzers organizados por estado.

        Returns:
            {
                "BAJADA": [{...}, {...}],
                "BASE_GOLPE": [{...}, {...}],
                "ATAQUE": [{...}, {...}],
                "BRAKE": [{...}, {...}]
            }
        """
        result = {}

        if not self.app_state.modules_by_state:
            return {"BAJADA": [], "BASE_GOLPE": [], "ATAQUE": [], "BRAKE": []}

        for state_name, modules in self.app_state.modules_by_state.items():
            result[state_name] = []
            for module in modules:
                try:
                    analyzer_data = self._extract_analyzer_data(module)
                    if analyzer_data:
                        result[state_name].append(analyzer_data)
                except Exception as e:
                    # Skip modules que no se pueden leer
                    continue

        return result

    def get_analyzers_by_state(self, state: str) -> List[Dict[str, Any]]:
        """
        Obtener analyzers de un estado especifico.

        Args:
            state: "BAJADA" | "BASE_GOLPE" | "ATAQUE" | "BRAKE"
        """
        all_analyzers = self.get_all_analyzers()
        return all_analyzers.get(state, [])

    def get_analyzer_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Buscar analyzer por nombre en todos los estados.
        """
        all_analyzers = self.get_all_analyzers()
        for state_name, modules in all_analyzers.items():
            for module in modules:
                if module.get("name", "").lower() == name.lower():
                    return module
        return None

    def get_active_analyzers(self) -> List[Dict[str, Any]]:
        """
        Obtener solo analyzers activos (is_on() == True).
        """
        active = []
        all_analyzers = self.get_all_analyzers()
        for state_name, modules in all_analyzers.items():
            for module in modules:
                if module.get("active", False):
                    active.append(module)
        return active

    def get_matching_analyzers(self) -> List[Dict[str, Any]]:
        """
        Obtener solo analyzers con match activo.
        """
        matching = []
        all_analyzers = self.get_all_analyzers()
        for state_name, modules in all_analyzers.items():
            for module in modules:
                if module.get("match", False):
                    matching.append(module)
        return matching

    def get_energy_state(self) -> Dict[str, Any]:
        """
        Obtener estado del energy detector.

        Returns:
            {
                "level": str ("BAJA"|"MEDIA"|"ALTA"),
                "score": float,
                "raw_value": float,
                "threshold_low": float,
                "threshold_high": float
            }
        """
        if not self.app_state.energy_detector:
            return {
                "level": "BAJA",
                "score": 0.0,
                "raw_value": 0.0,
                "threshold_low": 0.0,
                "threshold_high": 1.0
            }

        try:
            energy_detector = self.app_state.energy_detector

            # Obtener nivel de energ�a (property o m�todo)
            level = "BAJA"
            if hasattr(energy_detector, 'get_energy'):
                level = energy_detector.get_energy()
            elif hasattr(energy_detector, 'energy'):
                level = energy_detector.energy

            # Obtener score
            score = 0.0
            if hasattr(energy_detector, 'get_score'):
                score = energy_detector.get_score()
            elif hasattr(energy_detector, 'score'):
                score = energy_detector.score

            # Obtener raw_value
            raw_value = 0.0
            if hasattr(energy_detector, 'raw_value'):
                raw_value = energy_detector.raw_value

            # Obtener thresholds
            threshold_low = 0.0
            threshold_high = 1.0
            if hasattr(energy_detector, 'threshold_low'):
                threshold_low = energy_detector.threshold_low
            if hasattr(energy_detector, 'threshold_high'):
                threshold_high = energy_detector.threshold_high

            return {
                "level": level,
                "score": score,
                "raw_value": raw_value,
                "threshold_low": threshold_low,
                "threshold_high": threshold_high
            }
        except Exception as e:
            # Fallback seguro
            return {
                "level": "BAJA",
                "score": 0.0,
                "raw_value": 0.0,
                "threshold_low": 0.0,
                "threshold_high": 1.0
            }

    def get_analyzer_stats(self) -> Dict[str, Any]:
        """
        Obtener estad�sticas generales de analyzers.

        Returns:
            {
                "total_count": int,
                "active_count": int,
                "matching_count": int,
                "by_state": {
                    "BAJADA": int,
                    "BASE_GOLPE": int,
                    ...
                }
            }
        """
        all_analyzers = self.get_all_analyzers()

        total_count = 0
        active_count = 0
        matching_count = 0
        by_state = {}

        for state_name, modules in all_analyzers.items():
            by_state[state_name] = len(modules)
            total_count += len(modules)

            for module in modules:
                if module.get("active", False):
                    active_count += 1
                if module.get("match", False):
                    matching_count += 1

        return {
            "total_count": total_count,
            "active_count": active_count,
            "matching_count": matching_count,
            "by_state": by_state
        }

    def _extract_analyzer_data(self, module) -> Optional[Dict[str, Any]]:
        """
        Extraer datos de un m�dulo analyzer.
        READ-ONLY: No modifica nada.
        """
        if not module:
            return None

        try:
            # Obtener name
            name = "Unknown"
            if hasattr(module, 'name'):
                name = module.name
            elif hasattr(module, '__class__'):
                name = module.__class__.__name__

            # Obtener type
            module_type = "analyzer"
            if hasattr(module, 'module_type'):
                module_type = module.module_type
            elif hasattr(module, 'card') and hasattr(module.card, 'name'):
                module_type = module.card.name

            # Obtener value
            value = 0.0
            if hasattr(module, 'get_value'):
                value = float(module.get_value())
            elif hasattr(module, 'value'):
                value = float(module.value)

            # Obtener thresholds
            thresholds = {"low": None, "medium": None, "high": None}
            if hasattr(module, 'get_thresholds'):
                th = module.get_thresholds()
                if isinstance(th, dict):
                    thresholds["low"] = th.get("low")
                    thresholds["medium"] = th.get("medium")
                    thresholds["high"] = th.get("high")

            # Obtener match
            match = False
            if hasattr(module, 'get_match'):
                match = bool(module.get_match())
            elif hasattr(module, 'match'):
                match = bool(module.match)

            # Obtener active
            active = False
            if hasattr(module, 'is_on'):
                active = bool(module.is_on())
            elif hasattr(module, 'active'):
                active = bool(module.active)

            return {
                "name": name,
                "type": module_type,
                "value": value,
                "thresholds": thresholds,
                "match": match,
                "active": active
            }
        except Exception as e:
            return None
