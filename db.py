import sqlite3
import threading
from datetime import datetime, timedelta

DB_PATH = "mutual_bot.db"
_db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE,
            username TEXT,
            strikes INTEGER DEFAULT 0,
            paused INTEGER DEFAULT 0,
            last_active TIMESTAMP,
            banned_until TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            thumbnail_file_id TEXT,
            duration INTEGER,
            yt_link TEXT,
            uploaded_at TIMESTAMP,
            active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            assigned_to INTEGER,
            assigned_at TIMESTAMP,
            proof_file_id TEXT,
            proof_uploaded_at TIMESTAMP,
            verified INTEGER DEFAULT 0,
            verification_result TEXT,
            verification_at TIMESTAMP,
            reviewer_msg TEXT,
            reviewer_id INTEGER,
            expired INTEGER DEFAULT 0,
            FOREIGN KEY (video_id) REFERENCES videos (id),
            FOREIGN KEY (assigned_to) REFERENCES users (id)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT,
            user_id INTEGER,
            details TEXT,
            created_at TIMESTAMP
        )""")
        conn.commit()
        conn.close()

def add_log(event, user_id, details):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO logs (event, user_id, details, created_at) VALUES (?, ?, ?, ?)",
                  (event, user_id, details, datetime.utcnow()))
        conn.commit()
        conn.close()

def remove_expired_tasks_and_proofs():
    """Deletes expired or unused proofs and tasks daily."""
    now = datetime.utcnow()
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        # Mark tasks as expired if more than 4 hours passed since proof upload and not verified
        c.execute("""
            UPDATE tasks SET expired=1 WHERE proof_uploaded_at IS NOT NULL AND verified=0 
            AND expired=0 AND proof_uploaded_at <= ?
        """, ((now - timedelta(hours=4)).isoformat(),))
        conn.commit()
        conn.close()