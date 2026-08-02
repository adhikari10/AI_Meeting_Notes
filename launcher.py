"""
launcher.py — Desktop launcher for Meeting Notes AI
Starts Flask in a background thread, then opens a pywebview window.
Bundled by PyInstaller into dist/MeetingNotesAI/MeetingNotesAI.exe
"""

import os
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

# ── Resolve bundle vs dev paths ────────────────────────────────────────────────
_FROZEN = getattr(sys, 'frozen', False)

if _FROZEN:
    BUNDLE_DIR = Path(sys.executable).parent   # dist/MeetingNotesAI/
    _INTERNAL  = Path(sys._MEIPASS)            # dist/MeetingNotesAI/_internal/
    # Add ffmpeg (if shipped) and the exe dir to PATH
    os.environ['PATH'] = str(BUNDLE_DIR) + os.pathsep + str(_INTERNAL) + os.pathsep + os.environ.get('PATH', '')
    # Run from BUNDLE_DIR so .env / notes / uploads are written next to the exe
    os.chdir(str(BUNDLE_DIR))
    # _MEIPASS already on sys.path via PyInstaller bootloader, but be explicit
    if str(_INTERNAL) not in sys.path:
        sys.path.insert(0, str(_INTERNAL))
else:
    BUNDLE_DIR = Path(__file__).parent
    _INTERNAL  = BUNDLE_DIR / 'meeting_notes_webapp'
    sys.path.insert(0, str(_INTERNAL))
    sys.path.insert(0, str(BUNDLE_DIR / 'backend'))
    os.chdir(str(_INTERNAL))

# ── Error log (always written; essential for diagnosing silent exits) ──────────
LOG_PATH = BUNDLE_DIR / 'error.log'

def _log(msg: str):
    """Write a timestamped line to both stdout and error.log."""
    import datetime
    line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass   # never let logging itself crash the app

def _log_exception(label: str):
    tb = traceback.format_exc()
    _log(f"ERROR — {label}\n{tb}")


# ── Stamp the log so each run is distinguishable ───────────────────────────────
import datetime
with open(LOG_PATH, 'w', encoding='utf-8') as _f:
    _f.write(f"=== Meeting Notes AI — {datetime.datetime.now()} ===\n")
    _f.write(f"BUNDLE_DIR : {BUNDLE_DIR}\n")
    _f.write(f"_INTERNAL  : {_INTERNAL}\n")
    _f.write(f"sys.path   : {sys.path}\n")
    _f.write(f"frozen     : {_FROZEN}\n\n")


# ── Flask startup ──────────────────────────────────────────────────────────────

def start_flask():
    """Import and run the Flask/SocketIO app (blocking call)."""
    try:
        _log("Importing Flask app…")
        from app import socketio, app as flask_app
        _log("Flask app imported successfully.")
        socketio.run(
            flask_app,
            host='127.0.0.1',
            port=5000,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    except Exception:
        _log_exception("start_flask()")


def wait_for_flask(url: str = 'http://127.0.0.1:5000/', timeout: int = 60) -> bool:
    """Poll until Flask responds or timeout (seconds) elapses."""
    _log(f"Waiting for Flask at {url} (timeout={timeout}s)…")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            _log("Flask is ready.")
            return True
        except Exception:
            time.sleep(0.4)
    _log("ERROR: Flask did not respond within the timeout.")
    return False


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    # 1. Start Flask in a daemon thread
    _log("Starting Flask thread…")
    flask_thread = threading.Thread(target=start_flask, name='flask', daemon=True)
    flask_thread.start()

    if not wait_for_flask():
        _log("Aborting — Flask never started. Check the lines above for import errors.")
        # Give user a moment to read the console before the window vanishes
        time.sleep(5)
        sys.exit(1)

    # 2. Open pywebview window
    try:
        _log("Importing pywebview…")
        import webview
        _log("pywebview imported successfully.")
    except ImportError:
        _log_exception("import webview")
        time.sleep(5)
        sys.exit(1)

    icon_path = str(BUNDLE_DIR / 'icon.ico')
    if not os.path.isfile(icon_path):
        icon_path = None

    _log("Creating pywebview window…")
    webview.create_window(
        title='Meeting Notes AI',
        url='http://127.0.0.1:5000/',
        width=1200,
        height=800,
        min_size=(800, 600),
    )

    _log("Starting pywebview event loop…")
    webview.start(icon=icon_path)

    # 3. Window closed → Flask daemon thread exits with the process
    _log("Window closed — exiting.")


if __name__ == '__main__':
    try:
        main()
    except Exception:
        _log_exception("main()")
        time.sleep(8)   # keep console open so user can read the error
        sys.exit(1)
