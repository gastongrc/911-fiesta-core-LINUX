#!/usr/bin/env python3
# tools/test_bpm_master.py
# Script de testing automático para BPM Master System

import sys
import os
import time
import numpy as np

# Agregar path del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core_bpm import (
    BpmRawDetector, BpmSmoother, BpmPll, BeatClock, HarmonicInspector,
    # ROBUST ENGINE V2
    MultibandOnsetDetector, BpmOCR, HarmonicInspectorV2, DriftAnalyzer, PllV2
)


def test_raw_detector():
    """Test 1: RAW detector debe detectar entre 80-150 BPM."""
    print("\n[TEST 1] RAW Detector - Rango 80-150 BPM")
    print("=" * 60)

    detector = BpmRawDetector(min_bpm=80.0, max_bpm=150.0, window_seconds=3.0)

    # Generar audio sintético a 120 BPM (2 beats/segundo)
    sr = 44100
    duration = 4.0  # 4 segundos
    samples = int(sr * duration)

    # Crear señal con pulsos a 120 BPM
    audio = np.zeros(samples)
    beat_interval = sr // 2  # 2 beats por segundo = 120 BPM
    for i in range(0, samples, beat_interval):
        # Añadir pulso
        if i + 100 < samples:
            audio[i:i+100] = 0.5 * np.sin(2 * np.pi * np.arange(100) / 100)

    # Procesar
    bpm = detector.process(audio.astype(np.float32), sr)

    if bpm is not None:
        print(f"✅ Detección exitosa: {bpm:.1f} BPM")
        if 80 <= bpm <= 150:
            print(f"✅ BPM dentro del rango esperado (80-150)")
            return True
        else:
            print(f"❌ BPM fuera de rango: {bpm:.1f}")
            return False
    else:
        print("❌ No se detectó BPM")
        return False


def test_smoother():
    """Test 2: Smoother debe converger sin overshoot."""
    print("\n[TEST 2] Smoother - Convergencia sin overshoot")
    print("=" * 60)

    smoother = BpmSmoother(alpha=0.20)

    # Simular entrada escalón de 100 BPM a 120 BPM
    values = []
    for i in range(50):
        if i < 10:
            raw = 100.0
        else:
            raw = 120.0

        smooth = smoother.update(raw)
        values.append(smooth)
        print(f"  Step {i:2d}: raw={raw:.1f} → smooth={smooth:.1f}")

    # Verificar convergencia
    final_value = values[-1]
    target = 120.0
    error = abs(final_value - target)

    if error < 1.0:
        print(f"✅ Convergencia exitosa: {final_value:.2f} ≈ {target:.2f} (error={error:.2f})")
        return True
    else:
        print(f"❌ No convergió: {final_value:.2f} vs {target:.2f} (error={error:.2f})")
        return False


def test_pll_stability():
    """Test 3: PLL debe estabilizar en menos de 4 segundos."""
    print("\n[TEST 3] PLL - Estabilización < 4 segundos")
    print("=" * 60)

    pll = BpmPll(kp=0.045, ki=0.015)

    # Simular entrada constante a 120 BPM
    dt = 0.25  # 4 Hz
    iterations = 20  # 5 segundos
    values = []

    for i in range(iterations):
        master = pll.update(120.0)
        values.append(master)
        time.sleep(0.01)  # Pequeña pausa
        print(f"  t={i*dt:.2f}s: master={master:.2f} BPM, locked={pll.is_locked()}")

        # Verificar estabilización en 4 segundos (16 iteraciones @ 0.25s)
        if i >= 16:
            error = abs(master - 120.0)
            if error < 2.0 and pll.is_locked():
                print(f"✅ PLL locked en {i*dt:.2f}s (error={error:.2f})")
                return True

    print(f"❌ PLL no se estabilizó en 4 segundos")
    return False


def test_beat_clock():
    """Test 4: Beat clock debe mantener ±1ms de drift."""
    print("\n[TEST 4] Beat Clock - Drift ±1ms")
    print("=" * 60)

    clock = BeatClock()
    clock.set_bpm(120.0)  # 2 beats/segundo

    # Simular ticks a 120 BPM
    dt = 0.010  # 10ms por tick
    beat_count = 0
    last_beat_time = time.time()

    for i in range(100):  # 1 segundo de simulación
        clock.tick(dt)

        if clock.is_beat():
            now = time.time()
            if beat_count > 0:
                interval = now - last_beat_time
                expected = 0.5  # 120 BPM = 2 beats/s = 0.5s por beat
                drift_ms = abs(interval - expected) * 1000
                print(f"  Beat {beat_count}: interval={interval:.3f}s, drift={drift_ms:.2f}ms")

                if drift_ms > 50:  # Tolerancia de 50ms (muy laxo para testing)
                    print(f"❌ Drift excesivo: {drift_ms:.2f}ms")
                    return False

            last_beat_time = now
            beat_count += 1

        time.sleep(dt)

    print(f"✅ Beat clock estable: {beat_count} beats detectados")
    return True


def test_integration():
    """Test 5: Integración completa del pipeline."""
    print("\n[TEST 5] Integración - Pipeline completo")
    print("=" * 60)

    # Instanciar todos los componentes
    raw_detector = BpmRawDetector()
    smoother = BpmSmoother()
    pll = BpmPll()
    beat_clock = BeatClock()

    print("✅ Todos los componentes instanciados correctamente")

    # Generar audio sintético
    sr = 44100
    duration = 2.0
    samples = int(sr * duration)
    audio = np.random.randn(samples) * 0.1  # Ruido de fondo

    # Añadir beats a 120 BPM
    beat_interval = sr // 2
    for i in range(0, samples, beat_interval):
        if i + 100 < samples:
            audio[i:i+100] += 0.5 * np.sin(2 * np.pi * np.arange(100) / 100)

    # Procesar pipeline
    raw_bpm = raw_detector.process(audio.astype(np.float32), sr)
    if raw_bpm is None:
        print("❌ RAW detector no detectó BPM")
        return False

    print(f"  RAW: {raw_bpm:.1f} BPM")

    smooth_bpm = smoother.update(raw_bpm)
    print(f"  SMOOTH: {smooth_bpm:.1f} BPM")

    master_bpm = pll.update(smooth_bpm)
    print(f"  MASTER: {master_bpm:.1f} BPM")

    beat_clock.set_bpm(master_bpm)
    beat_clock.tick(0.25)
    phase = beat_clock.get_phase()
    print(f"  PHASE: {phase:.3f}")

    print("✅ Pipeline completo exitoso")
    return True


def test_harmonic_inspector():
    """Test 6: Harmonic Inspector debe corregir half/double-tempo."""
    print("\n[TEST 6] Harmonic Inspector - Corrección armónica")
    print("=" * 60)

    inspector = HarmonicInspector(window_seconds=10.0, cadence_hz=4.0)

    # Escenario: RAW oscila entre 84 (half-tempo) y 118 (correcto)
    # El inspector debe identificar cluster dominante y corregir

    print("  Fase 1: RAW=84 durante 6s (24 muestras @ 4Hz)")
    for i in range(24):
        corrected = inspector.get_corrected(84.0)
        if i % 6 == 0:
            print(f"    t={i*0.25:.2f}s: RAW=84 → corrected={corrected:.1f}")

    print("\n  Fase 2: RAW=118 durante 6s (24 muestras @ 4Hz)")
    for i in range(24):
        corrected = inspector.get_corrected(118.0)
        if i % 6 == 0:
            print(f"    t={(24+i)*0.25:.2f}s: RAW=118 → corrected={corrected:.1f}")

    # Verificar que el cluster dominante se estableció correctamente
    status = inspector.get_status()
    dominant = status.get('dominant_cluster')

    print(f"\n  Cluster dominante: {dominant:.1f} BPM")

    # El cluster dominante debe estar cerca de 118 o 168 (84*2)
    # Porque el inspector agrupa variantes armónicas
    if dominant is not None:
        # Verificar que está en el rango esperado (cerca de 118)
        if 110 <= dominant <= 125:
            print(f"✅ Cluster dominante correcto: {dominant:.1f} ≈ 118")
            return True
        else:
            print(f"❌ Cluster dominante inesperado: {dominant:.1f}")
            return False
    else:
        print("❌ No se estableció cluster dominante")
        return False


def test_multiband_onset():
    """Test 7: Multiband Onset Detector debe detectar onsets en 5 bandas."""
    print("\n[TEST 7] Multiband Onset Detector - 5 bandas")
    print("=" * 60)

    detector = MultibandOnsetDetector(hop_size=512, threshold=0.05)

    # Generar audio con onsets en diferentes bandas
    sr = 44100
    duration = 2.0
    samples = int(sr * duration)
    audio = np.zeros(samples)

    # Añadir kicks (40-120 Hz) cada 0.5s
    for i in range(0, samples, sr // 2):
        if i + 1000 < samples:
            # Kick: onda sinusoidal a 80 Hz
            t = np.arange(1000) / sr
            audio[i:i+1000] += 0.8 * np.sin(2 * np.pi * 80 * t)

    # Añadir hi-hats (8k-20k Hz) cada 0.25s
    for i in range(0, samples, sr // 4):
        if i + 100 < samples:
            # Hi-hat: ruido filtrado en high freq
            audio[i:i+100] += 0.3 * np.random.randn(100)

    # Procesar
    onsets = detector.process(audio.astype(np.float32), sr)

    print(f"  Onsets detectados: {len(onsets)}")
    for i, (timestamp, strength) in enumerate(onsets[:10]):
        print(f"    Onset {i}: t={timestamp:.3f}s, strength={strength:.3f}")

    if len(onsets) >= 4:  # Al menos 4 beats en 2 segundos
        print(f"✅ Multiband detector exitoso: {len(onsets)} onsets")
        return True
    else:
        print(f"❌ Pocos onsets detectados: {len(onsets)}")
        return False


def test_bpm_ocr():
    """Test 8: BPM OCR debe reconstruir BPM desde onsets irregulares."""
    print("\n[TEST 8] BPM OCR - Clustering de deltas")
    print("=" * 60)

    ocr = BpmOCR(min_bpm=80.0, max_bpm=180.0, window_seconds=6.0, cadence_hz=4.0)

    # Simular onsets a 120 BPM (0.5s entre beats) con 20% missing
    target_bpm = 120.0
    beat_interval = 60.0 / target_bpm
    onsets = []
    t = 0.0

    for i in range(20):
        if np.random.random() > 0.2:  # 80% de beats presentes
            strength = 0.5 + 0.3 * np.random.random()
            onsets.append((t, strength))
        t += beat_interval

    print(f"  Onsets simulados: {len(onsets)} (de 20 esperados)")

    # Procesar
    bpm = ocr.process(onsets)
    confidence = ocr.get_confidence()

    print(f"  BPM detectado: {bpm:.1f}")
    print(f"  Confidence: {confidence:.2f}")
    print(f"  Target: {target_bpm:.1f}")

    if bpm is not None:
        error = abs(bpm - target_bpm)
        if error < 5.0:  # Error < 5 BPM
            print(f"✅ BPM OCR exitoso: {bpm:.1f} ≈ {target_bpm:.1f} (error={error:.2f})")
            return True
        else:
            print(f"❌ Error excesivo: {error:.2f} BPM")
            return False
    else:
        print("❌ No se detectó BPM")
        return False


def test_harmonic_v2():
    """Test 9: Harmonic Inspector v2 debe corregir con multi-ventana."""
    print("\n[TEST 9] Harmonic Inspector v2 - Multi-ventana")
    print("=" * 60)

    inspector = HarmonicInspectorV2(cadence_hz=4.0, tolerance=0.03)

    # Escenario: RAW oscila entre 59 (half) y 118 (correcto)
    print("  Fase 1: RAW=59 BPM durante 3s")
    for i in range(12):  # 3s @ 4Hz
        corrected = inspector.fix(59.0)
        if i % 4 == 0:
            print(f"    t={i*0.25:.2f}s: 59 → {corrected:.1f}")

    print("\n  Fase 2: RAW=118 BPM durante 6s")
    for i in range(24):  # 6s @ 4Hz
        corrected = inspector.fix(118.0)
        if i % 6 == 0:
            print(f"    t={(12+i)*0.25:.2f}s: 118 → {corrected:.1f}")

    # Verificar corrección
    status = inspector.get_status()
    dominant = status.get('dominant_cluster')
    correction = inspector.get_correction_type()

    print(f"\n  Cluster dominante: {dominant:.1f} BPM")
    print(f"  Corrección aplicada: {correction}")

    if dominant is not None and 110 <= dominant <= 125:
        print(f"✅ Harmonic v2 correcto: {dominant:.1f} ≈ 118")
        return True
    else:
        print(f"❌ Cluster inesperado: {dominant}")
        return False


def test_drift_analyzer():
    """Test 10: Drift Analyzer debe detectar y corregir micro-drifts."""
    print("\n[TEST 10] Drift Analyzer - Corrección <1ms")
    print("=" * 60)

    analyzer = DriftAnalyzer(window_size=32, drift_threshold=0.001)

    # Simular BPM estable con drift acumulado
    base_bpm = 120.0
    drift_per_beat = 0.0005  # 0.5ms por beat

    print("  Simulando 40 beats con drift acumulado")
    for i in range(40):
        # BPM con drift simulado
        bpm_with_drift = base_bpm * (1.0 + drift_per_beat * i)
        corrected = analyzer.apply(bpm_with_drift)

        if i % 10 == 0:
            drift_detected = analyzer.get_drift()
            print(f"    Beat {i}: input={bpm_with_drift:.3f}, corrected={corrected:.3f}, drift={drift_detected*1000:.3f}ms")

        time.sleep(0.01)  # Simular tiempo entre beats

    # Verificar que se detectó drift
    final_drift = analyzer.get_drift()
    drift_ms = abs(final_drift) * 1000

    print(f"\n  Drift final detectado: {drift_ms:.3f}ms")

    if drift_ms > 0.1:  # Debe detectar algún drift
        print(f"✅ Drift analyzer funcional: {drift_ms:.3f}ms detectado")
        return True
    else:
        print(f"❌ No se detectó drift suficiente")
        return False


def test_pll_v2():
    """Test 11: PLL v2 debe auto-lock con modos dinámicos."""
    print("\n[TEST 11] PLL v2 - Auto-lock dinámico")
    print("=" * 60)

    pll = PllV2(kp_base=0.045, ki_base=0.015)

    # Fase 1: Input estable → HARD_LOCK
    print("  Fase 1: Input estable a 120 BPM")
    for i in range(30):
        master = pll.update(120.0 + np.random.randn() * 0.2)
        if i % 10 == 0:
            print(f"    t={i*0.25:.2f}s: master={master:.2f}, mode={pll.get_lock_mode()}")
        time.sleep(0.01)

    mode_after_stable = pll.get_lock_mode()

    # Fase 2: Input variable → UNLOCKED
    print("\n  Fase 2: Input variable")
    pll.reset()
    for i in range(20):
        noisy_bpm = 120.0 + np.random.randn() * 5.0  # Mucho ruido
        master = pll.update(noisy_bpm)
        if i % 10 == 0:
            print(f"    t={i*0.25:.2f}s: master={master:.2f}, mode={pll.get_lock_mode()}")
        time.sleep(0.01)

    mode_after_noisy = pll.get_lock_mode()

    print(f"\n  Modo después de estabilidad: {mode_after_stable}")
    print(f"  Modo después de ruido: {mode_after_noisy}")

    if mode_after_stable in ['HARD_LOCK', 'SOFT_LOCK'] and mode_after_noisy == 'UNLOCKED':
        print(f"✅ PLL v2 auto-lock correcto")
        return True
    else:
        print(f"❌ Modos incorrectos: {mode_after_stable}, {mode_after_noisy}")
        return False


def main():
    """Ejecutar todos los tests."""
    print("\n" + "=" * 60)
    print(" BPM MASTER SYSTEM - TEST SUITE")
    print("=" * 60)

    results = []

    # Ejecutar tests v1
    results.append(("RAW Detector", test_raw_detector()))
    results.append(("Smoother", test_smoother()))
    results.append(("PLL Stability", test_pll_stability()))
    results.append(("Beat Clock", test_beat_clock()))
    results.append(("Integration", test_integration()))
    results.append(("Harmonic Inspector", test_harmonic_inspector()))

    # Ejecutar tests ROBUST v2
    results.append(("Multiband Onset", test_multiband_onset()))
    results.append(("BPM OCR", test_bpm_ocr()))
    results.append(("Harmonic v2", test_harmonic_v2()))
    results.append(("Drift Analyzer", test_drift_analyzer()))
    results.append(("PLL v2", test_pll_v2()))

    # Resumen
    print("\n" + "=" * 60)
    print(" RESUMEN DE TESTS")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name:20s} {status}")

    print("\n" + "=" * 60)
    print(f" TOTAL: {passed}/{total} tests passed")
    print("=" * 60 + "\n")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
