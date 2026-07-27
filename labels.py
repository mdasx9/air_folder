import sqlite3

from datetime import datetime, timedelta

import pandas as pd

from config import DATABASE_PATH, EVENT_TYPES, MAX_BACKDATE_DAYS, ROOM_SLUGS, STATE_TYPES


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
#
# logged_at is provenance: always the server clock at insert time. For a
# live label it matches start_time/changed_at; for a retroactive label it
# differs, so recalled labels can be identified and sanity-checked later.

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT NOT NULL CHECK (room IN ('kitchen', 'living_room', 'bedroom')),
    event_type TEXT NOT NULL CHECK (event_type IN ('cooking', 'cleaning', 'candle', 'occupancy_change')),
    subtype TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    notes TEXT,
    logged_at TEXT,
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
    changed_at TEXT NOT NULL,
    logged_at TEXT
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
        check_same_thread=False,
        timeout=30
    )

    # never let a label write fail because the dashboard is mid-query
    conn.execute("PRAGMA journal_mode=WAL")

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



def _timestamp_minutes_ago(minutes):
    """Server timestamp `minutes` in the past, bounded by the backdate cap."""

    if minutes < 0:
        raise ValueError("Minutes ago cannot be negative.")

    moment = datetime.now() - timedelta(minutes=minutes)

    return _check_bounds(moment.strftime("%Y-%m-%d %H:%M:%S"))



def _check_bounds(timestamp_text):
    """Reject timestamps in the future or absurdly far in the past."""

    moment = pd.Timestamp(timestamp_text)
    now = pd.Timestamp(server_now())

    # a second of slack absorbs the clock ticking between calls
    if moment > now + pd.Timedelta(seconds=1):
        raise ValueError(
            f"{timestamp_text} is in the future. Labels can only describe "
            "things that have already happened."
        )

    if moment < now - pd.Timedelta(days=MAX_BACKDATE_DAYS):
        raise ValueError(
            f"{timestamp_text} is more than {MAX_BACKDATE_DAYS} days ago, "
            "which is almost certainly a typo in the date."
        )

    return timestamp_text



def resolve_time(explicit=None, minutes_ago=0):
    """
    Turn either an explicit date/time or a "minutes ago" offset into a
    stored timestamp. Explicit wins when both are supplied.
    """

    if explicit is not None:
        return _check_bounds(_normalize_timestamp(explicit))

    return _timestamp_minutes_ago(minutes_ago)



# =====================================================
# EVENTS
# =====================================================

def start_event(room, event_type, subtype=None, notes=None, started_minutes_ago=0,
                start_time=None, db_path=DATABASE_PATH):
    """
    Open a new event (end_time = NULL). start_time defaults to the server
    clock; pass started_minutes_ago for something noticed late, or an
    explicit start_time (date and time) for anything older.

    Raises DuplicateOpenEventError if an event of the same room + type
    is already open.
    """

    _validate_room(room)

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. Expected one of {EVENT_TYPES}.")

    start_time = resolve_time(start_time, started_minutes_ago)

    conn = get_connection(db_path)

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO events (room, event_type, subtype, start_time, notes, logged_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    room,
                    event_type,
                    _clean_text(subtype),
                    start_time,
                    _clean_text(notes),
                    server_now(),
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



def stop_event(event_id, ended_minutes_ago=0, end_time=None, db_path=DATABASE_PATH):
    """
    Close an open event. end_time defaults to the server clock; pass
    ended_minutes_ago or an explicit end_time for events that finished
    before anyone hit Stop.

    Returns True if an open event was closed, False if the id did not
    match an open event. Raises ValueError if the end would land before
    the event's start.
    """

    end_time = resolve_time(end_time, ended_minutes_ago)

    conn = get_connection(db_path)

    try:
        with conn:
            row = conn.execute(
                "SELECT start_time FROM events WHERE id = ? AND end_time IS NULL",
                (event_id,)
            ).fetchone()

            if row is None:
                return False

            if end_time < row[0]:
                raise ValueError(
                    f"End time {end_time} is before the event started ({row[0]}). "
                    "Reduce how many minutes ago it ended."
                )

            conn.execute(
                "UPDATE events SET end_time = ? WHERE id = ? AND end_time IS NULL",
                (end_time, event_id)
            )

        return True

    finally:
        conn.close()



def log_past_event(room, event_type, started_minutes_ago=None, duration_minutes=None,
                   start_time=None, end_time=None, subtype=None, notes=None,
                   db_path=DATABASE_PATH):
    """
    Record a completed event entirely in the past (already closed, so the
    open-event constraint does not apply).

    Give either an explicit start_time and end_time (any date within the
    backdate window), or started_minutes_ago plus duration_minutes for
    something that happened earlier today.
    """

    _validate_room(room)

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. Expected one of {EVENT_TYPES}.")

    if start_time is not None or end_time is not None:

        if start_time is None or end_time is None:
            raise ValueError("Give both a start and an end date/time.")

        start_time = resolve_time(start_time)
        end_time = resolve_time(end_time)

        if end_time <= start_time:
            raise ValueError("The event must end after it starts.")

    else:

        if started_minutes_ago is None or duration_minutes is None:
            raise ValueError(
                "Give either start/end date-times, or minutes ago plus a duration."
            )

        if duration_minutes <= 0:
            raise ValueError("Duration must be at least one minute.")

        if duration_minutes > started_minutes_ago:
            raise ValueError(
                "That duration puts the end of the event in the future. "
                "For an event that is still running, use Start event instead."
            )

        start_time = _timestamp_minutes_ago(started_minutes_ago)
        end_time = _timestamp_minutes_ago(started_minutes_ago - duration_minutes)

    conn = get_connection(db_path)

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO events (room, event_type, subtype, start_time, end_time, notes, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room,
                    event_type,
                    _clean_text(subtype),
                    start_time,
                    end_time,
                    _clean_text(notes),
                    server_now(),
                )
            )

        return cursor.lastrowid

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
        SELECT id, room, event_type, subtype, start_time, end_time, notes, logged_at
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

def set_room_state(room, state_type, state_value, changed_minutes_ago=0,
                   changed_at=None, db_path=DATABASE_PATH):
    """
    Record a state change for (room, state_type), optionally backdated
    by minutes or to an explicit date and time.

    Only inserts if the value differs from the state active at that
    moment (for a live change, that is simply the latest recorded value).
    Returns True if a row was inserted, False if the state was already
    the same.
    """

    _validate_room(room)

    if state_type not in STATE_TYPES:
        raise ValueError(f"Unknown state_type '{state_type}'. Expected one of {sorted(STATE_TYPES)}.")

    if state_value not in STATE_TYPES[state_type]:
        raise ValueError(
            f"Invalid value '{state_value}' for '{state_type}'. "
            f"Expected one of {STATE_TYPES[state_type]}."
        )

    changed_at = resolve_time(changed_at, changed_minutes_ago)

    conn = get_connection(db_path)

    try:
        with conn:
            active = conn.execute(
                """
                SELECT state_value
                FROM room_states
                WHERE room = ? AND state_type = ? AND changed_at <= ?
                ORDER BY changed_at DESC, id DESC
                LIMIT 1
                """,
                (room, state_type, changed_at)
            ).fetchone()

            if active is not None and active[0] == state_value:
                return False

            conn.execute(
                """
                INSERT INTO room_states (room, state_type, state_value, changed_at, logged_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (room, state_type, state_value, changed_at, server_now())
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
