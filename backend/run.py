import uvicorn
import sys
import subprocess
import os
import atexit

def start_signer_service():
    signer_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signer')
    if os.path.exists(os.path.join(signer_dir, 'index.js')):
        print("[Engine] Starting Node.js Signer Microservice...")
        proc = subprocess.Popen(["node", "index.js"], cwd=signer_dir)
        atexit.register(proc.kill)
        return proc
    return None

if __name__ == "__main__":
    # Attempt uvloop optimization if available
    try:
        import uvloop
        uvloop.install()
        print("[Engine] uvloop event loop successfully installed.")
    except ImportError:
        print("[Engine] uvloop not available, defaulting to standard asyncio loop.")

    signer_proc = start_signer_service()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        ws_ping_interval=None,
    )
