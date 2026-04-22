"""
run_app.py - Run the Flask app embedded in a native window using pywebview.

Usage:
  python run_app.py

Notes:
- Requires `pywebview` package (pip install pywebview).
- This still starts a local Flask server but embeds it in a native window, so
  users don't have to open a browser and the app feels like a desktop app.
- For a single-file distributable, you can package this with PyInstaller.
"""

import socket
import threading
import time
import sys

try:
    import webview
except Exception:
    webview = None
    # Attempt to auto-install pywebview when missing (helpful for end-users)
    try:
        import subprocess
        print("pywebview not found; attempting to install required packages...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "hub\\requirements.txt"])
        # re-import
        import importlib
        webview = importlib.import_module('webview')
        print("pywebview installed successfully.")
    except Exception as ie:
        print("Automatic installation failed:", ie)
        webview = None

# Import the Flask app module
try:
    import hub.app as app_module
except Exception as e:
    print("Failed to import hub.app:", e)
    sys.exit(1)


def find_free_port(host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    addr, port = s.getsockname()
    s.close()
    return port


def run_server(host, port):
    # Ensure DB exists
    try:
        app_module.init_db()
    except Exception:
        pass
    # Run Flask (do not use reloader)
    app_module.app.run(host=host, port=port, debug=False, use_reloader=False)


def main():
    host = "127.0.0.1"
    port = find_free_port(host)
    url = f"http://{host}:{port}"

    if webview is None:
        print("pywebview is not installed. Install it with: pip install pywebview")
        print(f"You can still run the server directly: python hub\\app.py --host {host} --port {port}")
        sys.exit(1)

    server_thread = threading.Thread(target=run_server, args=(host, port), daemon=True)
    server_thread.start()

    # Wait a short while for the server to start
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.2)

    window = webview.create_window("Lab Equipment Manager", url, width=1200, height=800)
    webview.start()


if __name__ == "__main__":
    main()
