"""SQLite storage (brief section 8) and chain-aware queries."""
import os
import sqlite3

import hashing

DB_PATH = os.environ.get("CHROMASEAL_DB", os.path.join(os.path.dirname(__file__), "chromaseal.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    gps_lat REAL,
    gps_lon REAL,
    gps_status TEXT NOT NULL,
    kit_profile TEXT NOT NULL,
    outcome TEXT NOT NULL,
    distance_to_target REAL,
    distance_to_blank REAL,
    margin REAL,
    fit_residual REAL,
    reject_reason TEXT,
    image_path TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL
);
"""

# Columns covered by the record hash (everything except the hash columns and id)
FIELD_COLUMNS = [
    "test_id", "operator_id", "timestamp_utc", "gps_lat", "gps_lon", "gps_status",
    "kit_profile", "outcome", "distance_to_target", "distance_to_blank", "margin",
    "fit_residual", "reject_reason", "image_path", "image_hash",
]


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path=None):
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def row_to_record(row):
    d = dict(row)
    return {
        "id": d["id"],
        "fields": {k: d[k] for k in FIELD_COLUMNS},
        "image_hash": d["image_hash"],
        "prev_hash": d["prev_hash"],
        "record_hash": d["record_hash"],
    }


def insert_record(fields, path=None):
    """Append a record to the chain. `fields` must contain FIELD_COLUMNS."""
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")  # serialise chain appends
        last = conn.execute("SELECT * FROM records ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = hashing.recompute_hash(row_to_record(last)) if last else hashing.GENESIS_HASH
        fields = {k: fields[k] for k in FIELD_COLUMNS}
        record_hash = hashing.make_record_hash(fields, prev_hash)
        cols = FIELD_COLUMNS + ["prev_hash", "record_hash"]
        cur = conn.execute(
            f"INSERT INTO records ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [fields[k] for k in FIELD_COLUMNS] + [prev_hash, record_hash])
        conn.execute("COMMIT")
        return cur.lastrowid
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def get_record(record_id, path=None):
    """Return (record, previous_record_or_None) for verification."""
    conn = connect(path)
    try:
        row = conn.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None, None
        prev = conn.execute("SELECT * FROM records WHERE id<? ORDER BY id DESC LIMIT 1",
                            (record_id,)).fetchone()
        return row_to_record(row), (row_to_record(prev) if prev else None)
    finally:
        conn.close()


def neighbour_ids(record_id, path=None):
    conn = connect(path)
    try:
        p = conn.execute("SELECT MAX(id) FROM records WHERE id<?", (record_id,)).fetchone()[0]
        n = conn.execute("SELECT MIN(id) FROM records WHERE id>?", (record_id,)).fetchone()[0]
        return p, n
    finally:
        conn.close()


def previous_hash_for(prev_record):
    return hashing.recompute_hash(prev_record) if prev_record else hashing.GENESIS_HASH


def list_records(operator=None, outcome=None, date_from=None, date_to=None, path=None):
    q, args = "SELECT * FROM records WHERE 1=1", []
    if operator:
        q += " AND operator_id LIKE ?"
        args.append(f"%{operator}%")
    if outcome:
        q += " AND outcome=?"
        args.append(outcome)
    if date_from:
        q += " AND substr(timestamp_utc,1,10)>=?"
        args.append(date_from)
    if date_to:
        q += " AND substr(timestamp_utc,1,10)<=?"
        args.append(date_to)
    q += " ORDER BY id DESC"
    conn = connect(path)
    try:
        return [dict(r) for r in conn.execute(q, args).fetchall()]
    finally:
        conn.close()


def all_records_ordered(path=None):
    conn = connect(path)
    try:
        return [row_to_record(r) for r in conn.execute("SELECT * FROM records ORDER BY id")]
    finally:
        conn.close()


def tamper_field(record_id, path=None):
    """DEMO ONLY: edit one stored field directly, bypassing the hash chain."""
    conn = connect(path)
    try:
        cur = conn.execute(
            "UPDATE records SET outcome = CASE outcome WHEN 'POSITIVE' THEN 'NEGATIVE' "
            "ELSE 'POSITIVE' END WHERE id=?", (record_id,))
        return cur.rowcount == 1
    finally:
        conn.close()
