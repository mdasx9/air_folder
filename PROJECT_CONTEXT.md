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

plotting.py:
Visualization helpers.

firmware/:
ESP32 firmware.


## Research Goals

1. Collect multi-room IAQ data over several weeks.
2. Analyze pollutant movement between rooms.
3. Calculate transport delays.
4. Detect pollution events.
5. Build prediction models for future air quality.
6. Compare predictive purifier control against threshold-based control.


## Development Principles

- Preserve existing working data collection.
- Avoid unnecessary complexity.
- Prioritize data quality and analysis.
- Do not modify firmware unless necessary.
- Do not introduce heavy ML without a clear research purpose.