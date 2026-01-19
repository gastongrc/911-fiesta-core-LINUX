"""
PresetService - Manejo de presets sin dependencias de Qt/UI
"""
import json
import os
import glob
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
from services.app_state import AppState


class PresetService:
    """
    Servicio para cargar/guardar presets de configuracion.
    Sin dependencias de Qt, puede ser usado por API.
    """

    def __init__(self, default_directory: str = "."):
        self.default_directory = default_directory

    def save_preset(
        self,
        path: str,
        data: dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Guardar preset en archivo JSON.

        Args:
            path: Ruta completa del archivo
            data: Dict con la configuracion a guardar

        Returns:
            (success: bool, error_message: Optional[str])
        """
        try:
            # Asegurar que termina en .json
            if not path.endswith('.json'):
                path += '.json'

            # Crear directorio si no existe
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # Guardar JSON con formato bonito
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            return (True, None)

        except Exception as e:
            return (False, str(e))

    def load_preset(
        self,
        path: str
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Cargar preset desde archivo JSON.

        Args:
            path: Ruta completa del archivo

        Returns:
            (data: Optional[dict], error_message: Optional[str])
        """
        try:
            if not os.path.exists(path):
                return (None, f"File not found: {path}")

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return (data, None)

        except json.JSONDecodeError as e:
            return (None, f"Invalid JSON: {e}")
        except Exception as e:
            return (None, str(e))

    def list_presets(
        self,
        directory: Optional[str] = None,
        pattern: str = "*.json"
    ) -> List[Dict[str, Any]]:
        """
        Listar archivos de preset en un directorio.

        Returns:
            Lista de dicts con: {
                "name": str,
                "path": str,
                "size": int,
                "modified": float (timestamp)
            }
        """
        if directory is None:
            directory = self.default_directory

        try:
            if not os.path.exists(directory):
                return []

            # Buscar archivos JSON
            search_pattern = os.path.join(directory, pattern)
            files = glob.glob(search_pattern)

            presets = []
            for file_path in files:
                try:
                    stat = os.stat(file_path)
                    presets.append({
                        "name": os.path.basename(file_path),
                        "path": file_path,
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
                except Exception:
                    continue

            # Ordenar por fecha de modificacion (mas reciente primero)
            presets.sort(key=lambda x: x["modified"], reverse=True)

            return presets

        except Exception as e:
            return []

    def validate_preset(self, data: dict) -> Tuple[bool, List[str]]:
        """
        Validar estructura de preset.

        Returns:
            (is_valid: bool, errors: List[str])
        """
        errors = []

        # Validar que sea un dict
        if not isinstance(data, dict):
            errors.append("Preset must be a dictionary")
            return (False, errors)

        # Validar keys opcionales conocidas
        known_keys = [
            "analyzers",
            "energy",
            "enabled",
            "net_panel",
            "version",
            "timestamp"
        ]

        # No hay keys obligatorias, pero validar formato si existen
        if "analyzers" in data and not isinstance(data["analyzers"], dict):
            errors.append("'analyzers' must be a dictionary")

        if "enabled" in data and not isinstance(data["enabled"], dict):
            errors.append("'enabled' must be a dictionary")

        if "net_panel" in data and not isinstance(data["net_panel"], dict):
            errors.append("'net_panel' must be a dictionary")

        return (len(errors) == 0, errors)

    def build_preset_data(
        self,
        app_state: AppState
    ) -> dict:
        """
        Construir dict de preset desde AppState actual.

        Returns:
            Dict con toda la configuracion serializable
        """
        import time

        data = {
            "version": app_state.version,
            "timestamp": time.time(),
            "analyzers": {},
            "enabled": {},
            "net_panel": {},
            "avolites": {}
        }

        # Extraer configs de modules
        if app_state.modules_by_state:
            for state_name, modules in app_state.modules_by_state.items():
                for module in modules:
                    try:
                        module_name = getattr(module, 'name', module.__class__.__name__)

                        # Guardar thresholds si existen
                        if hasattr(module, 'get_thresholds'):
                            thresholds = module.get_thresholds()
                            data["analyzers"][module_name] = {
                                "thresholds": thresholds
                            }

                        # Guardar enabled state
                        if hasattr(module, 'is_on'):
                            data["enabled"][module_name] = module.is_on()

                    except Exception:
                        continue

        # Extraer config de avolites
        if app_state.avolites:
            try:
                if hasattr(app_state.avolites, 'config_manager'):
                    config = app_state.avolites.config_manager.config
                    data["avolites"] = {
                        "console_ip": config.get("console_ip", ""),
                        "console_port": config.get("console_port", 4430),
                        "user_number_offset": config.get("user_number_offset", 169)
                    }
            except Exception:
                pass

        return data

    def apply_preset_data(
        self,
        data: dict,
        app_state: AppState
    ) -> Tuple[bool, List[str]]:
        """
        Aplicar preset data al AppState.

        NOTA: Esta funcion solo actualiza configuraciones,
        NO debe llamar a process() o update().

        Returns:
            (success: bool, errors: List[str])
        """
        errors = []

        try:
            # Aplicar thresholds a modulos
            if "analyzers" in data and app_state.modules_by_state:
                for state_name, modules in app_state.modules_by_state.items():
                    for module in modules:
                        try:
                            module_name = getattr(module, 'name', module.__class__.__name__)

                            if module_name in data["analyzers"]:
                                module_config = data["analyzers"][module_name]

                                # Actualizar thresholds si el modulo lo soporta
                                if "thresholds" in module_config and hasattr(module, 'set_thresholds'):
                                    module.set_thresholds(module_config["thresholds"])

                        except Exception as e:
                            errors.append(f"Error applying config to {module_name}: {e}")

            # Aplicar enabled flags
            if "enabled" in data and app_state.modules_by_state:
                for state_name, modules in app_state.modules_by_state.items():
                    for module in modules:
                        try:
                            module_name = getattr(module, 'name', module.__class__.__name__)

                            if module_name in data["enabled"]:
                                enabled = data["enabled"][module_name]

                                # Actualizar enabled state si el modulo lo soporta
                                if hasattr(module, 'set_enabled'):
                                    module.set_enabled(enabled)
                                elif hasattr(module, 'enabled'):
                                    module.enabled = enabled

                        except Exception as e:
                            errors.append(f"Error setting enabled for {module_name}: {e}")

            # Aplicar config de avolites
            if "avolites" in data and app_state.avolites:
                try:
                    avo_config = data["avolites"]

                    if "console_ip" in avo_config and "console_port" in avo_config:
                        if hasattr(app_state.avolites, 'set_console_ip'):
                            app_state.avolites.set_console_ip(
                                avo_config["console_ip"],
                                avo_config["console_port"]
                            )

                    if "user_number_offset" in avo_config:
                        if hasattr(app_state.avolites, 'set_cue_offset'):
                            app_state.avolites.set_cue_offset(avo_config["user_number_offset"])

                except Exception as e:
                    errors.append(f"Error applying avolites config: {e}")

            return (len(errors) == 0, errors)

        except Exception as e:
            errors.append(f"General error: {e}")
            return (False, errors)
