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

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,   -- badge / officer number; becomes operator_id
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('officer', 'admin')),
    active INTEGER NOT NULL DEFAULT 1,
    must_change INTEGER NOT NULL DEFAULT 0,
    created_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    username TEXT NOT NULL,
    success INTEGER NOT NULL,
    ip TEXT,
    note TEXT
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


def neighbour_ids(record_id, path=None, owner=None):
    """Previous/next record ids for navigation, optionally only among one operator's records."""
    extra, args = ("", ()) if not owner else (" AND operator_id=?", (owner,))
    conn = connect(path)
    try:
        p = conn.execute("SELECT MAX(id) FROM records WHERE id<?" + extra, (record_id,) + args).fetchone()[0]
        n = conn.execute("SELECT MIN(id) FROM records WHERE id>?" + extra, (record_id,) + args).fetchone()[0]
        return p, n
    finally:
        conn.close()


def previous_hash_for(prev_record):
    return hashing.recompute_hash(prev_record) if prev_record else hashing.GENESIS_HASH


def list_records(operator=None, outcome=None, date_from=None, date_to=None, path=None, owner=None):
    """owner: restrict to records whose operator_id equals this exactly (officer view)."""
    q, args = "SELECT * FROM records WHERE 1=1", []
    if owner:
        q += " AND operator_id=?"
        args.append(owner)
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


# --- users and login audit -------------------------------------------------
def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_user(username, display_name, password_hash, role, must_change=False, path=None):
    conn = connect(path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, must_change, created_utc) "
            "VALUES (?,?,?,?,?,?)",
            (username, display_name, password_hash, role, int(must_change), _now()))
        return cur.lastrowid
    finally:
        conn.close()


def get_user(user_id=None, username=None, path=None):
    conn = connect(path)
    try:
        if user_id is not None:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users(path=None):
    conn = connect(path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY username")]
    finally:
        conn.close()


def update_user(user_id, path=None, **cols):
    allowed = {"password_hash", "active", "must_change", "role", "display_name"}
    if not cols or not set(cols) <= allowed:
        raise ValueError("bad columns")
    conn = connect(path)
    try:
        conn.execute(f"UPDATE users SET {', '.join(k + '=?' for k in cols)} WHERE id=?",
                     list(cols.values()) + [user_id])
    finally:
        conn.close()


def count_active_admins(path=None):
    conn = connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
    finally:
        conn.close()


def log_login_event(username, success, ip, note="", path=None):
    conn = connect(path)
    try:
        conn.execute("INSERT INTO login_events (ts, username, success, ip, note) VALUES (?,?,?,?,?)",
                     (_now(), username[:64], int(success), ip, note))
    finally:
        conn.close()


def recent_failures(username, since_ts, path=None):
    """Failed logins for `username` since `since_ts`, ignoring anything before its last success."""
    conn = connect(path)
    try:
        last_ok = conn.execute(
            "SELECT COALESCE(MAX(id),0) FROM login_events WHERE username=? COLLATE NOCASE AND success=1",
            (username,)).fetchone()[0]
        return conn.execute(
            "SELECT COUNT(*) FROM login_events WHERE username=? COLLATE NOCASE AND success=0 "
            "AND ts>=? AND id>?", (username, since_ts, last_ok)).fetchone()[0]
    finally:
        conn.close()


def list_login_events(limit=50, path=None):
    conn = connect(path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM login_events ORDER BY id DESC LIMIT ?", (limit,))]
    finally:
        conn.close()
