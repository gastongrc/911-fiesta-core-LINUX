#!/usr/bin/env python3
"""
diag_boot.py - Diagnóstico de arranque para 911 Fiesta
======================================================
Detecta problemas de portabilidad entre máquinas (Windows/Linux/Mac).

Uso:
    python tools/diag_boot.py

Reporta:
    - .pth files que ejecutan código
    - sitecustomize/usercustomize
    - signature_bootstrap origen
    - variables de entorno críticas
    - estado de PySide6
"""

import sys
import os
import site
import importlib.util
from pathlib import Path


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


def check_python_env():
    """Información básica del entorno Python."""
    print_section("ENTORNO PYTHON")
    print(f"  sys.executable: {sys.executable}")
    print(f"  sys.version: {sys.version.split()[0]}")
    print(f"  sys.platform: {sys.platform}")
    print(f"  cwd: {os.getcwd()}")
    print(f"\n  sys.path[0:5]:")
    for i, p in enumerate(sys.path[:5]):
        print(f"    [{i}] {p}")


def find_pth_files_with_exec():
    """Busca .pth que ejecutan código (import o código directo)."""
    print_section(".PTH FILES CON CÓDIGO EJECUTABLE")

    site_packages = site.getsitepackages() + [site.getusersitepackages()]
    found_any = False

    for sp in site_packages:
        if not sp or not os.path.isdir(sp):
            continue

        for f in os.listdir(sp):
            if not f.endswith('.pth'):
                continue

            pth_path = os.path.join(sp, f)
            try:
                with open(pth_path, 'r', encoding='utf-8', errors='ignore') as fp:
                    lines = fp.readlines()

                exec_lines = []
                for i, line in enumerate(lines, 1):
                    line = line.strip()
                    if line.startswith('import ') or line.startswith('import\t'):
                        exec_lines.append((i, line))
                    elif line and not line.startswith('#') and not line.startswith('/') and not line.startswith('\\'):
                        # Podría ser código ejecutable si no es un path
                        if ';' in line or '(' in line:
                            exec_lines.append((i, line[:60] + '...' if len(line) > 60 else line))

                if exec_lines:
                    found_any = True
                    print(f"\n  {pth_path}")
                    for lineno, code in exec_lines:
                        print(f"    L{lineno}: {code}")
            except Exception as e:
                print(f"  ERROR leyendo {pth_path}: {e}")

    if not found_any:
        print("  (ninguno encontrado)")


def check_site_customize():
    """Verifica sitecustomize.py y usercustomize.py."""
    print_section("SITECUSTOMIZE / USERCUSTOMIZE")

    for name in ('sitecustomize', 'usercustomize'):
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            print(f"  {name}: {spec.origin}")
        else:
            print(f"  {name}: (no existe)")


def check_signature_bootstrap():
    """Busca signature_bootstrap y su origen."""
    print_section("SIGNATURE_BOOTSTRAP")

    spec = importlib.util.find_spec('signature_bootstrap')
    if spec:
        print(f"  origin: {spec.origin}")
        print(f"  submodule_search_locations: {spec.submodule_search_locations}")
        if spec.loader:
            print(f"  loader: {type(spec.loader).__name__}")
    else:
        print("  (módulo no encontrado en sys.path)")

    # Buscar en site-packages directamente
    site_packages = site.getsitepackages() + [site.getusersitepackages()]
    for sp in site_packages:
        if not sp or not os.path.isdir(sp):
            continue
        candidate = os.path.join(sp, 'signature_bootstrap.py')
        if os.path.exists(candidate):
            print(f"  archivo encontrado: {candidate}")

        # Buscar en shiboken6 (común con PySide6)
        shiboken_path = os.path.join(sp, 'shiboken6')
        if os.path.isdir(shiboken_path):
            sig_in_shib = os.path.join(shiboken_path, 'signature_bootstrap.py')
            if os.path.exists(sig_in_shib):
                print(f"  encontrado en shiboken6: {sig_in_shib}")


def check_pyside6():
    """Verifica estado de PySide6."""
    print_section("PYSIDE6 STATUS")

    spec = importlib.util.find_spec('PySide6')
    if not spec:
        print("  PySide6: NO INSTALADO")
        return False

    print(f"  PySide6 location: {spec.origin}")

    # Verificar QtWidgets sin importar (evita crash)
    widgets_spec = importlib.util.find_spec('PySide6.QtWidgets')
    if widgets_spec:
        print(f"  QtWidgets: OK ({widgets_spec.origin})")
    else:
        print("  QtWidgets: NOT FOUND (potencial problema)")
        return False

    # Variables de entorno críticas para Qt
    qt_vars = ['QT_QPA_PLATFORM', 'QT_QPA_PLATFORM_PLUGIN_PATH',
               'QT_PLUGIN_PATH', 'DISPLAY', 'WAYLAND_DISPLAY']
    print("\n  Variables Qt:")
    for var in qt_vars:
        val = os.environ.get(var)
        if val:
            print(f"    {var}={val}")

    # Intentar import real
    print("\n  Test import PySide6.QtWidgets...")
    try:
        from PySide6 import QtWidgets
        print("    OK")
        return True
    except Exception as e:
        print(f"    FAIL: {type(e).__name__}: {e}")
        return False


def check_env_vars():
    """Variables de entorno relevantes."""
    print_section("VARIABLES DE ENTORNO RELEVANTES")

    relevant = [
        'CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'VIRTUAL_ENV',
        'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP',
        'PATH',
    ]

    for var in relevant:
        val = os.environ.get(var)
        if val:
            # Truncar PATH que suele ser muy largo
            if var == 'PATH':
                val = val[:100] + '...' if len(val) > 100 else val
            print(f"  {var}={val}")


def check_repo_mentions():
    """Busca menciones de signature_bootstrap en el repo."""
    print_section("MENCIONES EN REPO (signature_bootstrap)")

    repo_root = Path(__file__).parent.parent
    found = []

    for ext in ('*.py', '*.pth', '*.cfg', '*.ini', '*.txt'):
        for f in repo_root.rglob(ext):
            # Skip node_modules y venv
            if 'node_modules' in str(f) or 'venv' in str(f) or '.git' in str(f):
                continue
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                if 'signature_bootstrap' in content:
                    found.append(str(f))
            except:
                pass

    if found:
        for f in found:
            print(f"  {f}")
    else:
        print("  (ninguna mención encontrada)")


def run_diagnostics():
    """Ejecuta todos los diagnósticos."""
    print("\n" + "="*60)
    print(" 911 FIESTA - DIAGNÓSTICO DE ARRANQUE")
    print("="*60)

    check_python_env()
    check_site_customize()
    find_pth_files_with_exec()
    check_signature_bootstrap()
    check_repo_mentions()
    check_env_vars()
    pyside_ok = check_pyside6()

    # Resumen final
    print_section("RESUMEN")

    issues = []

    # Verificar signature_bootstrap
    spec = importlib.util.find_spec('signature_bootstrap')
    if spec and spec.origin:
        issues.append(f"signature_bootstrap activo: {spec.origin}")

    if not pyside_ok:
        issues.append("PySide6.QtWidgets no carga correctamente")

    if issues:
        print("  STATUS: FAIL")
        print("\n  Problemas detectados:")
        for issue in issues:
            print(f"    - {issue}")
        print("\n  Soluciones sugeridas:")
        print("    1. Si signature_bootstrap falla, es un problema del entorno conda")
        print("    2. Reinstalar PySide6: pip uninstall pyside6 shiboken6 && pip install pyside6")
        print("    3. Verificar que conda activate ohfiesta911 funciona")
        return False
    else:
        print("  STATUS: OK")
        print("  El entorno está configurado correctamente.")
        return True


if __name__ == '__main__':
    success = run_diagnostics()
    sys.exit(0 if success else 1)
