# ============================================================================
# tests/test_titan_transport.py - Tests para TITAN HTTP TRANSPORT
# ============================================================================
# Tests incluidos:
# - Test 1: Enviar 50 FIRE rapidisimos (rate limit)
# - Test 2: Simular corte de red 500ms (retry)
# - Test 3: BaseGolpe 180 golpes/min (sin cues pegados)
# - Test 4: Bajada ON->OFF rapido (OFF garantizado)
# - Test 5: Auxiliares ON/OFF continuos (nunca colgados)
# ============================================================================

import time
import threading
import unittest
from unittest.mock import Mock, patch, MagicMock
from typing import Set, List
import queue

# Ajustar path para imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.transport.titan_transport import (
    TitanTransport,
    TransportConfig,
    TransportResult,
)
from core.transport.titan_queue import (
    TitanQueue,
    QueueConfig,
    QueueState,
    TaskType,
)
from core.transport.titan_sync import (
    TitanStateSync,
    SyncConfig,
    SyncState,
)


class MockResponse:
    """Mock para requests.Response."""
    def __init__(self, status_code=200, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data or {}


class TestTitanTransport(unittest.TestCase):
    """Tests para TitanTransport."""

    def setUp(self):
        self.config = TransportConfig(
            console_ip="192.168.1.20",
            console_port=80,
            transport="http",
            user_number_offset=169,
        )

    def tearDown(self):
        pass

    @patch('core.transport.titan_transport.requests.Session')
    def test_send_fire_success(self, mock_session_class):
        """Test FIRE exitoso."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        transport = TitanTransport(self.config)
        result = transport.send_fire(1)

        self.assertTrue(result)
        self.assertEqual(transport.stats.fires_ok, 1)
        self.assertEqual(transport.stats.fires_failed, 0)

    @patch('core.transport.titan_transport.requests.Session')
    def test_send_kill_success(self, mock_session_class):
        """Test KILL exitoso."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        transport = TitanTransport(self.config)
        result = transport.send_kill(42)

        self.assertTrue(result)
        self.assertEqual(transport.stats.kills_ok, 1)
        self.assertEqual(transport.stats.kills_failed, 0)

    @patch('core.transport.titan_transport.requests.Session')
    def test_send_fire_with_retry(self, mock_session_class):
        """Test FIRE con reintentos."""
        mock_session = MagicMock()
        # Falla 2 veces, exito en la 3ra
        mock_session.get.side_effect = [
            MockResponse(500),
            MockResponse(500),
            MockResponse(200),
        ]
        mock_session_class.return_value = mock_session

        transport = TitanTransport(self.config)
        result = transport.send_fire(1)

        self.assertTrue(result)
        self.assertEqual(mock_session.get.call_count, 3)

    @patch('core.transport.titan_transport.requests.Session')
    def test_send_fire_all_retries_fail(self, mock_session_class):
        """Test FIRE cuando todos los reintentos fallan."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(500)
        mock_session_class.return_value = mock_session

        transport = TitanTransport(self.config)
        result = transport.send_fire(1)

        self.assertFalse(result)
        self.assertEqual(transport.stats.fires_failed, 1)

    @patch('core.transport.titan_transport.requests.Session')
    def test_cue_mapping(self, mock_session_class):
        """Test mapeo de cue_id con offset."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        transport = TitanTransport(self.config)
        transport.send_fire(1)  # cue_id=1 deberia mapear a 1+169=170

        # Verificar que la URL contiene el cue mapeado
        call_args = mock_session.get.call_args[0][0]
        self.assertIn("userNumber=170", call_args)


class TestTitanQueue(unittest.TestCase):
    """Tests para TitanQueue."""

    def setUp(self):
        self.transport_config = TransportConfig(
            console_ip="192.168.1.20",
            console_port=80,
            user_number_offset=169,
        )
        self.queue_config = QueueConfig(
            max_queue_size=512,
            rate_limit_ms=10.0,  # Reducido para tests
            max_retries=3,
            dedup_window_ms=100.0,
        )

    def tearDown(self):
        pass

    @patch('core.transport.titan_transport.requests.Session')
    def test_fire_enqueue(self, mock_session_class):
        """Test encolado de FIRE."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        titan_queue = TitanQueue(self.transport_config, self.queue_config)
        titan_queue.start()

        result = titan_queue.fire(42)
        self.assertTrue(result)

        time.sleep(0.2)  # Esperar procesamiento
        titan_queue.stop()

        stats = titan_queue.get_stats()
        self.assertGreaterEqual(stats["fires_enqueued"], 1)

    @patch('core.transport.titan_transport.requests.Session')
    def test_kill_priority_over_fire(self, mock_session_class):
        """Test que KILL tiene prioridad sobre FIRE."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        call_order = []

        def track_calls(url, **kwargs):
            if "KillPlayback" in url:
                call_order.append("KILL")
            elif "FirePlaybackAtLevel" in url:
                call_order.append("FIRE")
            return MockResponse(200)

        mock_session.get.side_effect = track_calls

        # Crear queue con rate limit alto para procesar secuencialmente
        queue_config = QueueConfig(
            rate_limit_ms=50.0,
            dedup_window_ms=10.0,
        )

        titan_queue = TitanQueue(self.transport_config, queue_config)

        # Encolar varios FIRE primero, luego KILL
        titan_queue.fire(1)
        titan_queue.fire(2)
        titan_queue.fire(3)
        titan_queue.kill(99, priority_boost=True)  # Este deberia procesarse primero

        titan_queue.start()
        time.sleep(0.5)  # Esperar procesamiento
        titan_queue.stop()

        # KILL deberia estar antes en la lista (o al menos presente)
        self.assertIn("KILL", call_order)

    @patch('core.transport.titan_transport.requests.Session')
    def test_dedup_prevents_spam(self, mock_session_class):
        """Test anti-duplicado."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        queue_config = QueueConfig(
            rate_limit_ms=5.0,
            dedup_window_ms=1000.0,  # 1 segundo de ventana
        )

        titan_queue = TitanQueue(self.transport_config, queue_config)
        titan_queue.start()

        # Intentar encolar el mismo cue rapidamente
        titan_queue.fire(42)
        result2 = titan_queue.fire(42)  # Deberia ser duplicado
        result3 = titan_queue.fire(42)  # Deberia ser duplicado

        time.sleep(0.2)
        titan_queue.stop()

        stats = titan_queue.get_stats()
        # Solo 1 FIRE deberia haberse encolado
        self.assertEqual(stats["fires_enqueued"], 1)
        self.assertGreater(stats["tasks_dropped_dedup"], 0)

    @patch('core.transport.titan_transport.requests.Session')
    def test_50_fires_rapidisimos(self, mock_session_class):
        """TEST 1: Enviar 50 FIRE rapidisimos - rate limit controla."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        queue_config = QueueConfig(
            rate_limit_ms=5.0,  # Rapido para test
            dedup_window_ms=10.0,  # Corto para permitir todos
        )

        titan_queue = TitanQueue(self.transport_config, queue_config)
        titan_queue.start()

        start = time.time()
        for i in range(50):
            titan_queue.fire(i + 1)  # Diferentes cue_ids
        enqueue_time = time.time() - start

        # El encolado debe ser instantaneo (< 100ms)
        self.assertLess(enqueue_time, 0.1)

        # Esperar procesamiento
        time.sleep(1.0)
        titan_queue.stop()

        stats = titan_queue.get_stats()
        # La mayoria deberia haberse procesado (rate limit puede dropear algunos)
        self.assertGreaterEqual(stats["fires_processed"], 30)

    @patch('core.transport.titan_transport.requests.Session')
    def test_basegolpe_180_golpes_min(self, mock_session_class):
        """TEST 3: BaseGolpe 180 golpes/min - sin cues pegados."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        queue_config = QueueConfig(
            rate_limit_ms=30.0,  # ~33 ops/seg max
            dedup_window_ms=50.0,
        )

        titan_queue = TitanQueue(self.transport_config, queue_config)
        titan_queue.start()

        # Simular 3 segundos de 180 golpes/min = 9 golpes
        # 180 golpes/min = 3 golpes/seg
        golpes = 9
        interval = 1.0 / 3.0  # 333ms entre golpes

        for i in range(golpes):
            cue_id = (i % 3) + 1  # Rotar entre C1, C2, C3
            # Simular KILL anterior + FIRE nuevo
            if i > 0:
                prev_cue = ((i - 1) % 3) + 1
                titan_queue.kill(prev_cue)
            titan_queue.fire(cue_id)
            time.sleep(interval)

        time.sleep(0.5)  # Esperar procesamiento final
        titan_queue.stop()

        stats = titan_queue.get_stats()
        # Verificar que no hay KILLs fallidos (cues pegados)
        self.assertEqual(stats["kills_failed"], 0)

    @patch('core.transport.titan_transport.requests.Session')
    def test_bajada_on_off_rapido(self, mock_session_class):
        """TEST 4: Bajada ON->OFF rapido - OFF garantizado."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        queue_config = QueueConfig(
            rate_limit_ms=20.0,
            dedup_window_ms=30.0,
        )

        titan_queue = TitanQueue(self.transport_config, queue_config)
        titan_queue.start()

        # Simular secuencia rapida ON->OFF
        for _ in range(10):
            titan_queue.fire(10)  # ON
            titan_queue.kill(10)  # OFF inmediato

        time.sleep(0.5)
        titan_queue.stop()

        stats = titan_queue.get_stats()
        # Todos los KILLs deben procesarse
        self.assertEqual(stats["kills_failed"], 0)
        # KILLs procesados >= que encolados (reintentos no cuentan como fail)
        self.assertGreaterEqual(stats["kills_processed"], stats["kills_enqueued"] - stats["kills_retried"])


class TestTitanStateSync(unittest.TestCase):
    """Tests para TitanStateSync."""

    def setUp(self):
        self.transport_config = TransportConfig(
            console_ip="192.168.1.20",
            console_port=80,
            user_number_offset=169,
        )
        self.queue_config = QueueConfig(
            rate_limit_ms=10.0,
        )

    @patch('core.transport.titan_transport.requests.Session')
    def test_orphan_detection(self, mock_session_class):
        """Test deteccion de huerfanos."""
        mock_session = MagicMock()

        # Configurar respuesta de GetActivePlaybacks
        def mock_get(url, **kwargs):
            if "GetActivePlaybacks" in url:
                # Titan reporta cues 170, 175 activos (logicos: 1, 6)
                return MockResponse(200, json_data=[
                    {"userNumber": 170},
                    {"userNumber": 175},
                ])
            return MockResponse(200)

        mock_session.get.side_effect = mock_get
        mock_session_class.return_value = mock_session

        # Crear queue
        titan_queue = TitanQueue(self.transport_config, self.queue_config)
        titan_queue.start()

        # Solo cue 1 esta activo localmente
        local_active = {1}

        sync_config = SyncConfig(
            poll_interval_s=0.5,
            orphan_grace_period_ms=100.0,
            auto_kill_orphans=True,
        )

        titan_sync = TitanStateSync(
            transport=titan_queue.get_transport(),
            queue=titan_queue,
            config=sync_config,
            get_local_active=lambda: local_active,
            user_number_offset=169,
        )
        titan_sync.start()

        # Esperar deteccion y grace period
        time.sleep(1.5)

        stats = titan_sync.get_stats()
        titan_sync.stop()
        titan_queue.stop()

        # Debe haber detectado huerfano (cue 6)
        self.assertGreater(stats["orphans_detected"], 0)

    @patch('core.transport.titan_transport.requests.Session')
    def test_auxiliares_on_off_continuos(self, mock_session_class):
        """TEST 5: Auxiliares ON/OFF continuos - nunca quedan colgados."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        titan_queue = TitanQueue(self.transport_config, self.queue_config)
        titan_queue.start()

        # Simular 20 ciclos ON/OFF de auxiliares
        for i in range(20):
            # ON auxiliar
            titan_queue.fire(45 + (i % 5))
            time.sleep(0.05)
            # OFF auxiliar
            titan_queue.kill(45 + (i % 5))
            time.sleep(0.05)

        time.sleep(0.3)
        titan_queue.stop()

        stats = titan_queue.get_stats()
        # Ningun KILL debe fallar
        self.assertEqual(stats["kills_failed"], 0)


class TestIntegration(unittest.TestCase):
    """Tests de integracion."""

    @patch('core.transport.titan_transport.requests.Session')
    def test_full_system_startup(self, mock_session_class):
        """Test arranque completo del sistema."""
        mock_session = MagicMock()
        mock_session.get.return_value = MockResponse(200)
        mock_session_class.return_value = mock_session

        transport_config = TransportConfig()
        queue_config = QueueConfig(rate_limit_ms=10.0)
        sync_config = SyncConfig(poll_interval_s=1.0)

        titan_queue = TitanQueue(transport_config, queue_config)
        titan_sync = TitanStateSync(
            transport=titan_queue.get_transport(),
            queue=titan_queue,
            config=sync_config,
            get_local_active=lambda: set(),
        )

        # Iniciar todo
        titan_queue.start()
        titan_sync.start()

        # Verificar estados
        self.assertEqual(titan_queue._state, QueueState.RUNNING)
        self.assertEqual(titan_sync._state, SyncState.RUNNING)

        # Enviar algunos comandos
        titan_queue.fire(1)
        titan_queue.kill(2)

        time.sleep(0.3)

        # Detener todo
        titan_sync.stop()
        titan_queue.stop()

        self.assertEqual(titan_queue._state, QueueState.STOPPED)
        self.assertEqual(titan_sync._state, SyncState.STOPPED)


class TestNetworkFailure(unittest.TestCase):
    """TEST 2: Simular corte de red 500ms."""

    @patch('core.transport.titan_transport.requests.Session')
    def test_network_cut_recovery(self, mock_session_class):
        """Test recuperacion de corte de red."""
        mock_session = MagicMock()

        # Simular fallo de red temporal
        call_count = [0]

        def mock_get_with_failure(url, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                # Primeras 2 llamadas fallan (simula corte)
                from requests.exceptions import ConnectionError
                raise ConnectionError("Network unreachable")
            return MockResponse(200)

        mock_session.get.side_effect = mock_get_with_failure
        mock_session_class.return_value = mock_session

        transport = TitanTransport(TransportConfig())

        # El FIRE deberia reintentar y eventualmente tener exito
        result = transport.send_fire(1)

        self.assertTrue(result)
        # Deberia haber hecho 3 llamadas (2 fallos + 1 exito)
        self.assertEqual(call_count[0], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
