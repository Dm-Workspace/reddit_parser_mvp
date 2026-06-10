#!/usr/bin/env python3
"""
Trend Intelligence Hub — API server entry point.

Run locally:
    python main_api.py

Or via uvicorn:
    uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn[standard]")
        sys.exit(1)

    port = int(os.environ.get("PORT", 8000))
    reload = os.environ.get("ENV", "").lower() not in ("production", "railway")

    print(f"Starting Trend Intelligence Hub API on port {port}")
    print(f"   Docs: http://localhost:{port}/docs")
    print(f"   Mini App: http://localhost:{port}/webapp")
    print(f"   Status: http://localhost:{port}/api/status")

    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
    )
