"""
Migration: allow 'ac' as a room_states state_type.

SQLite cannot alter a CHECK constraint in place, so the table is rebuilt
with the new constraint and existing rows are copied over unchanged.
Safe to run more than once.

Run from the project folder:
    py migrate_add_ac_state.py
"""

import sqlite3

from config import DATABASE_PATH


def main():

    conn = sqlite3.connect(str(DATABASE_PATH))

    before = conn.execute("SELECT COUNT(*) FROM room_states").fetchone()[0]

    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'room_states'"
    ).fetchone()[0]

    if "'ac'" in table_sql:
        print("room_states already allows 'ac' — nothing to do.")
        conn.close()
        return

    conn.executescript("""
    BEGIN;

    CREATE TABLE room_states_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL CHECK (room IN ('kitchen', 'living_room', 'bedroom')),
        state_type TEXT NOT NULL CHECK (state_type IN ('window', 'exhaust_fan', 'purifier', 'ac')),
        state_value TEXT NOT NULL CHECK (state_value IN ('open', 'closed', 'on', 'off')),
        changed_at TEXT NOT NULL
    );

    INSERT INTO room_states_new (id, room, state_type, state_value, changed_at)
    SELECT id, room, state_type, state_value, changed_at FROM room_states;

    DROP TABLE room_states;

    ALTER TABLE room_states_new RENAME TO room_states;

    CREATE INDEX IF NOT EXISTS ix_room_states_lookup
    ON room_states (room, state_type, changed_at);

    COMMIT;
    """)

    after = conn.execute("SELECT COUNT(*) FROM room_states").fetchone()[0]
    conn.close()

    print(f"room_states rebuilt with 'ac' allowed; rows preserved: {before} -> {after}")

    if before != after:
        raise SystemExit("Row count changed during migration — investigate before continuing.")


if __name__ == "__main__":
    main()
