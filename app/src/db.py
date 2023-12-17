import sqlite3
import sqlite_vss


def create_db():
    """Create database"""
    db = sqlite3.connect("/app/memory.db")
    db.execute("""\
    CREATE TABLE memory using vss0(
        audio_file VARCHAR(255),
        markdown_file VARCHAR(255),
        text TEXT,
        start_time TEXT,
        embeddings TEXT);
               """)
    db.commit()
    db.execute("""\
    CREATE VIRTUAL TABLE IF NOT EXISTS
        vss_memory using vss0(embeddings(512));
               """)
    db.commit()
    db.close()