"""
Migration: switch the database to WAL (write-ahead logging) mode.

In SQLite's default "delete" journal mode there is one lock for the whole
file, and a reader blocks every writer. The dashboard reading a few
hundred thousand rows therefore locks out the Flask server, whose insert
waits, times out, and drops that sensor reading for good.

WAL keeps writes in a separate log file, so readers and writers no longer
block each other: the dashboard can run any query it likes while sensor
data keeps landing.

journal_mode is a persistent property of the database file - setting it
once here applies to every process that opens it afterwards. Safe to run
more than once.

Run from the project folder (the Flask server can stay running):
    py migrate_enable_wal.py
"""

import sqlite3

import sys
from pathlib import Path

# migrations live one level down; make the project modules importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH


def main():

    conn = sqlite3.connect(str(DATABASE_PATH), timeout=30)

    before = conn.execute("PRAGMA journal_mode").fetchone()[0]
    print(f"journal_mode was: {before}")

    mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]

    # NORMAL is the recommended companion to WAL: still crash-safe, but
    # it stops fsyncing on every single insert
    conn.execute("PRAGMA synchronous=NORMAL")

    # cap how large the write-ahead log grows before being folded back in
    conn.execute("PRAGMA wal_autocheckpoint=1000")

    conn.commit()
    conn.close()

    print(f"journal_mode now: {mode}")

    if mode.lower() != "wal":
        raise SystemExit(
            "Could not switch to WAL. This happens if the database sits on a "
            "network drive; it must be on a local disk."
        )

    print(
        "\nDone. Readers and writers no longer block each other.\n"
        "Restart the Flask server and the dashboard so both pick up the new mode."
    )


if __name__ == "__main__":
    main()
