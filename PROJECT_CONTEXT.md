# Indoor Air Quality Monitoring Platform

## Overview

This project is a multi-room indoor air quality monitoring system.

The goal is to study indoor pollutant transport, room-to-room delays, event detection, and predictive air purifier control.

## Hardware

Three ESP32 sensor nodes:

- Kitchen
- Living Room
- Bedroom

Each node uses a Sensirion SEN66 sensor.

Measurements:

- PM1
- PM2.5
- PM4
- PM10
- VOC
- NOx
- CO2
- Temperature
- Humidity


## Data Pipeline

SEN66 sensors
    ↓
ESP32 nodes
    ↓
WiFi JSON POST
    ↓
Flask server
    ↓
SQLite database
    ↓
Python analysis
    ↓
Streamlit dashboard


## Current Software

dashboard.py:
Streamlit dashboard entry point.

server.py:
Flask API receiving ESP32 data.

database.py:
SQLite database functions.

metrics.py:
Data processing and analysis functions.

labels.py:
Event and room-state logging (ground truth).

dataset.py:
Joins readings to events and room states for analysis.

transport.py:
Airflow analysis: per-event arrival lag, attenuation, clearance time.

plotting.py:
Visualization helpers.

firmware/:
ESP32 firmware.


## Research Goals

The project's primary question is **indoor airflow and pollutant
transport**: how a pollution event in one room propagates to the others,
how long it takes, how much survives the journey, and how ventilation
conditions change that.

1. Collect multi-room IAQ data over several weeks.
2. Quantify room-to-room transport: arrival lag, attenuation, clearance time.
3. Relate transport behaviour to room conditions (window, exhaust fan,
   purifier, AC).
4. Establish which sensor channels track transport most reliably.
5. Detect pollution events as the trigger for the above.

### Why this, and not source classification

The original plan was to classify the *source* of an event (cooking,
cleaning, candle, occupancy) from the SEN66 channels, with a
channel-ablation experiment as the centrepiece. That was set aside because
the collected labels are overwhelmingly one class - of the events logged
so far, nearly all are cooking, with a single cleaning event and no candle
or occupancy events. A four-class classifier cannot be trained or
honestly validated on that.

The same data is, however, well suited to transport analysis. Repeated
kitchen events act as replicate tracer releases into a fixed floor plan,
measured simultaneously in three rooms against one server clock. What was
a weakness for classification - many repetitions of one event type - is a
strength here, because it gives repeated measurements of the same
transport path.

Source classification remains possible later if the label mix becomes
balanced; nothing in the schema or the export prevents it.


## Development Principles

- Preserve existing working data collection.
- Avoid unnecessary complexity.
- Prioritize data quality and analysis.
- Do not modify firmware unless necessary.
- Do not introduce heavy ML without a clear research purpose.