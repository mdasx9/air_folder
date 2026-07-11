import sqlite3

from datetime import datetime

import pandas as pd

from config import DATABASE_PATH, EVENT_TYPES, ROOM_SLUGS, STATE_TYPES


# =====================================================
# ERRORS
# =====================================================

class DuplicateOpenEventError(Exception):
    """Raised when starting an event that is already open for the same room + type."""


# =====================================================
# SCHEMA
# =====================================================

# Timestamps are stored as TEXT in the exact same "YYYY-MM-DD HH:MM:SS"
# format the Flask server uses for sensor_data, so string comparison and
# joins against sensor readings stay exact.
#
# The partial unique index is what enforces "no two open events of the
# same room + event_type": it only applies to rows where end_time IS NULL.

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT NOT NULL CHECK (room IN ('kitchen', 'living_room', 'bedroom')),
    event_type TEXT NOT NULL CHECK (event_type IN ('cooking', 'cleaning', 'candle', 'occupancy_change')),
    subtype TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    notes TEXT,
    CHECK (end_time IS NULL OR end_time >= start_time)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_events_open
ON events (room, event_type)
WHERE end_time IS NULL;

CREATE INDEX IF NOT EXISTS ix_events_start_time
ON events (start_time);

CREATE TABLE IF NOT EXISTS room_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT NOT NULL CHECK (room IN ('kitchen', 'living_room', 'bedroom')),
    state_type TEXT NOT NULL CHECK (state_type IN ('window', 'exhaust_fan', 'purifier', 'ac')),
    state_value TEXT NOT NULL CHECK (state_value IN ('open', 'closed', 'on', 'off')),
    changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_room_states_lookup
ON room_states (room, state_type, changed_at);
"""


# =====================================================
# CONNECTION
# =====================================================

def server_now():
    """Server-generated timestamp, same format as sensor_data.timestamp."""

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def get_connection(db_path=DATABASE_PATH):

    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False
    )

    conn.executescript(SCHEMA)

    return conn



def _validate_room(room):

    if room not in ROOM_SLUGS.values():
        raise ValueError(f"Unknown room '{room}'. Expected one of {sorted(ROOM_SLUGS.values())}.")



def _clean_text(value):

    if value is None:
        return None

    value = value.strip()

    return value or None



def _normalize_timestamp(value):

    if isinstance(value, str):
        value = pd.to_datetime(value)

    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")



# =====================================================
# EVENTS
# =====================================================

def start_event(room, event_type, subtype=None, notes=None, db_path=DATABASE_PATH):
    """
    Open a new event (end_time = NULL) with a server-generated start time.

    Raises DuplicateOpenEventError if an event of the same room + type
    is already open.
    """

    _validate_room(room)

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. Expected one of {EVENT_TYPES}.")

    conn = get_connection(db_path)

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO events (room, event_type, subtype, start_time, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    room,
                    event_type,
                    _clean_text(subtype),
                    server_now(),
                    _clean_text(notes),
                )
            )

        return cursor.lastrowid

    except sqlite3.IntegrityError as err:
        raise DuplicateOpenEventError(
            f"There is already an open '{event_type}' event in '{room}'. "
            "Stop it before starting a new one."
        ) from err

    finally:
        conn.close()



def stop_event(event_id, db_path=DATABASE_PATH):
    """
    Close an open event by setting end_time = now (server clock).

    Returns True if an open event was closed, False if the id did not
    match an open event.
    """

    conn = get_connection(db_path)

    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE events
                SET end_time = ?
                WHERE id = ? AND end_time IS NULL
                """,
                (server_now(), event_id)
            )

        return cursor.rowcount == 1

    finally:
        conn.close()



def open_events(db_path=DATABASE_PATH):

    conn = get_connection(db_path)

    df = pd.read_sql_query(
        """
        SELECT id, room, event_type, subtype, start_time, notes
        FROM events
        WHERE end_time IS NULL
        ORDER BY start_time
        """,
        conn,
        parse_dates=["start_time"]
    )

    conn.close()

    return df



def recent_events(limit=20, db_path=DATABASE_PATH):

    conn = get_connection(db_path)

    df = pd.read_sql_query(
        """
        SELECT id, room, event_type, subtype, start_time, end_time, notes
        FROM events
        ORDER BY start_time DESC
        LIMIT ?
        """,
        conn,
        params=[limit],
        parse_dates=["start_time", "end_time"]
    )

    conn.close()

    return df



# =====================================================
# ROOM STATES
# =====================================================

def set_room_state(room, state_type, state_value, db_path=DATABASE_PATH):
    """
    Record a state change for (room, state_type).

    Only inserts if the value differs from the most recent recorded value
    (or if nothing has been recorded yet). Returns True if a row was
    inserted, False if the state was already the same.
    """

    _validate_room(room)

    if state_type not in STATE_TYPES:
        raise ValueError(f"Unknown state_type '{state_type}'. Expected one of {sorted(STATE_TYPES)}.")

    if state_value not in STATE_TYPES[state_type]:
        raise ValueError(
            f"Invalid value '{state_value}' for '{state_type}'. "
            f"Expected one of {STATE_TYPES[state_type]}."
        )

    conn = get_connection(db_path)

    try:
        with conn:
            last = conn.execute(
                """
                SELECT state_value
                FROM room_states
                WHERE room = ? AND state_type = ?
                ORDER BY changed_at DESC, id DESC
                LIMIT 1
                """,
                (room, state_type)
            ).fetchone()

            if last is not None and last[0] == state_value:
                return False

            conn.execute(
                """
                INSERT INTO room_states (room, state_type, state_value, changed_at)
                VALUES (?, ?, ?, ?)
                """,
                (room, state_type, state_value, server_now())
            )

        return True

    finally:
        conn.close()



def current_room_states(db_path=DATABASE_PATH):
    """Latest recorded value for every (room, state_type) pair that has history."""

    conn = get_connection(db_path)

    df = pd.read_sql_query(
        """
        SELECT room, state_type, state_value, changed_at
        FROM (
            SELECT
                room, state_type, state_value, changed_at,
                ROW_NUMBER() OVER (
                    PARTITION BY room, state_type
                    ORDER BY changed_at DESC, id DESC
                ) AS row_num
            FROM room_states
        )
        WHERE row_num = 1
        ORDER BY room, state_type
        """,
        conn,
        parse_dates=["changed_at"]
    )

    conn.close()

    return df



def state_as_of(room, state_type, timestamp, db_path=DATABASE_PATH):
    """
    The state value active at a given timestamp: the most recent change
    at or before it. Returns None if nothing had been recorded yet —
    the state is genuinely unknown, not assumed.
    """

    _validate_room(room)

    if state_type not in STATE_TYPES:
        raise ValueError(f"Unknown state_type '{state_type}'. Expected one of {sorted(STATE_TYPES)}.")

    conn = get_connection(db_path)

    row = conn.execute(
        """
        SELECT state_value
        FROM room_states
        WHERE room = ? AND state_type = ? AND changed_at <= ?
        ORDER BY changed_at DESC, id DESC
        LIMIT 1
        """,
        (room, state_type, _normalize_timestamp(timestamp))
    ).fetchone()

    conn.close()

    return row[0] if row else None
