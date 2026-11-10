"""One SQLite database per study, stored inside the study folder.

The study folder is self-contained (database, audio copies, reports), so it
can be zipped and handed to an examiner.
"""
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from . import constants

SCHEMA = """
CREATE TABLE IF NOT EXISTS study (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created REAL,
    constants TEXT NOT NULL,
    locked INTEGER DEFAULT 0,
    citation_style TEXT DEFAULT 'APA'
);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    tradition TEXT DEFAULT '',
    role TEXT DEFAULT 'study',          -- study | archival | test
    color TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS singers (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT DEFAULT '',
    voice_type TEXT DEFAULT '',         -- male | female | other
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    code TEXT,
    filename TEXT,
    stored_name TEXT,
    sha256 TEXT,
    meta TEXT DEFAULT '{}',
    qc TEXT DEFAULT '{}',
    qc_status TEXT DEFAULT 'pending',   -- pass | flag | reject | pending
    duration REAL,
    tonic_hz REAL,
    tonic_method TEXT,
    tonic_confirmed INTEGER DEFAULT 0,
    prepared INTEGER DEFAULT 0,
    separated INTEGER DEFAULT 0,
    created REAL
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    sample_id INTEGER REFERENCES samples(id) ON DELETE CASCADE,
    start REAL NOT NULL,
    end REAL NOT NULL,
    kind TEXT DEFAULT 'phrase',         -- phrase | vowel | rhythm
    section TEXT DEFAULT 'free',        -- free | metred
    singer_id INTEGER REFERENCES singers(id),
    vowel TEXT DEFAULT '',
    label TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    excluded INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY,
    sample_id INTEGER REFERENCES samples(id) ON DELETE CASCADE,
    t REAL NOT NULL,
    kind TEXT DEFAULT 'cycle',          -- cycle | beat
    source TEXT DEFAULT 'manual'        -- manual | proposed
);
CREATE TABLE IF NOT EXISTS ornaments (
    id INTEGER PRIMARY KEY,
    segment_id INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    start REAL, end REAL,
    rate_hz REAL, extent_cents REAL, regularity REAL,
    auto_label TEXT, final_label TEXT, reviewed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started REAL, finished REAL,
    versions TEXT, constants_hash TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    segment_id INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    feature TEXT, value REAL, unit TEXT
);
CREATE INDEX IF NOT EXISTS ix_results ON results(run_id, segment_id);
CREATE TABLE IF NOT EXISTS bias (
    id INTEGER PRIMARY KEY,
    feature TEXT UNIQUE, mean_shift REAL, sd_shift REAL, n INTEGER, unit TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    segment_id INTEGER REFERENCES segments(id) ON DELETE CASCADE,
    sample_id INTEGER REFERENCES samples(id) ON DELETE CASCADE,
    kind TEXT DEFAULT 'musicological',  -- musicological | listening | expert
    text TEXT, created REAL
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY, t REAL, action TEXT, detail TEXT
);
"""


def slugify(name):
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return s[:60] or "study"


class Study:
    """Thread-safe wrapper around one study folder."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.dbpath = self.folder / "study.db"
        for sub in ("audio/original", "audio/measure", "audio/guide", "audio/stems", "reports", "cache"):
            (self.folder / sub).mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.dbpath, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------- generic ----------
    def q(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def ex(self, sql, args=()):
        with self._lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def exmany(self, sql, rows):
        with self._lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def log(self, action, detail=""):
        if not isinstance(detail, str):
            detail = json.dumps(detail, ensure_ascii=False)
        self.ex("INSERT INTO log(t, action, detail) VALUES (?,?,?)", (time.time(), action, detail))

    # ---------- study ----------
    def init(self, name, description=""):
        if not self.one("SELECT id FROM study"):
            self.ex("INSERT INTO study(id, name, description, created, constants) VALUES (1,?,?,?,?)",
                    (name, description, time.time(), json.dumps(constants.defaults())))
            self.log("study.create", name)

    def info(self):
        s = self.one("SELECT * FROM study WHERE id=1")
        if s:
            s["constants"] = json.loads(s["constants"])
        return s

    def constants(self):
        return self.info()["constants"]

    def close(self):
        with self._lock:
            self.conn.close()


def sample_row(s):
    if not s:
        return s
    for k in ("meta", "qc"):
        if isinstance(s.get(k), str):
            try:
                s[k] = json.loads(s[k])
            except Exception:
                s[k] = {}
    return s
