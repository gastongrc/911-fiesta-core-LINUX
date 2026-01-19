# ============================================================================
# titan_transport.py v1.1 - TITAN HTTP TRANSPORT (LEGACY COMPATIBLE)
# ============================================================================
# Responsable del envio real HTTP a Avolites Titan
#
# LEGACY MODE v1.1:
# - Sin health-check obligatorio
# - Solo endpoints clasicos:
#   FIRE: /titan/script/Playbacks/FirePlaybackAtLevel?userNumber={cue}&level=1.0&bool=false
#   KILL: /titan/script/Playbacks/KillPlayback?userNumber={cue}
# - HTTP siempre (consolas legacy no soportan HTTPS)
# - Sin dependencia de endpoints modernos (SoftwareVersion, GetActivePlaybacks)
#
# Features:
# - send_fire(cue_id) -> bool
# - send_kill(cue_id) -> bool
# - 3 reintentos automaticos con delay exponencial
# - Timeout configurable por request
# - Logs estructurados para debug
# - Confirmacion de entrega (HTTP 200 = OK)
# ============================================================================

from __future__ import annotations

import time
import logging
from typing import Optional, Tuple, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException, Timeout, ConnectionError

# ===== LOGGING =====
logger = logging.getLogger("TitanTransport")


class TransportResult(Enum):
    """Resultado del envio HTTP."""
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    HTTP_ERROR = "HTTP_ERROR"
    EXCEPTION = "EXCEPTION"


@dataclass
class TransportConfig:
    """Configuracion del transporte HTTP."""
    console_ip: str = "192.168.1.20"
    console_port: int = 80
    transport: str = "http"
    connect_timeout: float = 1.2
    read_timeout: float = 1.0
    max_retries: int = 3
    retry_delays: Tuple[float, ...] = (0.05, 0.1, 0.2)  # ms entre reintentos
    user_number_offset: int = 169


@dataclass
class TransportStats:
    """Estadisticas del transporte."""
    fires_sent: int = 0
    fires_ok: int = 0
    fires_failed: int = 0
    kills_sent: int = 0
    kills_ok: int = 0
    kills_failed: int = 0
    retries_total: int = 0
    last_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_success_ts: float = 0.0
    last_error_ts: float = 0.0


class TitanTransport:
    """
    Titan HTTP Transport v1.0

    Responsable del envio HTTP real a Avolites Titan.
    NO gestiona colas ni prioridades - solo envia y reporta resultado.

    Uso:
        transport = TitanTransport(config)
        success = transport.send_fire(cue_id=42)
        success = transport.send_kill(cue_id=42)
    """

    def __init__(
        self,
        config: Optional[TransportConfig] = None,
        on_success: Optional[Callable[[str, int], None]] = None,
        on_failure: Optional[Callable[[str, int, str], None]] = None,
    ):
        """
        Inicializa el transporte.

        Args:
            config: Configuracion del transporte (usa defaults si None)
            on_success: Callback(action, cue_id) cuando envio OK
            on_failure: Callback(action, cue_id, error) cuando envio falla
        """
        self.config = config or TransportConfig()
        self.stats = TransportStats()
        self._session: Optional[requests.Session] = None
        self._on_success = on_success
        self._on_failure = on_failure

        # Inicializar sesion HTTP
        self._setup_session()

        logger.info(f"[TitanTransport] Inicializado -> {self.config.transport}://{self.config.console_ip}:{self.config.console_port}")

    def _setup_session(self):
        """Configura sesion HTTP con keep-alive."""
        if self._session:
            try:
                self._session.close()
            except:
                pass

        self._session = requests.Session()

        # Configurar adapter con connection pooling
        adapter = HTTPAdapter(
            pool_connections=2,
            pool_maxsize=4,
            max_retries=0  # Manejamos retries manualmente
        )
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)

        self._session.headers.update({
            "Connection": "keep-alive",
            "User-Agent": "911Fiesta-TitanTransport/1.0"
        })

    def _build_url(self, path: str) -> str:
        """Construye URL completa."""
        scheme = self.config.transport
        ip = self.config.console_ip
        port = self.config.console_port
        return f"{scheme}://{ip}:{port}{path}"

    def _timeouts(self) -> Tuple[float, float]:
        """Retorna (connect_timeout, read_timeout)."""
        return (self.config.connect_timeout, self.config.read_timeout)

    def _map_cue(self, cue_id: int) -> int:
        """Aplica offset de mapeo al cue_id."""
        return cue_id + self.config.user_number_offset

    def _send_request(self, url: str, action: str, cue_id: int) -> Tuple[bool, TransportResult, Optional[str]]:
        """
        Envia request HTTP con reintentos.

        Args:
            url: URL completa
            action: "FIRE" o "KILL" para logging
            cue_id: ID del cue (para logging)

        Returns:
            (success, result_type, error_message)
        """
        last_error = None
        retry_delays = list(self.config.retry_delays)

        for attempt in range(self.config.max_retries):
            try:
                start_ts = time.time()

                response = self._session.get(
                    url,
                    timeout=self._timeouts(),
                    verify=False  # Titan no siempre tiene cert valido
                )

                elapsed_ms = (time.time() - start_ts) * 1000
                self.stats.last_latency_ms = elapsed_ms

                if response.status_code == 200:
                    self.stats.last_success_ts = time.time()
                    logger.debug(f"[TitanTransport] {action} C{cue_id} OK ({elapsed_ms:.0f}ms)")
                    return (True, TransportResult.SUCCESS, None)
                else:
                    last_error = f"HTTP {response.status_code}"
                    logger.warning(f"[TitanTransport] {action} C{cue_id} HTTP error: {last_error}")

            except Timeout as e:
                last_error = f"Timeout: {e}"
                self.stats.retries_total += 1
                logger.warning(f"[TitanTransport] {action} C{cue_id} timeout (attempt {attempt+1})")

            except ConnectionError as e:
                last_error = f"Connection: {e}"
                self.stats.retries_total += 1
                logger.warning(f"[TitanTransport] {action} C{cue_id} connection error (attempt {attempt+1})")

            except RequestException as e:
                last_error = f"Request: {e}"
                self.stats.retries_total += 1
                logger.warning(f"[TitanTransport] {action} C{cue_id} request error: {e}")

            except Exception as e:
                last_error = f"Exception: {e}"
                logger.error(f"[TitanTransport] {action} C{cue_id} unexpected error: {e}")
                break  # No reintentar en errores inesperados

            # Delay antes del siguiente intento
            if attempt < self.config.max_retries - 1 and retry_delays:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                time.sleep(delay)

        # Todos los intentos fallaron
        self.stats.last_error = last_error
        self.stats.last_error_ts = time.time()
        return (False, TransportResult.HTTP_ERROR, last_error)

    def send_fire(self, cue_id: int) -> bool:
        """
        Envia comando FIRE a Titan.

        Args:
            cue_id: ID logico del cue (se aplica offset)

        Returns:
            bool: True si el envio fue exitoso
        """
        real_cue = self._map_cue(cue_id)
        print(f"[TitanTransport] SEND FIRE cue={cue_id} (real={real_cue})")
        url = self._build_url(
            f"/titan/script/Playbacks/FirePlaybackAtLevel?userNumber={real_cue}&level=1.0&bool=false"
        )

        self.stats.fires_sent += 1
        success, result, error = self._send_request(url, "FIRE", cue_id)

        if success:
            self.stats.fires_ok += 1
            if self._on_success:
                try:
                    self._on_success("FIRE", cue_id)
                except:
                    pass
        else:
            self.stats.fires_failed += 1
            if self._on_failure:
                try:
                    self._on_failure("FIRE", cue_id, error or "Unknown error")
                except:
                    pass

        return success

    def send_kill(self, cue_id: int) -> bool:
        """
        Envia comando KILL a Titan.

        Args:
            cue_id: ID logico del cue (se aplica offset)

        Returns:
            bool: True si el envio fue exitoso
        """
        real_cue = self._map_cue(cue_id)
        print(f"[TitanTransport] SEND KILL cue={cue_id} (real={real_cue})")
        url = self._build_url(
            f"/titan/script/Playbacks/KillPlayback?userNumber={real_cue}"
        )

        self.stats.kills_sent += 1
        success, result, error = self._send_request(url, "KILL", cue_id)

        if success:
            self.stats.kills_ok += 1
            if self._on_success:
                try:
                    self._on_success("KILL", cue_id)
                except:
                    pass
        else:
            self.stats.kills_failed += 1
            if self._on_failure:
                try:
                    self._on_failure("KILL", cue_id, error or "Unknown error")
                except:
                    pass

        return success

    def send_fire_raw(self, real_cue: int) -> bool:
        """
        Envia FIRE sin aplicar offset (cue ya mapeado).

        Args:
            real_cue: ID real del cue en Titan

        Returns:
            bool: True si exitoso
        """
        url = self._build_url(
            f"/titan/script/Playbacks/FirePlaybackAtLevel?userNumber={real_cue}&level=1.0&bool=false"
        )

        self.stats.fires_sent += 1
        success, _, _ = self._send_request(url, "FIRE_RAW", real_cue)

        if success:
            self.stats.fires_ok += 1
        else:
            self.stats.fires_failed += 1

        return success

    def send_kill_raw(self, real_cue: int) -> bool:
        """
        Envia KILL sin aplicar offset (cue ya mapeado).

        Args:
            real_cue: ID real del cue en Titan

        Returns:
            bool: True si exitoso
        """
        url = self._build_url(
            f"/titan/script/Playbacks/KillPlayback?userNumber={real_cue}"
        )

        self.stats.kills_sent += 1
        success, _, _ = self._send_request(url, "KILL_RAW", real_cue)

        if success:
            self.stats.kills_ok += 1
        else:
            self.stats.kills_failed += 1

        return success

    def ping(self) -> bool:
        """
        Ping a Titan para verificar conectividad.

        Returns:
            bool: True si Titan responde
        """
        url = self._build_url("/titan/get/System/SoftwareVersion")

        try:
            response = self._session.get(url, timeout=self._timeouts(), verify=False)
            if response.status_code == 200:
                version = response.text.strip().strip('"')
                logger.info(f"[TitanTransport] Ping OK - Titan {version}")
                return True
        except Exception as e:
            logger.warning(f"[TitanTransport] Ping failed: {e}")

        return False

    def get_active_playbacks(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene lista de playbacks activos desde Titan.

        Returns:
            Dict con playbacks activos o None si falla
        """
        url = self._build_url("/titan/script/Playbacks/GetActivePlaybacks")

        try:
            response = self._session.get(url, timeout=self._timeouts(), verify=False)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.warning(f"[TitanTransport] GetActivePlaybacks failed: {e}")

        return None

    def update_config(
        self,
        console_ip: Optional[str] = None,
        console_port: Optional[int] = None,
        transport: Optional[str] = None,
        user_number_offset: Optional[int] = None,
    ):
        """
        Actualiza configuracion del transporte.

        Args:
            console_ip: Nueva IP de consola
            console_port: Nuevo puerto
            transport: Nuevo protocolo (http/https)
            user_number_offset: Nuevo offset de cues
        """
        if console_ip:
            self.config.console_ip = console_ip
        if console_port:
            self.config.console_port = console_port
        if transport:
            self.config.transport = transport
        if user_number_offset is not None:
            self.config.user_number_offset = user_number_offset

        # Recrear sesion con nueva config
        self._setup_session()

        logger.info(f"[TitanTransport] Config updated -> {self.config.transport}://{self.config.console_ip}:{self.config.console_port}")

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estadisticas del transporte."""
        return {
            "fires_sent": self.stats.fires_sent,
            "fires_ok": self.stats.fires_ok,
            "fires_failed": self.stats.fires_failed,
            "kills_sent": self.stats.kills_sent,
            "kills_ok": self.stats.kills_ok,
            "kills_failed": self.stats.kills_failed,
            "retries_total": self.stats.retries_total,
            "last_latency_ms": self.stats.last_latency_ms,
            "last_error": self.stats.last_error,
            "last_success_ts": self.stats.last_success_ts,
            "last_error_ts": self.stats.last_error_ts,
            "success_rate_fire": (
                self.stats.fires_ok / self.stats.fires_sent * 100
                if self.stats.fires_sent > 0 else 100.0
            ),
            "success_rate_kill": (
                self.stats.kills_ok / self.stats.kills_sent * 100
                if self.stats.kills_sent > 0 else 100.0
            ),
        }

    def reset_stats(self):
        """Resetea estadisticas."""
        self.stats = TransportStats()

    def close(self):
        """Cierra la sesion HTTP."""
        if self._session:
            try:
                self._session.close()
            except:
                pass
            self._session = None

        logger.info("[TitanTransport] Closed")

    def __del__(self):
        try:
            self.close()
        except:
            pass


__all__ = ["TitanTransport", "TransportConfig", "TransportStats", "TransportResult"]
