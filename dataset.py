"""
Builds the labeled training dataset by joining sensor readings with
logged events and room states.

Output is tidy long format: one row per (reading x overlapping event),
covering ALL rooms — not just the event's source room — so downstream
feature extraction can build either the classification dataset
(source-room rows) or the transport dataset (all rooms).

Each row carries:
  - the raw sensor channels for that room at that timestamp
  - event_id / event_type / subtype of any event whose buffered window
    [start - buffer, end + buffer] contains the timestamp (NULL if none:
    these are the background / no-event class, kept on purpose)
  - role: "source" if the reading's room is the event's room, else
    "transport" (NULL for background rows)
  - window / exhaust_fan / purifier: the state active in the reading's
    OWN room at that timestamp, via a backward as-of join (NULL if that
    state had never been logged yet — unknown, not assumed)

If two events overlap the same timestamp, the reading appears once per
event rather than one label being silently dropped.

Open events (end_time still NULL) are treated as running through the end
of the requested range.
"""

import pandas as pd

from config import DATABASE_PATH, METRICS, ROOM_SLUGS, STATE_TYPES
from labels import get_connection, _normalize_timestamp


SENSOR_COLUMNS = list(METRICS.values())

EVENT_COLUMNS = ["event_id", "event_type", "subtype", "role"]

OUTPUT_COLUMNS = (
    ["timestamp", "room"]
    + SENSOR_COLUMNS
    + EVENT_COLUMNS
    + list(STATE_TYPES)
)


def _empty_dataset():

    df = pd.DataFrame(columns=OUTPUT_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df



def _load_readings(conn, start_text, end_text):

    df = pd.read_sql_query(
        f"""
        SELECT timestamp, node, {", ".join(SENSOR_COLUMNS)}
        FROM sensor_data
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp
        """,
        conn,
        params=[start_text, end_text],
        parse_dates=["timestamp"]
    )

    # slug the room so it compares directly against events.room /
    # room_states.room; unknown node names pass through untouched
    df["room"] = df["node"].map(ROOM_SLUGS).fillna(df["node"])

    return df.drop(columns=["node"])



def _load_events(conn, end_text):

    return pd.read_sql_query(
        """
        SELECT id, room, event_type, subtype, start_time, end_time
        FROM events
        WHERE start_time <= ?
        ORDER BY start_time
        """,
        conn,
        params=[end_text],
        parse_dates=["start_time", "end_time"]
    )



def _load_states(conn, end_text):

    return pd.read_sql_query(
        """
        SELECT room, state_type, state_value, changed_at
        FROM room_states
        WHERE changed_at <= ?
        ORDER BY changed_at
        """,
        conn,
        params=[end_text],
        parse_dates=["changed_at"]
    )



def _attach_events(readings, events, range_start, range_end, buffer):
    """
    One output row per (reading, overlapping event); readings that match
    no event appear exactly once with NULL event columns.
    """

    pieces = []
    matched = pd.Series(False, index=readings.index)

    for event in events.itertuples(index=False):

        event_end = event.end_time if pd.notna(event.end_time) else range_end

        window_start = event.start_time - buffer
        window_end = event_end + buffer

        if window_end < range_start or window_start > range_end:
            continue

        mask = readings["timestamp"].between(window_start, window_end)

        if not mask.any():
            continue

        chunk = readings[mask].copy()
        chunk["event_id"] = event.id
        chunk["event_type"] = event.event_type
        chunk["subtype"] = event.subtype
        chunk["role"] = (chunk["room"] == event.room).map(
            {True: "source", False: "transport"}
        )

        pieces.append(chunk)
        matched |= mask

    background = readings[~matched].copy()
    background["event_id"] = pd.NA
    background["event_type"] = None
    background["subtype"] = None
    background["role"] = None
    pieces.append(background)

    labeled = pd.concat(pieces, ignore_index=True)
    labeled["event_id"] = labeled["event_id"].astype("Int64")

    return labeled



def _attach_room_states(labeled, states):
    """
    Backward as-of join: for each reading, the most recent state change
    in its own room at or before its timestamp. Rooms with no logged
    history for a state_type get NULL (unknown).
    """

    labeled = labeled.sort_values("timestamp", kind="mergesort").reset_index(drop=True)

    for state_type in STATE_TYPES:

        changes = states[states["state_type"] == state_type]
        changes = changes[["room", "changed_at", "state_value"]]
        changes = changes.rename(columns={"state_value": state_type})
        changes = changes.sort_values("changed_at", kind="mergesort")

        if changes.empty:
            labeled[state_type] = None
            continue

        labeled = pd.merge_asof(
            labeled,
            changes,
            left_on="timestamp",
            right_on="changed_at",
            by="room",
            direction="backward",
        ).drop(columns=["changed_at"])

    return labeled



def build_labeled_dataset(start_time, end_time, buffer_minutes=10, db_path=DATABASE_PATH):
    """
    The export/join that feeds the ML pipeline.

    Parameters
    ----------
    start_time, end_time : str or datetime — range of sensor readings to return.
    buffer_minutes : minutes of context added before each event's start and
        after its end, so pre-event baseline and propagation lag are captured.

    Returns a tidy long-format DataFrame (see module docstring).
    """

    start_text = _normalize_timestamp(start_time)
    end_text = _normalize_timestamp(end_time)

    conn = get_connection(db_path)

    try:
        readings = _load_readings(conn, start_text, end_text)
        events = _load_events(conn, end_text)
        states = _load_states(conn, end_text)
    finally:
        conn.close()

    if readings.empty:
        return _empty_dataset()

    labeled = _attach_events(
        readings,
        events,
        range_start=pd.Timestamp(start_text),
        range_end=pd.Timestamp(end_text),
        buffer=pd.Timedelta(minutes=buffer_minutes),
    )

    labeled = _attach_room_states(labeled, states)

    labeled = labeled.sort_values(
        ["timestamp", "room", "event_id"],
        kind="mergesort",
    ).reset_index(drop=True)

    return labeled[OUTPUT_COLUMNS]
