import sqlite3
from pathlib import Path
from config import DB_PATH

def ensure_instance_dir():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def get_connection():
    ensure_instance_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
