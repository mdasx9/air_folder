# Migrations

Schema changes, applied in order. Every script is **idempotent** — running
it twice is safe and does nothing the second time — so re-running the full
set is always a valid way to bring a database up to date.

Run from the project root:

```bash
py migrations/migrate_add_labels.py
py migrations/migrate_add_logged_at.py
py migrations/migrate_add_ac_state.py
py migrations/migrate_add_sensor_index.py
py migrations/migrate_enable_wal.py
```

| Script | What it does |
|---|---|
| `migrate_add_labels.py` | Creates `events` and `room_states`, plus the partial unique index that forbids duplicate open events |
| `migrate_add_logged_at.py` | Adds the `logged_at` provenance column to both label tables and backfills existing rows |
| `migrate_add_ac_state.py` | Widens the `state_type` constraint to allow `ac` (rebuilds the table, preserving rows) |
| `migrate_add_sensor_index.py` | Indexes `sensor_data` on `(node, timestamp)` and `(timestamp)` |
| `migrate_enable_wal.py` | Switches the database to WAL so readers and writers stop blocking each other |

`server.py` creates the `sensor_data` table and its indexes on startup, so
a brand-new install only needs the label migrations.

## Why WAL matters

Before `migrate_enable_wal.py`, a long dashboard query held a lock on the
whole database file and the ingestion server's inserts would time out —
**silently dropping sensor readings**, measured at roughly 20% loss during
one heavy-query hour. WAL keeps writes in a separate log so reads and
writes no longer block each other. It is a persistent property of the
database file, so it only needs applying once.
