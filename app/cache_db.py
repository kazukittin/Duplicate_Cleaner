
import sqlite3
import os
from typing import Optional

class HashCache:
    def __init__(self, db_path: str):
        self.db_path = db_path
        if os.path.dirname(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init()

    def _init(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS files(
          path   TEXT PRIMARY KEY,
          size   INTEGER,
          mtime  REAL,
          sha256 TEXT,
          phash  TEXT,
          width  INTEGER,
          height INTEGER,
          kind   TEXT,
          noise  REAL
        );
        CREATE INDEX IF NOT EXISTS idx_prefix ON files(substr(phash,1,4));
        """ )
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(files)")}
        if "noise" not in cols:
            self.conn.execute("ALTER TABLE files ADD COLUMN noise REAL")
        if "blur" in cols:
            self.conn.execute("UPDATE files SET noise = COALESCE(noise, blur) WHERE blur IS NOT NULL")

    def get(self, path: str, size: int, mtime: float):
        cur = self.conn.execute(
            "SELECT sha256, phash, width, height, kind, noise FROM files WHERE path=? AND size=? AND mtime=?",
            (path, size, mtime)
        )
        return cur.fetchone()

    def upsert(self, path: str, size: int, mtime: float,
               sha256: str, phash: str, width: int, height: int, kind: str,
               noise: Optional[float] = None):
        self.conn.execute(
            """INSERT INTO files(path,size,mtime,sha256,phash,width,height,kind,noise)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(path) DO UPDATE SET
                     size=excluded.size,
                     mtime=excluded.mtime,
                     sha256=excluded.sha256,
                     phash=excluded.phash,
                     width=excluded.width,
                     height=excluded.height,
                     kind=excluded.kind,
                     noise=COALESCE(excluded.noise, files.noise)
            """,
            (path, size, mtime, sha256, phash, width, height, kind, noise)
        )

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.conn.commit()
        finally:
            self.conn.close()
