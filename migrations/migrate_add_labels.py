"""
Migration: add the events and room_states tables for ML training labels.

Safe to run more than once (everything is CREATE ... IF NOT EXISTS) and
does not touch the existing sensor_data table.

Run from the project folder:
    py migrate_add_labels.py
"""

import sqlite3

import sys
from pathlib import Path

# migrations live one level down; make the project modules importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATABASE_PATH
from labels import SCHEMA


def main():

    conn = sqlite3.connect(str(DATABASE_PATH))

    conn.executescript(SCHEMA)
    conn.commit()

    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ]

    conn.close()

    print(f"Database: {DATABASE_PATH}")
    print(f"Tables now present: {', '.join(tables)}")


if __name__ == "__main__":
    main()
