"""
Unit tests for the labeling layer and the ML export join.

Run from the project folder:
    py -m unittest discover -s tests -v

Each test gets its own throwaway SQLite file, so the real
air_quality.db is never touched.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import labels
from dataset import build_labeled_dataset


SENSOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    node TEXT,
    pm1 REAL, pm25 REAL, pm4 REAL, pm10 REAL,
    voc REAL, nox REAL, co2 REAL,
    temperature REAL, humidity REAL
)
"""


class LabelsTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "test.db"

        conn = sqlite3.connect(self.db)
        conn.executescript(SENSOR_SCHEMA)
        conn.executescript(labels.SCHEMA)
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    # ---------- helpers ----------

    def insert_reading(self, timestamp, node, pm25=5.0):
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            INSERT INTO sensor_data
                (timestamp, node, pm1, pm25, pm4, pm10, voc, nox, co2, temperature, humidity)
            VALUES (?, ?, 1.0, ?, 1.0, 1.0, 100.0, 1.0, 500.0, 21.0, 50.0)
            """,
            (timestamp, node, pm25),
        )
        conn.commit()
        conn.close()

    def insert_event(self, room, event_type, start_time, end_time=None, subtype=None):
        # direct insert so tests control the timestamps exactly
        conn = sqlite3.connect(self.db)
        cursor = conn.execute(
            """
            INSERT INTO events (room, event_type, subtype, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
            """,
            (room, event_type, subtype, start_time, end_time),
        )
        conn.commit()
        conn.close()
        return cursor.lastrowid

    def insert_state(self, room, state_type, state_value, changed_at):
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            INSERT INTO room_states (room, state_type, state_value, changed_at)
            VALUES (?, ?, ?, ?)
            """,
            (room, state_type, state_value, changed_at),
        )
        conn.commit()
        conn.close()


class DuplicateOpenEventTests(LabelsTestCase):

    def test_second_open_event_same_room_and_type_is_rejected(self):
        labels.start_event("kitchen", "cooking", db_path=self.db)

        with self.assertRaises(labels.DuplicateOpenEventError):
            labels.start_event("kitchen", "cooking", db_path=self.db)

        open_df = labels.open_events(db_path=self.db)
        self.assertEqual(len(open_df), 1)

    def test_same_type_in_other_room_and_other_type_same_room_are_allowed(self):
        labels.start_event("kitchen", "cooking", db_path=self.db)
        labels.start_event("bedroom", "cooking", db_path=self.db)
        labels.start_event("kitchen", "candle", db_path=self.db)

        self.assertEqual(len(labels.open_events(db_path=self.db)), 3)

    def test_restart_allowed_after_stopping(self):
        event_id = labels.start_event("kitchen", "cooking", db_path=self.db)

        self.assertTrue(labels.stop_event(event_id, db_path=self.db))
        # stopping an already-closed event is a no-op, not an error
        self.assertFalse(labels.stop_event(event_id, db_path=self.db))

        labels.start_event("kitchen", "cooking", db_path=self.db)
        self.assertEqual(len(labels.open_events(db_path=self.db)), 1)


class RoomStateTests(LabelsTestCase):

    def test_repeated_value_is_not_inserted(self):
        self.assertTrue(labels.set_room_state("kitchen", "window", "open", db_path=self.db))
        self.assertFalse(labels.set_room_state("kitchen", "window", "open", db_path=self.db))
        self.assertTrue(labels.set_room_state("kitchen", "window", "closed", db_path=self.db))

        conn = sqlite3.connect(self.db)
        count = conn.execute("SELECT COUNT(*) FROM room_states").fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

    def test_invalid_value_for_state_type_is_rejected(self):
        with self.assertRaises(ValueError):
            labels.set_room_state("kitchen", "window", "on", db_path=self.db)

    def test_ac_state_is_accepted(self):
        self.assertTrue(labels.set_room_state("bedroom", "ac", "on", db_path=self.db))
        self.assertEqual(
            labels.state_as_of("bedroom", "ac", "2099-01-01 00:00:00", db_path=self.db),
            "on",
        )


class StateAsOfTests(LabelsTestCase):

    def test_no_history_returns_none(self):
        self.assertIsNone(
            labels.state_as_of("kitchen", "window", "2026-07-05 12:00:00", db_path=self.db)
        )

    def test_before_first_change_returns_none(self):
        self.insert_state("kitchen", "window", "open", "2026-07-05 12:00:00")

        self.assertIsNone(
            labels.state_as_of("kitchen", "window", "2026-07-05 11:59:59", db_path=self.db)
        )

    def test_returns_latest_change_at_or_before_timestamp(self):
        self.insert_state("kitchen", "window", "open", "2026-07-05 12:00:00")
        self.insert_state("kitchen", "window", "closed", "2026-07-05 14:00:00")

        self.assertEqual(
            labels.state_as_of("kitchen", "window", "2026-07-05 12:00:00", db_path=self.db),
            "open",
        )
        self.assertEqual(
            labels.state_as_of("kitchen", "window", "2026-07-05 13:30:00", db_path=self.db),
            "open",
        )
        self.assertEqual(
            labels.state_as_of("kitchen", "window", "2026-07-05 15:00:00", db_path=self.db),
            "closed",
        )

    def test_other_rooms_history_does_not_leak(self):
        self.insert_state("kitchen", "window", "open", "2026-07-05 12:00:00")

        self.assertIsNone(
            labels.state_as_of("bedroom", "window", "2026-07-05 13:00:00", db_path=self.db)
        )


class DatasetJoinTests(LabelsTestCase):

    def setUp(self):
        super().setUp()

        # one reading per minute, 10:00-10:30, in all three rooms
        for minute in range(0, 31):
            timestamp = f"2026-07-05 10:{minute:02d}:00"
            for node in ("Kitchen", "Living Room", "Bedroom"):
                self.insert_reading(timestamp, node)

        # cooking in the kitchen 10:10-10:15, exported with a 2 min buffer
        self.event_id = self.insert_event(
            "kitchen", "cooking", "2026-07-05 10:10:00", "2026-07-05 10:15:00",
            subtype="stovetop",
        )

    def build(self, buffer_minutes=2):
        return build_labeled_dataset(
            "2026-07-05 10:00:00",
            "2026-07-05 10:30:00",
            buffer_minutes=buffer_minutes,
            db_path=self.db,
        )

    def test_buffered_window_and_roles(self):
        df = self.build()

        labeled = df[df["event_id"].notna()]

        # buffered window is 10:08-10:17 inclusive -> 10 minutes x 3 rooms
        self.assertEqual(labeled["timestamp"].min(), pd.Timestamp("2026-07-05 10:08:00"))
        self.assertEqual(labeled["timestamp"].max(), pd.Timestamp("2026-07-05 10:17:00"))
        self.assertEqual(len(labeled), 10 * 3)

        self.assertTrue((labeled["event_type"] == "cooking").all())
        self.assertTrue((labeled["subtype"] == "stovetop").all())
        self.assertTrue(
            (labeled.loc[labeled["room"] == "kitchen", "role"] == "source").all()
        )
        self.assertTrue(
            (labeled.loc[labeled["room"] != "kitchen", "role"] == "transport").all()
        )

    def test_background_rows_are_kept_with_null_event(self):
        df = self.build()

        background = df[df["event_id"].isna()]

        # 31 minutes x 3 rooms total, minus the 10 x 3 labeled rows
        self.assertEqual(len(background), 31 * 3 - 10 * 3)
        self.assertTrue(background["event_type"].isna().all())
        self.assertTrue(background["role"].isna().all())
        # background still includes the source room outside the event window
        self.assertIn("kitchen", set(background["room"]))

    def test_open_event_runs_to_end_of_range(self):
        self.insert_event("bedroom", "candle", "2026-07-05 10:25:00", None)

        df = self.build(buffer_minutes=0)
        candle = df[df["event_type"] == "candle"]

        self.assertEqual(candle["timestamp"].max(), pd.Timestamp("2026-07-05 10:30:00"))

    def test_overlapping_events_duplicate_the_reading_once_per_event(self):
        self.insert_event("kitchen", "candle", "2026-07-05 10:12:00", "2026-07-05 10:13:00")

        df = self.build(buffer_minutes=0)
        at_1012 = df[
            (df["timestamp"] == pd.Timestamp("2026-07-05 10:12:00"))
            & (df["room"] == "kitchen")
        ]

        self.assertEqual(sorted(at_1012["event_type"]), ["candle", "cooking"])

    def test_room_state_as_of_join(self):
        self.insert_state("kitchen", "window", "open", "2026-07-05 10:05:00")
        self.insert_state("kitchen", "window", "closed", "2026-07-05 10:20:00")
        self.insert_state("bedroom", "exhaust_fan", "on", "2026-07-05 10:00:00")

        df = self.build()

        kitchen = df[df["room"] == "kitchen"].set_index("timestamp")
        self.assertTrue(kitchen.loc[: "2026-07-05 10:04:00", "window"].isna().all())
        self.assertTrue((kitchen.loc["2026-07-05 10:05:00":"2026-07-05 10:19:00", "window"] == "open").all())
        self.assertTrue((kitchen.loc["2026-07-05 10:20:00":, "window"] == "closed").all())

        # states are per-room: living room never logged anything
        living = df[df["room"] == "living_room"]
        self.assertTrue(living["window"].isna().all())
        self.assertTrue(living["exhaust_fan"].isna().all())

        bedroom = df[df["room"] == "bedroom"]
        self.assertTrue((bedroom["exhaust_fan"] == "on").all())

        # purifier never logged anywhere -> unknown everywhere
        self.assertTrue(df["purifier"].isna().all())


if __name__ == "__main__":
    unittest.main()
