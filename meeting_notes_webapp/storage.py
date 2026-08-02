"""Note storage layer.

Two backends behind one interface:
  - PostgresStorage — used when DATABASE_URL is set (cloud deployments;
    Render wipes the filesystem on redeploy, so notes can't live on disk).
  - JSONFileStorage — used otherwise, preserving the exact on-disk
    behaviour app.py used before this layer existed. The desktop build
    never sets DATABASE_URL, so it keeps working unchanged.

This module only provides storage — nothing in app.py calls into it yet.
"""

import json
import os
import sys
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, String, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Dynamic paths — mirrors app.py so the JSON backend's default notes
# folder matches app.py's NOTES_FOLDER exactly, including in the
# PyInstaller one-folder desktop bundle. ──────────────────────────────
_FROZEN = getattr(sys, 'frozen', False)
if _FROZEN:
    _BASE_DIR = Path(sys.executable).parent
else:
    _BASE_DIR = Path(__file__).parent

Base = declarative_base()


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True)
    title = Column(String)
    timestamp = Column(String)
    source = Column(String)
    # Holds a formatted string on the upload path, an int (seconds) on the
    # URL path, and is absent on the live path — JSONB stores whichever it
    # actually is instead of forcing a lossy cast to a single type.
    duration = Column(JSONB)
    payload = Column(JSONB)


class NoteStorage(ABC):
    """Interface both backends implement. Signatures/return shapes match
    what the original JSON-file code in app.py produced, so callers can be
    switched over with no other changes."""

    @abstractmethod
    def save_note(self, data: dict, source_type: str) -> str:
        ...

    @abstractmethod
    def list_notes(self) -> list:
        ...

    @abstractmethod
    def get_note(self, note_id: str):
        ...

    @abstractmethod
    def delete_note(self, note_id: str) -> bool:
        ...


class JSONFileStorage(NoteStorage):
    """Preserves the exact on-disk behaviour of the original
    MeetingAssistant.save_notes() / NOTES_FOLDER route handlers."""

    def __init__(self, notes_folder):
        self.notes_folder = Path(notes_folder)
        self.notes_folder.mkdir(exist_ok=True)

    def save_note(self, data: dict, source_type: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_id = f"meeting_{source_type}_{timestamp}"
        filepath = self.notes_folder / f"{note_id}.json"

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return note_id

    def list_notes(self) -> list:
        notes = []
        for note_file in self.notes_folder.glob('*.json'):
            try:
                with open(note_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"Error reading note {note_file}: {e}")
                continue

            notes.append({
                'id': note_file.stem,
                'title': data.get('title', note_file.stem),
                'timestamp': data.get('timestamp', ''),
                'source': data.get('source', 'unknown'),
                'duration': data.get('duration'),
            })

        notes.sort(key=lambda n: n['timestamp'], reverse=True)
        return notes

    def get_note(self, note_id: str):
        filepath = self.notes_folder / f"{note_id}.json"
        if not filepath.exists():
            return None

        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    def delete_note(self, note_id: str) -> bool:
        filepath = self.notes_folder / f"{note_id}.json"
        if not filepath.exists():
            return False

        filepath.unlink()
        return True


class PostgresStorage(NoteStorage):
    def __init__(self, database_url: str):
        self.engine = create_engine(_normalize_db_url(database_url))
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_note(self, data: dict, source_type: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        note_id = f"meeting_{source_type}_{timestamp}"

        session = self.Session()
        try:
            if session.get(Note, note_id) is not None:
                # Same-second collision — make it unique instead of
                # overwriting the earlier note.
                note_id = f"{note_id}_{uuid.uuid4().hex[:8]}"

            note = Note(
                id=note_id,
                title=data.get('title'),
                timestamp=data.get('timestamp', ''),
                source=data.get('source', source_type),
                duration=data.get('duration'),
                payload=data,
            )
            session.add(note)
            session.commit()
            return note_id
        finally:
            session.close()

    def list_notes(self) -> list:
        session = self.Session()
        try:
            rows = session.query(Note).all()
            notes = [
                {
                    'id': n.id,
                    'title': n.title if n.title is not None else n.id,
                    'timestamp': n.timestamp or '',
                    'source': n.source or 'unknown',
                    'duration': n.duration,
                }
                for n in rows
            ]
            notes.sort(key=lambda n: n['timestamp'], reverse=True)
            return notes
        finally:
            session.close()

    def get_note(self, note_id: str):
        session = self.Session()
        try:
            note = session.get(Note, note_id)
            return note.payload if note else None
        finally:
            session.close()

    def delete_note(self, note_id: str) -> bool:
        session = self.Session()
        try:
            note = session.get(Note, note_id)
            if note is None:
                return False
            session.delete(note)
            session.commit()
            return True
        finally:
            session.close()


def _normalize_db_url(url: str) -> str:
    # Render (and some other hosts) hand out "postgres://", but SQLAlchemy's
    # default dialect requires "postgresql://".
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


_DATABASE_URL = os.getenv("DATABASE_URL")

if _DATABASE_URL:
    _backend = PostgresStorage(_DATABASE_URL)
else:
    _notes_folder = os.getenv("NOTES_FOLDER", str(_BASE_DIR / 'notes'))
    _backend = JSONFileStorage(_notes_folder)


def save_note(data: dict, source_type: str) -> str:
    return _backend.save_note(data, source_type)


def list_notes() -> list:
    return _backend.list_notes()


def get_note(note_id: str):
    return _backend.get_note(note_id)


def delete_note(note_id: str) -> bool:
    return _backend.delete_note(note_id)
