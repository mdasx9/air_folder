"""
Build the public sample dataset in data/sample/ from the live database.

The sample is a short, self-contained slice that shows every structure a
reader needs to understand the project: three rooms sampling in parallel,
overlapping labelled events, room-state history, and the joined
long-format table the classifier consumes.

Anonymisation
-------------
Calendar dates are shifted to a synthetic epoch so the files do not reveal
which real days the household was doing what. Time-of-day is preserved,
because when an event happens is part of what makes the data meaningful.
Nothing else is altered - the sensor values are the real measurements.

Run from the project folder:
    py tools/make_sample_dataset.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATABASE_PATH
from dataset import build_labeled_dataset
from labels import get_connection


# A four-hour evening window containing two overlapping cooking events,
# which is what makes it a good worked example.
WINDOW_START = "2026-07-13 16:00:00"
WINDOW_END = "2026-07-13 20:00:00"

# real dates -> synthetic epoch (whole days, so clock times are unchanged)
SYNTHETIC_START_DATE = pd.Timestamp("2024-03-01")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


def _shift(series, offset):
    return pd.to_datetime(series) + offset


def main():

    window_start = pd.Timestamp(WINDOW_START)
    window_end = pd.Timestamp(WINDOW_END)

    offset = SYNTHETIC_START_DATE - window_start.normalize()

    conn = get_connection(DATABASE_PATH)

    readings = pd.read_sql_query(
        """
        SELECT timestamp, node, pm1, pm25, pm4, pm10, voc, nox, co2, temperature, humidity
        FROM sensor_data
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp
        """,
        conn,
        params=[WINDOW_START, WINDOW_END],
        parse_dates=["timestamp"],
    )

    events = pd.read_sql_query(
        """
        SELECT id AS event_id, room, event_type, subtype, start_time, end_time, notes, logged_at
        FROM events
        WHERE start_time <= ? AND (end_time IS NULL OR end_time >= ?)
        ORDER BY start_time
        """,
        conn,
        params=[WINDOW_END, WINDOW_START],
        parse_dates=["start_time", "end_time", "logged_at"],
    )

    # every state change up to the window end: the ones before the window
    # are what the as-of join needs to know the state at the start
    states = pd.read_sql_query(
        """
        SELECT room, state_type, state_value, changed_at, logged_at
        FROM room_states
        WHERE changed_at <= ?
        ORDER BY changed_at
        """,
        conn,
        params=[WINDOW_END],
        parse_dates=["changed_at", "logged_at"],
    )

    conn.close()

    labeled = build_labeled_dataset(WINDOW_START, WINDOW_END, buffer_minutes=10)

    # ---- anonymise ----
    readings["timestamp"] = _shift(readings["timestamp"], offset)
    labeled["timestamp"] = _shift(labeled["timestamp"], offset)

    for column in ("start_time", "end_time", "logged_at"):
        events[column] = _shift(events[column], offset)

    for column in ("changed_at", "logged_at"):
        states[column] = _shift(states[column], offset)

    # notes are free text a person typed; keep the column, drop the content
    events["notes"] = ""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "sample_readings.csv": readings,
        "sample_events.csv": events,
        "sample_room_states.csv": states,
        "sample_labeled_dataset.csv": labeled,
    }

    for name, frame in outputs.items():
        path = OUTPUT_DIR / name
        frame.to_csv(path, index=False)
        size_kb = path.stat().st_size / 1024
        print(f"{name:30s} {len(frame):7,} rows   {size_kb:8.1f} KB")

    print(f"\nwindow      : {window_start} -> {window_end} (real)")
    print(f"published as: {window_start + offset} -> {window_end + offset} (shifted)")
    print(f"events       : {len(events)}")
    print(f"rooms        : {readings['node'].nunique()}")

    event_rows = labeled['event_type'].notna().sum()
    print(f"labelled rows: {event_rows:,} of {len(labeled):,} "
          f"({100 * event_rows / max(len(labeled), 1):.1f}%)")


if __name__ == "__main__":
    main()
