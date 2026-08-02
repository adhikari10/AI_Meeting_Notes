# -*- mode: python ; coding: utf-8 -*-
#
# app.spec — PyInstaller spec for Meeting Notes AI
#
# Build command (run from repo root, with your venv active):
#   pyinstaller app.spec
#
# Output: dist/MeetingNotesAI/MeetingNotesAI.exe  (one-folder bundle)

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT    = Path(SPECPATH)               # repo root (where this .spec lives)
WEBAPP  = ROOT / 'meeting_notes_webapp'
BACKEND = ROOT / 'backend'

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / 'launcher.py')],

    pathex=[
        str(ROOT),
        str(WEBAPP),    # so PyInstaller finds the `app` module
        str(BACKEND),   # so PyInstaller finds `simple_speaker_detection`
    ],

    binaries=[
        # Uncomment if you have a local ffmpeg.exe to ship with the bundle:
        # (str(ROOT / 'ffmpeg.exe'), '.'),
    ],

    datas=[
        # Flask templates and static assets
        (str(WEBAPP / 'templates'), 'templates'),
        (str(WEBAPP / 'static'),    'static'),

        # .env template for first-run setup
        (str(ROOT / '.env.example'), '.'),

        # whisper ships mel filterbank and other data files
        *collect_data_files('whisper'),

        # pywebview ships HTML/JS/CSS helper assets
        *collect_data_files('webview'),

        # NOTE: app.py and simple_speaker_detection.py are NOT added here.
        # Adding .py source files to datas when PyInstaller already compiles
        # them as modules causes C-extension double-load errors (numpy, torch).
        # They are picked up automatically via pathex + Analysis import tracing.
    ],

    hiddenimports=[
        # ── Flask / SocketIO ──────────────────────────────────────────────
        'flask',
        'flask.templating',
        'flask.json',
        'flask_socketio',
        'flask_cors',

        # Both async driver names are required by python-socketio / python-engineio
        'engineio.async_drivers.threading',
        'socketio.async_drivers.threading',

        # ── Audio ────────────────────────────────────────────────────────
        'pyaudiowpatch',
        'pyaudio',
        'numpy',
        'scipy',
        'scipy.signal',
        'scipy.io',
        'scipy.io.wavfile',

        # ── Whisper / faster-whisper ─────────────────────────────────────
        *collect_submodules('whisper'),
        'faster_whisper',

        # ── AI / API ─────────────────────────────────────────────────────
        'openai',
        'groq',

        # ── python-dotenv — all submodules required in frozen bundle ─────
        'dotenv',
        'dotenv.main',
        'dotenv.compat',
        'dotenv.parser',
        'dotenv.variables',
        'dotenv.version',

        # ── Speaker detection ─────────────────────────────────────────────
        'resemblyzer',
        'simple_speaker_detection',

        # ── Optional extras (graceful fallback if missing) ────────────────
        'webrtcvad',
        'noisereduce',
        'yt_dlp',
        'transformers',

        # ── pywebview (Windows uses the WinForms backend) ─────────────────
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.cef',
        'clr',          # pythonnet — required by pywebview WinForms backend

        # ── pkg_resources ────────────────────────────────────────────────
        'pkg_resources',
        'pkg_resources.extern',
        'pkg_resources.py2_warn',

        # ── stdlib bits PyInstaller sometimes misses ──────────────────────
        'email.mime.multipart',
        'email.mime.text',
        'logging.handlers',
        'queue',
        'ctypes',
        'ctypes.wintypes',
    ],

    # Keep the bundle lean — these are never needed at runtime
    excludes=[
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'PIL._tkinter_finder',
        'pydoc',
        'xmlrpc',
    ],

    noarchive=False,
    optimize=1,
)

# ── PYZ ───────────────────────────────────────────────────────────────────────
pyz = PYZ(a.pure)

# ── EXE ───────────────────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,      # one-folder mode: binaries land in COLLECT
    name='MeetingNotesAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,               # ← keeps a console window so startup errors are visible
    icon=str(ROOT / 'icon.ico') if (ROOT / 'icon.ico').exists() else None,
)

# ── COLLECT ───────────────────────────────────────────────────────────────────
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MeetingNotesAI',      # → dist/MeetingNotesAI/
)
