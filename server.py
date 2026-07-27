from flask import Flask, request
import sqlite3
import time
from datetime import datetime
import logging

logging.getLogger('werkzeug').disabled = True
app = Flask(__name__)
DB_NAME = "air_quality.db"

# How long a single insert may wait for the database before giving up.
# Reads from the dashboard can hold the file briefly; waiting is always
# better than dropping a reading we can never recover.
BUSY_TIMEOUT_SECONDS = 30

# Retries after a timeout, in case the wait itself was not enough.
WRITE_ATTEMPTS = 3

INSERT_SQL = """
INSERT INTO sensor_data (
    timestamp, node,
    pm1, pm25, pm4, pm10,
    voc, nox, co2,
    temperature, humidity
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def connect():
    conn = sqlite3.connect(DB_NAME, timeout=BUSY_TIMEOUT_SECONDS)
    # WAL lets the dashboard read while this process writes; without it a
    # long dashboard query locks the file and inserts fail
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = connect()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        node TEXT,
        pm1 REAL,
        pm25 REAL,
        pm4 REAL,
        pm10 REAL,
        voc REAL,
        nox REAL,
        co2 REAL,
        temperature REAL,
        humidity REAL
    )
    """)

    # the dashboard filters by room and time on every page
    c.execute("""
    CREATE INDEX IF NOT EXISTS ix_sensor_node_time
    ON sensor_data (node, timestamp)
    """)

    c.execute("""
    CREATE INDEX IF NOT EXISTS ix_sensor_time
    ON sensor_data (timestamp)
    """)

    conn.commit()
    conn.close()

    print(f"Database ready: {DB_NAME}")


init_db()


@app.route("/data", methods=["POST"])
def receive_data():
    data = request.json
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = (
        timestamp,
        data["node"],
        data["pm1"],
        data["pm25"],
        data["pm4"],
        data["pm10"],
        data["voc"],
        data["nox"],
        data["co2"],
        data["temperature"],
        data["humidity"]
    )

    for attempt in range(1, WRITE_ATTEMPTS + 1):

        try:
            conn = connect()
            conn.execute(INSERT_SQL, row)
            conn.commit()
            conn.close()

            return "OK"

        except sqlite3.OperationalError as error:

            try:
                conn.close()
            except Exception:
                pass

            if attempt == WRITE_ATTEMPTS:
                # one readable line instead of a full traceback per reading
                print(
                    f"[{timestamp}] DROPPED reading from {data['node']}: {error}"
                )
                return "DB busy", 503

            time.sleep(0.5 * attempt)


app.run(host="0.0.0.0", port=5000)
