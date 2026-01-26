#!/usr/bin/env python3
"""
Smoke Test - SERVER Runtime (911 Fiesta V7)

Valida que todas las dependencias del servidor FastAPI estan instaladas.
Exit code 0 = OK, Exit code 1 = FAIL

Uso:
    python scripts/smoke_server.py
"""
import sys
import os

# Track results
results = []
failed = False


def check(name: str, test_func):
    """Run a test and record result."""
    global failed
    try:
        result = test_func()
        if result:
            print(f"[OK] {name}: {result}")
            results.append((name, "OK", result))
        else:
            print(f"[OK] {name}")
            results.append((name, "OK", ""))
    except ImportError as e:
        print(f"[FAIL] {name}: ImportError - {e}")
        results.append((name, "FAIL", str(e)))
        failed = True
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__} - {e}")
        results.append((name, "FAIL", str(e)))
        failed = True


def main():
    global failed

    print("=" * 60)
    print("SMOKE TEST - 911 Fiesta V7 SERVER Runtime")
    print("=" * 60)
    print()

    # === FastAPI Stack ===
    print("--- FastAPI Stack ---")

    def check_fastapi():
        import fastapi
        from fastapi import FastAPI, APIRouter, Depends, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        return fastapi.__version__
    check("fastapi", check_fastapi)

    def check_uvicorn():
        import uvicorn
        return uvicorn.__version__
    check("uvicorn", check_uvicorn)

    def check_pydantic():
        import pydantic
        from pydantic import BaseModel, Field
        return pydantic.__version__
    check("pydantic", check_pydantic)

    def check_starlette():
        import starlette
        return starlette.__version__
    check("starlette", check_starlette)

    # === Core Scientific ===
    print("\n--- Core Scientific ---")

    check("numpy", lambda: __import__("numpy").__version__)

    # === OpenCV Headless ===
    print("\n--- OpenCV ---")

    def check_opencv():
        import cv2
        # Check if it's headless (no GUI functions)
        headless = not hasattr(cv2, 'imshow') or 'headless' in cv2.__file__.lower()
        variant = "headless" if headless else "full"
        return f"{cv2.__version__} ({variant})"
    check("cv2 (OpenCV)", check_opencv)

    # === Network ===
    print("\n--- Network ---")

    check("requests", lambda: __import__("requests").__version__)

    # === Utilities ===
    print("\n--- Utilities ---")

    check("python-dotenv", lambda: __import__("dotenv").__version__)
    check("typing_extensions", lambda: __import__("typing_extensions").__version__)

    # === API Module Check ===
    print("\n--- API Modules (import check) ---")

    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    def check_api_main():
        from api.main import app
        # Verify app has expected routes
        routes = [r.path for r in app.routes]
        return f"FastAPI app with {len(routes)} routes"
    check("api.main", check_api_main)

    def check_api_models():
        from api import models
        # Count model classes
        model_count = sum(1 for name in dir(models)
                        if not name.startswith('_') and
                        isinstance(getattr(models, name, None), type))
        return f"{model_count} models defined"
    check("api.models", check_api_models)

    def check_api_routers():
        from api.routers import status, analyzers, cues, network, presets, config, alerts
        return "all routers imported"
    check("api.routers", check_api_routers)

    # === Quick Server Start Test ===
    print("\n--- Server Start Test ---")

    def check_server_startup():
        """Test that uvicorn can import and configure the app."""
        from api.main import app
        import uvicorn

        # Create config without starting server
        config = uvicorn.Config(
            app=app,
            host="127.0.0.1",
            port=0,  # Random port
            log_level="error"
        )
        # Just verify config is valid
        return f"uvicorn config OK (host={config.host})"
    check("uvicorn config", check_server_startup)

    # === Summary ===
    print()
    print("=" * 60)

    ok_count = sum(1 for _, status, _ in results if status == "OK")
    fail_count = sum(1 for _, status, _ in results if status == "FAIL")

    print(f"Results: {ok_count} OK, {fail_count} FAIL")
    print()

    if failed:
        print("SMOKE TEST FAILED")
        print()
        print("Failed components:")
        for name, status, msg in results:
            if status == "FAIL":
                print(f"  - {name}: {msg}")
        print()
        print("Please install missing dependencies:")
        print("  pip install -r requirements/server.lock.txt")
        sys.exit(1)
    else:
        print("SMOKE TEST PASSED")
        print()
        print("All SERVER runtime dependencies are correctly installed.")
        print()
        print("To start the server:")
        print("  uvicorn api.main:app --host 0.0.0.0 --port 8000")
        print("  # or")
        print("  python -c \"from api.main import start_api_server; start_api_server()\"")
        sys.exit(0)


if __name__ == "__main__":
    main()
