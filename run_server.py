"""Server entry point to launch the Bankism AI Firewall & SOC Dashboard."""

import uvicorn
import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


import threading
import time
import webbrowser


def main():
    print("=" * 70)
    print("🛡️  BANKISM: BLUE-TEAM DEFENSIVE AI FIREWALL FOR CORE BANKING")
    print("=" * 70)
    print("• SOC Dashboard: http://127.0.0.1:8000")
    print("• OpenAPI Docs:  http://127.0.0.1:8000/docs")
    print("• Core Banking Ledger & 5-Layer Defense Active")
    print("=" * 70)

    # Launch browser automatically once server starts
    def _open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open("http://127.0.0.1:8000")
        except Exception:
            pass

    threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "bankism.soc.dashboard_api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
