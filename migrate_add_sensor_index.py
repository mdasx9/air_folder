"""
Migration: index sensor_data for the queries the dashboard actually runs.

Every dashboard page filters by node and/or timestamp. Without an index
SQLite scans the whole table each time, which gets slower every day the
sensors run. This adds:

  (node, timestamp) - room + time range filters (most pages)
  (timestamp)       - time range across all rooms (export/join)

Indexes cost disk and a little insert time; at 0.6 inserts/second that
tradeoff is heavily in our favour. Safe to run more than once.

Run from the project folder:
    py migrate_add_sensor_index.py
"""

import sqlite3
import time

from config import DATABASE_PATH


def main():

    conn = sqlite3.connect(str(DATABASE_PATH))

    rows = conn.execute("SELECT COUNT(*) FROM sensor_data").fetchone()[0]
    print(f"sensor_data rows: {rows:,}")

    started = time.perf_counter()

    conn.executescript("""
    CREATE INDEX IF NOT EXISTS ix_sensor_node_time
    ON sensor_data (node, timestamp);

    CREATE INDEX IF NOT EXISTS ix_sensor_time
    ON sensor_data (timestamp);
    """)
    conn.commit()

    conn.execute("ANALYZE")
    conn.commit()

    elapsed = time.perf_counter() - started

    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'sensor_data'"
        )
    ]

    conn.close()

    print(f"indexes present: {', '.join(names)}")
    print(f"built in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
