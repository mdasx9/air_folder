"""
Migration: add the logged_at provenance column to events and room_states.

logged_at is always the server clock at insert time. For live labels it
matches start_time / changed_at; for retroactive labels it differs, which
is how recalled labels can be identified later (e.g. to check whether the
classifier behaves differently on them).

Existing rows were all logged live, so their logged_at is backfilled from
start_time / changed_at. Safe to run more than once.

Run from the project folder:
    py migrate_add_logged_at.py
"""

import sqlite3

from config import DATABASE_PATH


def add_column(conn, table, backfill_from):

    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]

    if "logged_at" in columns:
        print(f"{table}: logged_at already present — nothing to do.")
        return

    conn.execute(f"ALTER TABLE {table} ADD COLUMN logged_at TEXT")
    conn.execute(f"UPDATE {table} SET logged_at = {backfill_from} WHERE logged_at IS NULL")
    conn.commit()

    filled = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE logged_at IS NOT NULL").fetchone()[0]
    print(f"{table}: logged_at added, {filled} existing rows backfilled from {backfill_from}.")


def main():

    conn = sqlite3.connect(str(DATABASE_PATH))

    add_column(conn, "events", "start_time")
    add_column(conn, "room_states", "changed_at")

    conn.close()


if __name__ == "__main__":
    main()
