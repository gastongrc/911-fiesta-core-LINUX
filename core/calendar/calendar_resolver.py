# core/calendar/calendar_resolver.py
"""
CalendarResolver v6.4 - Resolucion pasiva de horarios.

Lee calendar.json y determina:
- Bloque activo segun hora actual
- Proximo cambio de modo
- Tiempo restante en bloque actual

v6.4 NUEVO: Soporte para bloques compuestos
- base_mode: Modo canónico obligatorio
- actions: Lista de acciones paralelas (0-5)

IMPORTANTE: Esta logica es 100% PASIVA
- NO ejecuta cues
- NO fuerza cambios
- NO bloquea el engine
- Solo resuelve estado basado en tiempo
"""

import json
import os
import re
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any, List, Tuple

from .calendar_state import ScheduleBlock, VALID_ACTIONS, MAX_ACTIONS_PER_BLOCK


# Regex para validar formato HH:MM
TIME_FORMAT_REGEX = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


# Mapeo de dias en ingles a indices Python (0=lunes)
DAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6
}

# Mapeo inverso
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class CalendarResolver:
    """
    Resuelve el bloque de horario activo basado en la hora actual.

    Lee el archivo calendar.json y determina que modo debe estar
    activo en cualquier momento dado.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Inicializa el resolver.

        Args:
            config_path: Ruta al archivo calendar.json (opcional)
        """
        if config_path is None:
            # Buscar en el mismo directorio que este archivo
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "calendar.json")

        self._config_path = config_path
        self._schedule: Dict[str, List[Dict]] = {}
        self._auto_mode_enabled = True
        self._last_load_time: Optional[datetime] = None

        # Cargar schedule inicial
        self._load_schedule()

    def _load_schedule(self) -> bool:
        """
        Carga el schedule desde calendar.json.

        Returns:
            True si cargo correctamente, False si hubo error
        """
        try:
            if not os.path.exists(self._config_path):
                print(f"[CalendarResolver] WARN: No existe {self._config_path}")
                self._schedule = {}
                return False

            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            raw_schedule = data.get("week", {})

            # Validar y filtrar bloques
            self._schedule = self._validate_and_filter_schedule(raw_schedule)
            self._last_load_time = datetime.now()

            total_blocks = sum(len(blocks) for blocks in self._schedule.values())
            print(f"[CalendarResolver] Schedule cargado: {len(self._schedule)} dias, {total_blocks} bloques")
            return True

        except Exception as e:
            print(f"[CalendarResolver] ERROR cargando schedule: {e}")
            self._schedule = {}
            return False

    def _validate_time_format(self, time_str: str) -> bool:
        """
        Valida que el string tenga formato HH:MM válido.

        Args:
            time_str: String a validar

        Returns:
            True si es válido
        """
        if not isinstance(time_str, str):
            return False
        return TIME_FORMAT_REGEX.match(time_str) is not None

    def _validate_block(self, block: Dict, day: str, index: int) -> bool:
        """
        Valida un bloque individual.

        Args:
            block: Diccionario del bloque
            day: Nombre del día
            index: Índice del bloque en el día

        Returns:
            True si el bloque es válido
        """
        # Validar que tenga from/to
        if "from" not in block or "to" not in block:
            print(f"[CalendarResolver] WARN: {day}[{index}] sin from/to, ignorado")
            return False

        # Validar formato HH:MM
        if not self._validate_time_format(block["from"]):
            print(f"[CalendarResolver] WARN: {day}[{index}] from='{block['from']}' formato inválido, ignorado")
            return False

        if not self._validate_time_format(block["to"]):
            print(f"[CalendarResolver] WARN: {day}[{index}] to='{block['to']}' formato inválido, ignorado")
            return False

        # Validar que tenga mode o actions
        has_mode = "mode" in block and block["mode"]
        has_actions = "actions" in block and block["actions"]

        if not has_mode and not has_actions:
            print(f"[CalendarResolver] WARN: {day}[{index}] sin mode ni actions, ignorado")
            return False

        # Validar max acciones
        if has_actions and len(block["actions"]) > MAX_ACTIONS_PER_BLOCK:
            print(f"[CalendarResolver] WARN: {day}[{index}] tiene {len(block['actions'])} actions (max {MAX_ACTIONS_PER_BLOCK})")

        return True

    def _detect_overlaps(self, blocks: List[Dict], day: str) -> None:
        """
        Detecta y loguea solapamientos entre bloques del mismo día.

        Args:
            blocks: Lista de bloques válidos
            day: Nombre del día
        """
        for i, block1 in enumerate(blocks):
            for j, block2 in enumerate(blocks):
                if i >= j:
                    continue

                from1 = self._time_to_minutes(self._parse_time(block1["from"]))
                to1 = self._time_to_minutes(self._parse_time(block1["to"]))
                from2 = self._time_to_minutes(self._parse_time(block2["from"]))
                to2 = self._time_to_minutes(self._parse_time(block2["to"]))

                # Caso normal (no cruza medianoche)
                if from1 < to1 and from2 < to2:
                    if not (to1 <= from2 or to2 <= from1):
                        print(f"[CalendarResolver] WARN: {day} bloques {i+1} y {j+1} se solapan")

    def _validate_and_filter_schedule(self, raw_schedule: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """
        Valida el schedule completo y filtra bloques inválidos.

        Args:
            raw_schedule: Schedule sin validar

        Returns:
            Schedule con solo bloques válidos
        """
        validated = {}

        for day in DAY_NAMES:
            raw_blocks = raw_schedule.get(day, [])
            valid_blocks = []

            for i, block in enumerate(raw_blocks):
                if self._validate_block(block, day, i):
                    valid_blocks.append(block)

            if valid_blocks:
                # Detectar solapamientos (solo log, no filtra)
                self._detect_overlaps(valid_blocks, day)
                validated[day] = valid_blocks

        return validated

    def reload_schedule(self) -> bool:
        """
        Recarga el schedule desde disco.

        Returns:
            True si recargo correctamente
        """
        return self._load_schedule()

    def _parse_time(self, time_str: str) -> time:
        """
        Parsea un string de tiempo HH:MM a objeto time.

        Args:
            time_str: Tiempo en formato "HH:MM"

        Returns:
            Objeto time
        """
        parts = time_str.split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]))

    def _time_to_minutes(self, t: time) -> int:
        """Convierte time a minutos desde medianoche"""
        return t.hour * 60 + t.minute

    def _is_time_in_range(self, current: time, from_time: time, to_time: time) -> bool:
        """
        Verifica si una hora esta dentro de un rango.

        Maneja cruces de medianoche (ej: 22:00 - 05:00)

        Args:
            current: Hora actual
            from_time: Hora de inicio
            to_time: Hora de fin

        Returns:
            True si current esta en el rango [from_time, to_time)
        """
        current_mins = self._time_to_minutes(current)
        from_mins = self._time_to_minutes(from_time)
        to_mins = self._time_to_minutes(to_time)

        # Caso normal: no cruza medianoche
        if from_mins < to_mins:
            return from_mins <= current_mins < to_mins

        # Caso cruce de medianoche (ej: 22:00 - 05:00)
        # El rango es [from_mins, 24:00) OR [00:00, to_mins)
        return current_mins >= from_mins or current_mins < to_mins

    def _derive_mode_from_actions(self, actions: List[str]) -> str:
        """
        Deriva un modo base a partir de la lista de acciones v6.4.

        Mapeo de prioridad:
        - audio_911 presente → BOLICHE_DESARROLLO
        - vision_artista presente → ARTISTA
        - cues_clima presente → CLIMA_1
        - system_idle presente → APAGADO
        - Cualquier otro → BOLICHE_INICIO

        Args:
            actions: Lista de acciones activas

        Returns:
            Modo canónico derivado (uppercase)
        """
        if not actions:
            return "APAGADO"

        # Normalizar a lowercase para comparar
        actions_lower = [a.lower() for a in actions]

        # Prioridad de derivación
        if "audio_911" in actions_lower:
            return "BOLICHE_DESARROLLO"
        if "vision_artista" in actions_lower:
            return "ARTISTA"
        if "cues_clima" in actions_lower:
            return "CLIMA_1"
        if "system_idle" in actions_lower:
            return "APAGADO"

        # Por defecto: boliche_inicio (sin acciones específicas)
        return "BOLICHE_INICIO"

    def _parse_block_mode_actions(self, block: Dict) -> Tuple[str, List[str]]:
        """
        Parsea un bloque y retorna (mode, actions).

        Soporta 3 formatos:
        1. mode + extra_actions (v6.4 nuevo)
        2. actions[] sin mode (v6.4 legacy)
        3. mode solo (legacy clásico)

        Args:
            block: Diccionario del bloque

        Returns:
            Tupla (mode_uppercase, actions_list)
        """
        # Formato 1: mode + extra_actions (v6.4 nuevo - prioritario)
        if "mode" in block:
            mode = block["mode"].upper()
            extra_actions = block.get("extra_actions", [])

            # Combinar acciones del modo con extras
            mode_actions = self._get_mode_base_actions(mode)
            all_actions = list(set(mode_actions + extra_actions))

            return mode, all_actions

        # Formato 2: actions[] sin mode (v6.4 legacy)
        if "actions" in block and block["actions"]:
            actions = block["actions"]
            mode = self._derive_mode_from_actions(actions)
            return mode, actions

        # Formato 3: sin mode ni actions → apagado
        return "APAGADO", ["system_idle"]

    def _get_mode_base_actions(self, mode: str) -> List[str]:
        """
        Obtiene las acciones base de un modo (LEGACY_MODE_MAP).

        Args:
            mode: Modo canónico (uppercase o lowercase)

        Returns:
            Lista de acciones base del modo
        """
        mode_lower = mode.lower()

        # Mapeo de modos a acciones base
        MODE_ACTIONS = {
            "clima_1": ["cues_clima"],
            "clima_2": ["cues_clima"],
            "clima_3": ["cues_clima"],
            "clima_4": ["cues_clima"],
            "teatro": ["vision_artista", "tracking_cam", "dj_detection"],
            "artista": ["vision_artista", "tracking_cam"],
            "boliche_inicio": [],
            "boliche_desarrollo": ["audio_911", "vision_haze", "vision_dj"],
            "boliche_fin": ["audio_911", "vision_haze", "vision_dj", "dj_detection"],
            "apagado": ["system_idle"],
        }

        return MODE_ACTIONS.get(mode_lower, [])

    def resolve(self, now: Optional[datetime] = None) -> Tuple[Optional[str], Optional[ScheduleBlock], Optional[datetime]]:
        """
        Resuelve el modo activo para el momento dado.

        Args:
            now: Momento a resolver (default: datetime.now())

        Returns:
            Tupla (modo, bloque_activo, proximo_cambio)
            - modo: Nombre del clima activo, o None si no hay bloque
            - bloque_activo: ScheduleBlock con info del bloque
            - proximo_cambio: datetime del proximo cambio de modo
        """
        if now is None:
            now = datetime.now()

        if not self._auto_mode_enabled:
            return None, None, None

        # Obtener dia de la semana
        day_name = DAY_NAMES[now.weekday()]
        current_time = now.time()

        # Obtener bloques del dia
        day_blocks = self._schedule.get(day_name, [])

        # Buscar bloque activo en el dia actual
        for block in day_blocks:
            from_time = self._parse_time(block["from"])
            to_time = self._parse_time(block["to"])

            # v6.4: Soportar formato mode + extra_actions
            mode, actions = self._parse_block_mode_actions(block)

            if self._is_time_in_range(current_time, from_time, to_time):
                schedule_block = ScheduleBlock(
                    from_time=block["from"],
                    to_time=block["to"],
                    mode=mode,
                    actions=actions
                )
                next_change = self._calculate_next_change(now, to_time)
                return mode, schedule_block, next_change

        # Si no hay bloque activo hoy, buscar en el dia anterior
        # (para manejar bloques que cruzan medianoche)
        yesterday_idx = (now.weekday() - 1) % 7
        yesterday_name = DAY_NAMES[yesterday_idx]
        yesterday_blocks = self._schedule.get(yesterday_name, [])

        for block in yesterday_blocks:
            from_time = self._parse_time(block["from"])
            to_time = self._parse_time(block["to"])

            # v6.4: Soportar formato mode + extra_actions
            mode, actions = self._parse_block_mode_actions(block)

            # Solo considerar bloques que cruzan medianoche
            if self._time_to_minutes(from_time) > self._time_to_minutes(to_time):
                # Verificar si estamos en la parte "de hoy" del bloque
                if self._time_to_minutes(current_time) < self._time_to_minutes(to_time):
                    schedule_block = ScheduleBlock(
                        from_time=block["from"],
                        to_time=block["to"],
                        mode=mode,
                        actions=actions
                    )
                    next_change = self._calculate_next_change(now, to_time)
                    return mode, schedule_block, next_change

        # No hay bloque activo
        return None, None, self._find_next_block_start(now)

    def _calculate_next_change(self, now: datetime, to_time: time) -> datetime:
        """
        Calcula el datetime del proximo cambio.

        Args:
            now: Momento actual
            to_time: Hora de fin del bloque actual

        Returns:
            datetime del proximo cambio
        """
        # Crear datetime con la hora de fin
        next_change = now.replace(
            hour=to_time.hour,
            minute=to_time.minute,
            second=0,
            microsecond=0
        )

        # Si la hora de fin ya paso hoy, es manana
        if next_change <= now:
            next_change += timedelta(days=1)

        return next_change

    def _find_next_block_start(self, now: datetime) -> Optional[datetime]:
        """
        Encuentra cuando empieza el proximo bloque.

        Args:
            now: Momento actual

        Returns:
            datetime del inicio del proximo bloque, o None
        """
        current_time = now.time()
        current_day = now.weekday()

        # Buscar en los proximos 7 dias
        for day_offset in range(7):
            check_day = (current_day + day_offset) % 7
            day_name = DAY_NAMES[check_day]
            day_blocks = self._schedule.get(day_name, [])

            for block in day_blocks:
                from_time = self._parse_time(block["from"])

                # Si es hoy, solo bloques futuros
                if day_offset == 0:
                    if self._time_to_minutes(from_time) > self._time_to_minutes(current_time):
                        return now.replace(
                            hour=from_time.hour,
                            minute=from_time.minute,
                            second=0,
                            microsecond=0
                        )
                else:
                    # Dias futuros: cualquier bloque
                    future_date = now + timedelta(days=day_offset)
                    return future_date.replace(
                        hour=from_time.hour,
                        minute=from_time.minute,
                        second=0,
                        microsecond=0
                    )

        return None

    def get_day_schedule(self, day_name: str) -> List[Dict]:
        """
        Obtiene el schedule de un dia especifico.

        Args:
            day_name: Nombre del dia en ingles (monday, tuesday, etc)

        Returns:
            Lista de bloques para ese dia
        """
        return self._schedule.get(day_name.lower(), [])

    def is_auto_mode_enabled(self) -> bool:
        """Retorna si el modo automatico esta habilitado"""
        return self._auto_mode_enabled

    def set_auto_mode(self, enabled: bool) -> None:
        """Habilita/deshabilita el modo automatico"""
        self._auto_mode_enabled = enabled
        print(f"[CalendarResolver] Modo automatico: {'ON' if enabled else 'OFF'}")

    def get_schedule_info(self) -> Dict[str, Any]:
        """
        Retorna informacion del schedule cargado.

        Returns:
            Dict con metadata del schedule
        """
        total_blocks = sum(len(blocks) for blocks in self._schedule.values())
        return {
            "config_path": self._config_path,
            "last_load": self._last_load_time.isoformat() if self._last_load_time else None,
            "total_blocks": total_blocks,
            "days_configured": [d for d in DAY_NAMES if self._schedule.get(d, [])],
            "auto_mode": self._auto_mode_enabled
        }
