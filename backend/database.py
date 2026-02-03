import sqlite3
import json
from datetime import datetime

class MeetingDatabase:
    def __init__(self, db_path="meetings.db"):
        self.conn = sqlite3.connect(db_path)
        self.create_tables()
        
    def create_tables(self):
        """Create database tables if they don't exist"""
        cursor = self.conn.cursor()
        
        # Meetings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id TEXT UNIQUE,
                title TEXT,
                start_time TEXT,
                end_time TEXT,
                participants TEXT,
                raw_transcript TEXT,
                analysis_json TEXT,
                created_at TEXT
            )
        ''')
        
        # Live notes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS live_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id TEXT,
                timestamp TEXT,
                speaker TEXT,
                transcript TEXT,
                summary TEXT,
                action_items TEXT,
                decisions TEXT,
                questions TEXT
            )
        ''')
        
        self.conn.commit()
        
    def save_live_note(self, meeting_id, note):
        """Save a live analysis note"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO live_notes 
            (meeting_id, timestamp, speaker, transcript, summary, action_items, decisions, questions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            meeting_id,
            note.timestamp,
            note.speaker,
            note.text,
            note.summary,
            json.dumps(note.action_items),
            json.dumps(note.decisions),
            json.dumps(note.questions)
        ))
        self.conn.commit()
        
    def save_final_meeting(self, meeting_id, title, analysis):
        """Save final meeting analysis"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO meetings 
            (meeting_id, title, end_time, analysis_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            meeting_id,
            title,
            datetime.now().isoformat(),
            json.dumps(analysis),
            datetime.now().isoformat()
        ))
        self.conn.commit()
        
    def close(self):
        """Close database connection"""
        self.conn.close()