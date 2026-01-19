# tests/test_v11.py — V11 Pipeline Integration Test Suite
# Tests for full analyzer → voting → state pipeline reconnection

import pytest
import sys
import os
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAnalyzerFlagNames:
    """Test that all modules_golpe analyzers have flag_name attribute."""

    def test_yes_hits_has_flag_name(self):
        from analyzers.yes_hits import YesHits
        analyzer = YesHits()
        assert hasattr(analyzer, 'flag_name'), "YesHits missing flag_name"
        assert analyzer.flag_name == "YES_HITS"

    def test_accent_catcher_has_flag_name(self):
        from analyzers.accent_catcher import AccentCatcher
        analyzer = AccentCatcher()
        assert hasattr(analyzer, 'flag_name'), "AccentCatcher missing flag_name"
        assert analyzer.flag_name == "ACCENT_CATCHER"

    def test_groove_keeper_has_flag_name(self):
        from analyzers.groove_keeper import GrooveKeeper
        analyzer = GrooveKeeper()
        assert hasattr(analyzer, 'flag_name'), "GrooveKeeper missing flag_name"
        assert analyzer.flag_name == "GROOVE_KEEPER"

    def test_pattern_lock_has_flag_name(self):
        from analyzers.pattern_lock import PatternLock
        analyzer = PatternLock()
        assert hasattr(analyzer, 'flag_name'), "PatternLock missing flag_name"
        assert analyzer.flag_name == "PATTERN_LOCK"

    def test_cadence_spotter_has_flag_name(self):
        from analyzers.cadence_spotter import CadenceSpotter
        analyzer = CadenceSpotter()
        assert hasattr(analyzer, 'flag_name'), "CadenceSpotter missing flag_name"
        assert analyzer.flag_name == "CADENCE_SPOTTER"

    def test_flow_monitor_has_flag_name(self):
        from analyzers.flow_monitor import FlowMonitor
        analyzer = FlowMonitor()
        assert hasattr(analyzer, 'flag_name'), "FlowMonitor missing flag_name"
        assert analyzer.flag_name == "FLOW_MONITOR"

    def test_dynamic_pulse_has_flag_name(self):
        from analyzers.dynamic_pulse import DynamicPulse
        analyzer = DynamicPulse()
        assert hasattr(analyzer, 'flag_name'), "DynamicPulse missing flag_name"
        assert analyzer.flag_name == "DYNAMIC_PULSE"

    def test_pulse_finder_wrapper_has_flag_name(self):
        try:
            from analyzers.pulse_finder_wrapper import PulseFinderAnalyzer
            analyzer = PulseFinderAnalyzer()
            assert hasattr(analyzer, 'flag_name'), "PulseFinderAnalyzer missing flag_name"
            assert analyzer.flag_name == "PULSE_FINDER"
        except ImportError:
            pytest.skip("PulseFinderAnalyzer not available")

    def test_rhythm_highlighter_has_flag_name(self):
        from analyzers.rhythm_highlighter import RhythmHighlighter
        analyzer = RhythmHighlighter()
        assert hasattr(analyzer, 'flag_name'), "RhythmHighlighter missing flag_name"
        assert analyzer.flag_name == "RHYTHM_HIGHLIGHTER"

    def test_burst_sharpness_has_flag_name(self):
        from analyzers.burst_sharpness import BurstSharpness
        analyzer = BurstSharpness()
        assert hasattr(analyzer, 'flag_name'), "BurstSharpness missing flag_name"
        assert analyzer.flag_name == "BURST_SHARPNESS"


class TestAnalyzerDetectedAttribute:
    """Test that all modules_golpe analyzers have .detected attribute."""

    def test_yes_hits_has_detected(self):
        from analyzers.yes_hits import YesHits
        analyzer = YesHits()
        assert hasattr(analyzer, 'detected'), "YesHits missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_accent_catcher_has_detected(self):
        from analyzers.accent_catcher import AccentCatcher
        analyzer = AccentCatcher()
        assert hasattr(analyzer, 'detected'), "AccentCatcher missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_groove_keeper_has_detected(self):
        from analyzers.groove_keeper import GrooveKeeper
        analyzer = GrooveKeeper()
        assert hasattr(analyzer, 'detected'), "GrooveKeeper missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_pattern_lock_has_detected(self):
        from analyzers.pattern_lock import PatternLock
        analyzer = PatternLock()
        assert hasattr(analyzer, 'detected'), "PatternLock missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_cadence_spotter_has_detected(self):
        from analyzers.cadence_spotter import CadenceSpotter
        analyzer = CadenceSpotter()
        assert hasattr(analyzer, 'detected'), "CadenceSpotter missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_rhythm_highlighter_has_detected(self):
        from analyzers.rhythm_highlighter import RhythmHighlighter
        analyzer = RhythmHighlighter()
        assert hasattr(analyzer, 'detected'), "RhythmHighlighter missing .detected"
        assert isinstance(analyzer.detected, bool)

    def test_pulse_finder_wrapper_has_detected(self):
        try:
            from analyzers.pulse_finder_wrapper import PulseFinderAnalyzer
            analyzer = PulseFinderAnalyzer()
            assert hasattr(analyzer, 'detected'), "PulseFinderAnalyzer missing .detected"
            assert isinstance(analyzer.detected, bool)
        except ImportError:
            pytest.skip("PulseFinderAnalyzer not available")


class TestBaseGolpeVoting:
    """Test BaseGolpeModule voting system with 10 flags."""

    @pytest.fixture
    def mock_avolites(self):
        """Create mock Avolites for testing."""
        class MockAvolites:
            class config_manager:
                config = {'families': {}}
            def is_active(self, cue_id):
                return False
            def fire_cue(self, cue_id):
                return True
            def kill_cue(self, cue_id):
                pass
        return MockAvolites()

    @pytest.fixture
    def mock_dimmer(self):
        """Create mock dimmer controller."""
        class MockDimmer:
            def request_dim_off(self, reason):
                pass
            def release_dim_off(self, reason):
                pass
        return MockDimmer()

    def test_base_golpe_has_10_flags(self, mock_avolites, mock_dimmer):
        from mod_basegolpe import BaseGolpeModule
        bg = BaseGolpeModule(mock_avolites, mock_dimmer)
        assert len(bg.flags) == 10, f"Expected 10 flags, got {len(bg.flags)}"

    def test_base_golpe_flag_keys(self, mock_avolites, mock_dimmer):
        from mod_basegolpe import BaseGolpeModule
        bg = BaseGolpeModule(mock_avolites, mock_dimmer)
        expected_keys = {
            "hits", "accent", "groove", "pattern", "cadence",
            "flow", "dynamic", "pulse", "rhythm", "burst"
        }
        assert set(bg.flags.keys()) == expected_keys

    def test_update_analyzer_flags_without_modules(self, mock_avolites, mock_dimmer):
        from mod_basegolpe import BaseGolpeModule
        bg = BaseGolpeModule(mock_avolites, mock_dimmer)
        flags = bg.update_analyzer_flags()
        assert all(v is False for v in flags.values()), "All flags should be False without modules"

    def test_update_analyzer_flags_with_mock_modules(self, mock_avolites, mock_dimmer):
        from mod_basegolpe import BaseGolpeModule
        bg = BaseGolpeModule(mock_avolites, mock_dimmer)

        # Create mock modules with flag_name and detected
        class MockModule:
            def __init__(self, flag_name, detected):
                self.flag_name = flag_name
                self.detected = detected

        modules = [
            MockModule("YES_HITS", True),
            MockModule("ACCENT_CATCHER", False),
            MockModule("GROOVE_KEEPER", True),
            MockModule("PATTERN_LOCK", False),
            MockModule("CADENCE_SPOTTER", True),
            MockModule("FLOW_MONITOR", False),
            MockModule("DYNAMIC_PULSE", True),
            MockModule("PULSE_FINDER", False),
            MockModule("RHYTHM_HIGHLIGHTER", True),
            MockModule("BURST_SHARPNESS", False),
        ]

        bg.set_modules_golpe(modules)
        flags = bg.update_analyzer_flags()

        assert flags["hits"] is True
        assert flags["accent"] is False
        assert flags["groove"] is True
        assert flags["pattern"] is False
        assert flags["cadence"] is True
        assert flags["flow"] is False
        assert flags["dynamic"] is True
        assert flags["pulse"] is False
        assert flags["rhythm"] is True
        assert flags["burst"] is False

    def test_get_votes_count(self, mock_avolites, mock_dimmer):
        from mod_basegolpe import BaseGolpeModule
        bg = BaseGolpeModule(mock_avolites, mock_dimmer)

        class MockModule:
            def __init__(self, flag_name, detected):
                self.flag_name = flag_name
                self.detected = detected

        modules = [
            MockModule("YES_HITS", True),
            MockModule("DYNAMIC_PULSE", True),
            MockModule("PULSE_FINDER", True),
        ]

        bg.set_modules_golpe(modules)
        bg.update_analyzer_flags()
        votes = bg.get_votes()

        assert votes == 3, f"Expected 3 votes, got {votes}"


class TestModulesAtaqueNoDuplicate:
    """Test that BurstSharpness is not duplicated in modules_ataque."""

    def test_burst_sharpness_not_in_ataque_definition(self):
        """Verify BurstSharpness is not listed in modules_ataque definition."""
        import ast

        main_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'main.py'
        )

        with open(main_path, 'r') as f:
            content = f.read()

        # Find modules_ataque section
        if 'modules_ataque' in content:
            # Find the array definition
            start = content.find('self.modules_ataque = [')
            if start != -1:
                # Find matching bracket
                depth = 0
                end = start
                for i, c in enumerate(content[start:], start):
                    if c == '[':
                        depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break

                ataque_section = content[start:end]
                # BurstSharpness should not appear in modules_ataque
                assert 'BurstSharpness()' not in ataque_section, \
                    "BurstSharpness should not be in modules_ataque (duplicate removed in V11)"


class TestAnalyzerProcessUpdatesDetected:
    """Test that analyzer.process() updates .detected attribute."""

    def test_accent_catcher_process_updates_detected(self):
        from analyzers.accent_catcher import AccentCatcher
        analyzer = AccentCatcher()

        # Create test audio block (1024 samples, stereo)
        sr = 44100
        block = np.random.randn(1024, 2).astype(np.float32) * 0.5

        # Process should not raise
        analyzer.process(block, sr)

        # detected should still be a bool
        assert isinstance(analyzer.detected, bool)

    def test_groove_keeper_process_updates_detected(self):
        from analyzers.groove_keeper import GrooveKeeper
        analyzer = GrooveKeeper()

        sr = 44100
        block = np.random.randn(1024, 2).astype(np.float32) * 0.5

        analyzer.process(block, sr)
        assert isinstance(analyzer.detected, bool)

    def test_cadence_spotter_process_updates_detected(self):
        from analyzers.cadence_spotter import CadenceSpotter
        analyzer = CadenceSpotter()

        sr = 44100
        block = np.random.randn(1024, 2).astype(np.float32) * 0.5

        analyzer.process(block, sr)
        assert isinstance(analyzer.detected, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
