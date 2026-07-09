from flask import Flask, request
import sqlite3
from datetime import datetime
import logging
logging.getLogger('werkzeug').disabled = True
app = Flask(__name__)
DB_NAME = "air_quality.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
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

    conn.commit()
    conn.close()


init_db()


@app.route("/data", methods=["POST"])
def receive_data():
    data = request.json
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    INSERT INTO sensor_data (
        timestamp, node,
        pm1, pm25, pm4, pm10,
        voc, nox, co2,
        temperature, humidity
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
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
    ))

    conn.commit()
    conn.close()

    #print(timestamp, data)

    return "OK"


app.run(host="0.0.0.0", port=5000)