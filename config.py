from pathlib import Path

#project paths

PROJECT_ROOT = Path(__file__).parent

DATABASE_PATH = PROJECT_ROOT / "air_quality.db"

ROOMS = [
    "Kitchen",
    "Living Room",
    "Bedroom",
]

#event / room-state labeling
#
#sensor_data.node stores display names ("Kitchen"); the events and
#room_states tables store slugs ("kitchen"). This map is the single
#source of truth for converting between the two.

ROOM_SLUGS = {
    "Kitchen": "kitchen",
    "Living Room": "living_room",
    "Bedroom": "bedroom",
}

EVENT_TYPES = [
    "cooking",
    "cleaning",
    "candle",
    "occupancy_change",
]

STATE_TYPES = {
    "window": ["open", "closed"],
    "exhaust_fan": ["on", "off"],
    "purifier": ["on", "off"],
    "ac": ["on", "off"],
}

#how far back a retroactive label may claim to have happened.
#labels can be entered as "minutes ago" for something recent, or as an
#explicit date and time for anything older. logged_at records when the
#entry was actually made, so recalled labels stay identifiable.

MAX_BACKDATE_DAYS = 90

MAX_BACKDATE_MINUTES = MAX_BACKDATE_DAYS * 24 * 60

#dashboard

REFRESH_SECONDS = 30

OFFLINE_THRESHOLD_SECONDS = 60

#metrics

METRICS = {
    "PM1": "pm1",
    "PM2.5": "pm25",
    "PM4": "pm4",
    "PM10": "pm10",
    "VOC Index": "voc",
    "NOx Index": "nox",
    "CO2": "co2",
    "Temperature": "temperature",
    "Humidity": "humidity"
}

#time range

TIME_RANGES = {
    "Last Hour": 1,
    "Last 6 Hours": 6,
    "Last 24 Hours": 24,
    "Last 7 Days": 24 * 7,
    "Last 30 Days": 24 * 30,
    "All Data": None
}
