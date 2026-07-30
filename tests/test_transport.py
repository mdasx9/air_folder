"""
Tests for the airflow/transport metrics.

Synthetic plumes with a known delay and known attenuation are written to a
throwaway database, so the recovered numbers can be checked against the
truth rather than eyeballed.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import labels
import transport


SENSOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, node TEXT,
    pm1 REAL, pm25 REAL, pm4 REAL, pm10 REAL,
    voc REAL, nox REAL, co2 REAL,
    temperature REAL, humidity REAL
)
"""

START = pd.Timestamp("2026-05-01 12:00:00")
EVENT_START = pd.Timestamp("2026-05-01 12:30:00")
EVENT_END = pd.Timestamp("2026-05-01 12:50:00")


class TransportTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "t.db"

        conn = sqlite3.connect(self.db)
        conn.executescript(SENSOR_SCHEMA)
        conn.executescript(labels.SCHEMA)
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def _plume(self, node, amplitude, delay_minutes, baseline=5.0, noise=0.05,
               minutes=120, seed=0):
        """A quiet baseline, then a delayed triangular rise and decay."""

        rng = np.random.default_rng(seed)
        rows = []

        for step in range(minutes * 12):          # 5-second samples
            moment = START + pd.Timedelta(seconds=5 * step)
            onset = EVENT_START + pd.Timedelta(minutes=delay_minutes)

            value = baseline + rng.normal(0, noise)

            if moment >= onset:
                elapsed = (moment - onset).total_seconds() / 60.0
                if elapsed <= 10:
                    value += amplitude * (elapsed / 10)      # rise
                elif elapsed <= 40:
                    value += amplitude * (1 - (elapsed - 10) / 30)   # decay

            rows.append((
                moment.strftime("%Y-%m-%d %H:%M:%S"), node,
                0.0, round(value, 3), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            ))

        conn = sqlite3.connect(self.db)
        conn.executemany(
            "INSERT INTO sensor_data (timestamp,node,pm1,pm25,pm4,pm10,voc,nox,co2,temperature,humidity)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()

    def _event(self, room="kitchen", event_type="cooking"):
        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO events (room, event_type, start_time, end_time) VALUES (?,?,?,?)",
            (room, event_type,
             EVENT_START.strftime("%Y-%m-%d %H:%M:%S"),
             EVENT_END.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()


class MetricRecoveryTests(TransportTestCase):

    def test_recovers_known_delay_and_attenuation(self):
        self._plume("Kitchen", amplitude=40.0, delay_minutes=0, seed=1)
        self._plume("Living Room", amplitude=20.0, delay_minutes=5, seed=2)
        self._plume("Bedroom", amplitude=10.0, delay_minutes=10, seed=3)
        self._event()

        metrics = transport.event_transport_metrics(db_path=self.db)
        by_room = metrics.set_index("room")

        # every room saw it
        self.assertTrue(by_room["detected"].all())

        # arrival lag recovers the injected delay
        self.assertAlmostEqual(by_room.loc["living_room", "arrival_lag_min"], 5, delta=1.5)
        self.assertAlmostEqual(by_room.loc["bedroom", "arrival_lag_min"], 10, delta=1.5)

        # cross-correlation agrees
        self.assertAlmostEqual(by_room.loc["living_room", "xcorr_lag_min"], 5, delta=1.5)
        self.assertAlmostEqual(by_room.loc["bedroom", "xcorr_lag_min"], 10, delta=1.5)

        # amplitude ratios recover the injected attenuation
        self.assertAlmostEqual(by_room.loc["living_room", "attenuation"], 0.5, delta=0.1)
        self.assertAlmostEqual(by_room.loc["bedroom", "attenuation"], 0.25, delta=0.1)

    def test_source_row_is_the_reference(self):
        self._plume("Kitchen", amplitude=40.0, delay_minutes=0, seed=1)
        self._plume("Living Room", amplitude=20.0, delay_minutes=5, seed=2)
        self._event()

        metrics = transport.event_transport_metrics(db_path=self.db)
        source = metrics[metrics["role"] == "source"].iloc[0]

        self.assertEqual(source["room"], "kitchen")
        self.assertEqual(source["arrival_lag_min"], 0.0)
        self.assertEqual(source["attenuation"], 1.0)


class DetectionTests(TransportTestCase):

    def test_room_with_no_plume_is_not_detected_and_reports_no_lag(self):
        self._plume("Kitchen", amplitude=40.0, delay_minutes=0, seed=1)
        self._plume("Bedroom", amplitude=0.0, delay_minutes=0, seed=2)   # flat
        self._event()

        metrics = transport.event_transport_metrics(db_path=self.db)
        bedroom = metrics[metrics["room"] == "bedroom"].iloc[0]

        self.assertFalse(bool(bedroom["detected"]))
        # an undetected arrival must not report a lag that looks measured
        self.assertTrue(pd.isna(bedroom["arrival_lag_min"]))
        self.assertTrue(pd.isna(bedroom["xcorr_lag_min"]))
        self.assertTrue(pd.isna(bedroom["attenuation"]))

    def test_open_events_are_skipped(self):
        self._plume("Kitchen", amplitude=40.0, delay_minutes=0, seed=1)

        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO events (room, event_type, start_time, end_time) VALUES (?,?,?,NULL)",
            ("kitchen", "cooking", EVENT_START.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()

        self.assertTrue(transport.event_transport_metrics(db_path=self.db).empty)


class SummaryTests(TransportTestCase):

    def test_summary_reports_per_pair_medians(self):
        self._plume("Kitchen", amplitude=40.0, delay_minutes=0, seed=1)
        self._plume("Living Room", amplitude=20.0, delay_minutes=5, seed=2)
        self._event()

        metrics = transport.event_transport_metrics(db_path=self.db)
        summary = transport.transport_summary(metrics)

        row = summary[summary["room"] == "living_room"].iloc[0]
        self.assertEqual(row["source_room"], "kitchen")
        self.assertEqual(row["events"], 1)
        self.assertAlmostEqual(row["median_arrival_lag_min"], 5, delta=1.5)

    def test_empty_input_is_handled(self):
        self.assertTrue(transport.event_transport_metrics(db_path=self.db).empty)
        self.assertTrue(transport.transport_summary(pd.DataFrame()).empty)


if __name__ == "__main__":
    unittest.main()
