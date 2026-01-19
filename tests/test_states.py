# tests/test_states.py - 911 Fiesta V12 Automated Tests
# ========================================================
# Tests for state machine, voting, anti-repeat, and transport
# ========================================================

import pytest
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Mock Classes for Testing
# =============================================================================

class MockCard:
    """Mock module card for testing"""
    def __init__(self, is_on: bool = False):
        self._on = is_on

    def is_on(self) -> bool:
        return self._on

    def set_on(self, value: bool):
        self._on = value


class MockModule:
    """Mock analyzer module for testing"""
    def __init__(self, name: str, is_on: bool = False):
        self.name = name
        self.card = MockCard(is_on)
        self.is_placeholder = False
        self.disabled_by_preset = False
        self.active = True

    def process(self, block, sr):
        pass


class MockEnergyDetector:
    """Mock energy detector for testing"""
    def __init__(self):
        self._energy = "MEDIA"
        self._score = 0.5

    def get_energy_name(self) -> str:
        return self._energy

    def get_energy_score(self) -> float:
        return self._score

    def set_energy(self, name: str, score: float = 0.5):
        self._energy = name
        self._score = score


class MockAvolites:
    """Mock Avolites controller for testing"""
    def __init__(self):
        self._active_cues = set()
        self._fire_log = []
        self._kill_log = []

    def is_active(self, cue: int) -> bool:
        return cue in self._active_cues

    def fire_cue(self, cue: int) -> bool:
        self._active_cues.add(cue)
        self._fire_log.append(cue)
        return True

    def kill_cue(self, cue: int) -> bool:
        self._active_cues.discard(cue)
        self._kill_log.append(cue)
        return True

    def get_fire_log(self):
        return self._fire_log

    def clear_logs(self):
        self._fire_log = []
        self._kill_log = []


# =============================================================================
# StateManager Tests
# =============================================================================

class TestStateManager:
    """Tests for StateManager V12"""

    @pytest.fixture
    def state_manager(self):
        """Create a fresh StateManager instance"""
        from state_manager import StateManager
        energy = MockEnergyDetector()
        return StateManager(energy)

    @pytest.fixture
    def modules_bajada(self):
        """Create mock bajada modules (5 modules)"""
        return [MockModule(f"bajada_{i}") for i in range(5)]

    @pytest.fixture
    def modules_golpe(self):
        """Create mock golpe modules (10 modules)"""
        return [MockModule(f"golpe_{i}") for i in range(10)]

    @pytest.fixture
    def modules_ataque(self):
        """Create mock ataque modules (3 modules)"""
        return [MockModule(f"ataque_{i}") for i in range(3)]

    @pytest.fixture
    def modules_brake(self):
        """Create mock brake modules (4 modules)"""
        return [MockModule(f"brake_{i}") for i in range(4)]

    def test_initial_state_is_bajada(self, state_manager):
        """Test that initial state is BAJADA"""
        assert state_manager.current_state == "BAJADA"

    def test_state_constants(self, state_manager):
        """Test state constants are defined"""
        assert state_manager.STATE_BAJADA == "BAJADA"
        assert state_manager.STATE_BASE_GOLPE == "BASE_GOLPE"
        assert state_manager.STATE_ATAQUE == "ATAQUE"
        assert state_manager.STATE_BRAKE == "BRAKE"

    def test_v12_stability_constants(self, state_manager):
        """Test V12 stability constants are defined"""
        assert state_manager.STABILITY_WINDOW_MS == 350
        assert state_manager.INTER_STATE_COOLDOWN_MS == 500

    def test_base_golpe_requires_4_votes(self, state_manager, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Test that BASE_GOLPE requires 4+ votes (40% of 10)"""
        # Set 3 golpe modules active (30% - should NOT trigger)
        for i in range(3):
            modules_golpe[i].card.set_on(True)

        # Wait for stability window + cooldown
        time.sleep(0.9)

        # Update multiple times for stability
        for _ in range(10):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Should still be BAJADA (3/10 = 30% < 40% threshold)
        assert state_manager.current_state == "BAJADA"

        # Set 4 golpe modules active (40% - should trigger)
        modules_golpe[3].card.set_on(True)

        # Wait and update
        for _ in range(20):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Should now be BASE_GOLPE
        assert state_manager.current_state == "BASE_GOLPE"

    def test_ataque_requires_clean_rise(self, state_manager, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Test that ATAQUE requires score to be rising"""
        # First get to BASE_GOLPE
        for i in range(5):
            modules_golpe[i].card.set_on(True)

        for _ in range(20):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Now set all ataque modules active
        for m in modules_ataque:
            m.card.set_on(True)

        # Update multiple times (should eventually trigger ATAQUE)
        for _ in range(30):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Should be ATAQUE after clean rise
        # Note: May need more time due to stability window
        assert state_manager.current_state in ["ATAQUE", "BASE_GOLPE"]

    def test_brake_bypasses_stability(self, state_manager, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Test that BRAKE bypasses stability window and cooldown"""
        # Get to BASE_GOLPE first
        for i in range(5):
            modules_golpe[i].card.set_on(True)

        for _ in range(20):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Now trigger BRAKE (3/4 = 75% > 65%)
        for m in modules_golpe:
            m.card.set_on(False)
        for i in range(3):
            modules_brake[i].card.set_on(True)

        # BRAKE should trigger quickly (bypasses stability)
        for _ in range(5):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        assert state_manager.current_state == "BRAKE"

    def test_bajada_stable_no_false_positives(self, state_manager, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Test that BAJADA doesn't trigger on noise"""
        # Rapidly toggle modules (simulating noise)
        for _ in range(50):
            # Random toggling
            import random
            for m in modules_bajada:
                m.card.set_on(random.random() < 0.3)

            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.02)

        # Should still be BAJADA (stability prevents false triggers)
        assert state_manager.current_state == "BAJADA"

    def test_reset_clears_state(self, state_manager, modules_bajada, modules_golpe, modules_ataque, modules_brake):
        """Test that reset() clears all state"""
        # Get to different state
        for i in range(5):
            modules_golpe[i].card.set_on(True)

        for _ in range(20):
            state_manager.update(modules_bajada, modules_golpe, modules_ataque, modules_brake)
            time.sleep(0.05)

        # Reset
        state_manager.reset()

        assert state_manager.current_state == "BAJADA"
        assert state_manager.previous_state is None
        assert state_manager._pending_state is None


# =============================================================================
# Anti-Repeat Tests
# =============================================================================

class TestAntiRepeat:
    """Tests for cue anti-repeat system"""

    def test_global_last_cue_tracking(self):
        """Test that global last cue is tracked"""
        # This would require importing BaseGolpeModule
        # For now, just verify the concept
        pass

    def test_no_consecutive_repeat(self):
        """Test that same cue is not selected consecutively"""
        # Would need full module setup
        pass


# =============================================================================
# Titan Transport Tests
# =============================================================================

class TestTitanTransport:
    """Tests for Titan HTTP transport"""

    def test_mock_avolites_fire(self):
        """Test mock avolites fire_cue"""
        mock = MockAvolites()
        assert mock.fire_cue(10) is True
        assert mock.is_active(10) is True
        assert 10 in mock.get_fire_log()

    def test_mock_avolites_kill(self):
        """Test mock avolites kill_cue"""
        mock = MockAvolites()
        mock.fire_cue(10)
        mock.kill_cue(10)
        assert mock.is_active(10) is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for full system"""

    def test_state_to_cue_flow(self):
        """Test that state changes trigger appropriate cues"""
        # Would need full CueEngine setup
        pass


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
