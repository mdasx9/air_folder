"""
Airflow / transport analysis.

Each logged event is a tracer release in a known room. Because all three
rooms are measured simultaneously against one server clock, every event
yields a set of paired observations: how long the signal took to reach
each other room, how much of it survived the trip, and how fast it
cleared afterwards.

Per event and room, this module reports:

  baseline        median level in the quiet window before the event
  noise           variability of that quiet window (used for detection)
  peak            highest level from the event start to the end of the
                  post-event window
  peak_time       when that peak occurred
  rise            peak - baseline, the amplitude attributable to the event
  snr             rise / noise; how confidently the rise is real
  lag_minutes     peak_time here minus peak_time in the source room
  xcorr_lag_min   lag from cross-correlation, which uses the whole curve
                  shape rather than a single point
  attenuation     rise here / rise in the source room
  clearance_min   time from peak to falling halfway back to baseline

Lag is only meaningful when a rise was actually detected, so rows below
the detection threshold report NaN rather than a number that would look
like a measurement.
"""

import numpy as np
import pandas as pd

from config import DATABASE_PATH, ROOM_SLUGS, STATE_TYPES
from labels import get_connection


# A rise must exceed this many standard deviations of the pre-event
# baseline to count as an arrival rather than ordinary drift.
DETECTION_SNR = 3.0

# ...and it must *stay* above that threshold for this long. The threshold
# alone is not enough: across the ~1000 samples in an event window, the
# largest value of pure noise clears 3 sigma by chance fairly often, so a
# peak-only test reports flat rooms as detections. Requiring the level to
# hold up for minutes is what separates a plume from a noise spike.
ARRIVAL_PERSISTENCE = pd.Timedelta(seconds=120)

# resolution the two curves are put on before cross-correlation
XCORR_BIN = "30s"

# How far either side cross-correlation may search. Kept to a physically
# plausible range for one dwelling: a wider window mostly lets the search
# run to its own boundary and report that as a measurement.
XCORR_MAX_LAG_MINUTES = 30

# Alignment below this correlation is not a lag measurement, it is the
# best of a set of bad fits, so it is reported as unknown instead.
XCORR_MIN_CORRELATION = 0.5



def _resample(series, bin_size=XCORR_BIN):
    return series.resample(bin_size).mean().interpolate(limit_direction="both")


def _xcorr_lag_minutes(source, target, source_baseline, target_baseline,
                       bin_size=XCORR_BIN,
                       max_lag_minutes=XCORR_MAX_LAG_MINUTES):
    """
    Lag that best aligns the target curve onto the source curve.

    Positive means the target lags the source, i.e. air arrived later -
    the expected direction for a room downstream of the event.

    Both curves are baseline-subtracted first: correlating raw levels
    mostly measures whether two rooms drift together over the day, which
    is not the question being asked.

    Returns NaN when the best alignment is still a poor fit, rather than
    reporting the least-bad shift as though it were a measurement.
    """

    a = _resample(source - source_baseline, bin_size)
    b = _resample(target - target_baseline, bin_size)

    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()

    if len(joined) < 4:
        return np.nan

    step_seconds = pd.Timedelta(bin_size).total_seconds()
    max_steps = int((max_lag_minutes * 60) / step_seconds)
    max_steps = min(max_steps, len(joined) - 2)

    if max_steps < 1:
        return np.nan

    best_lag, best_corr = np.nan, -np.inf

    for lag in range(-max_steps, max_steps + 1):
        shifted = joined["b"].shift(-lag)
        corr = joined["a"].corr(shifted)

        if pd.notna(corr) and corr > best_corr:
            best_corr, best_lag = corr, lag

    if not np.isfinite(best_corr) or best_corr < XCORR_MIN_CORRELATION:
        return np.nan

    return best_lag * step_seconds / 60.0


def _room_metrics(readings, metric, event_start, event_end, pre_minutes):
    """Baseline, peak and clearance for one room around one event."""

    series = (
        readings.set_index("timestamp")[metric]
        .sort_index()
        .astype(float)
    )

    if series.empty:
        return None

    pre_start = event_start - pd.Timedelta(minutes=pre_minutes)
    pre = series.loc[pre_start:event_start]

    if pre.empty:
        return None

    baseline = float(pre.median())
    noise = float(pre.std(ddof=0))

    during = series.loc[event_start:]

    if during.empty:
        return None

    peak = float(during.max())
    peak_time = during.idxmax()
    rise = peak - baseline

    # When the level first climbs clear of baseline noise and stays there.
    # This is a better answer to "when did the air get here" than the peak,
    # which sits at the top of a broad plateau and moves around with noise.
    threshold = baseline + DETECTION_SNR * noise if noise > 0 else baseline
    above = during[during > threshold]

    arrival_time = pd.NaT

    for candidate in above.index:
        window = during.loc[candidate: candidate + ARRIVAL_PERSISTENCE]
        if len(window) > 1 and (window > threshold).all():
            arrival_time = candidate
            break

    # how long until the level falls halfway back toward baseline
    after_peak = during.loc[peak_time:]
    half = baseline + rise / 2.0
    below = after_peak[after_peak <= half]

    if rise > 0 and not below.empty:
        clearance = (below.index[0] - peak_time).total_seconds() / 60.0
    else:
        clearance = np.nan

    return {
        "baseline": baseline,
        "noise": noise,
        "peak": peak,
        "peak_time": peak_time,
        "arrival_time": arrival_time,
        "rise": rise,
        "snr": rise / noise if noise > 0 else np.nan,
        "clearance_min": clearance,
        "series": series,
    }


def _states_at(conn, room, moment):
    """Room conditions in effect at a given time (as-of lookup)."""

    values = {}

    for state_type in STATE_TYPES:
        row = conn.execute(
            """
            SELECT state_value FROM room_states
            WHERE room = ? AND state_type = ? AND changed_at <= ?
            ORDER BY changed_at DESC, id DESC LIMIT 1
            """,
            (room, state_type, moment.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

        values[state_type] = row[0] if row else None

    return values


def event_transport_metrics(metric="pm25", pre_minutes=20, post_minutes=60,
                            min_duration_minutes=0, db_path=DATABASE_PATH):
    """
    Propagation metrics for every closed event, one row per event per room.

    Returns a tidy DataFrame. The source room's own row has lag 0 and
    attenuation 1 by definition and is kept, so each event is complete.
    """

    conn = get_connection(db_path)

    events = pd.read_sql_query(
        """
        SELECT id, room, event_type, subtype, start_time, end_time
        FROM events
        WHERE end_time IS NOT NULL
        ORDER BY start_time
        """,
        conn,
        parse_dates=["start_time", "end_time"],
    )

    rows = []

    for event in events.itertuples(index=False):

        duration = (event.end_time - event.start_time).total_seconds() / 60.0

        if duration < min_duration_minutes:
            continue

        window_start = event.start_time - pd.Timedelta(minutes=pre_minutes)
        window_end = event.end_time + pd.Timedelta(minutes=post_minutes)

        readings = pd.read_sql_query(
            f"""
            SELECT timestamp, node, {metric}
            FROM sensor_data
            WHERE timestamp BETWEEN ? AND ?
            ORDER BY timestamp
            """,
            conn,
            params=[
                window_start.strftime("%Y-%m-%d %H:%M:%S"),
                window_end.strftime("%Y-%m-%d %H:%M:%S"),
            ],
            parse_dates=["timestamp"],
        )

        if readings.empty:
            continue

        readings["room"] = readings["node"].map(ROOM_SLUGS).fillna(readings["node"])

        per_room = {}

        for room, group in readings.groupby("room"):
            result = _room_metrics(
                group, metric, event.start_time, event.end_time, pre_minutes
            )
            if result is not None:
                per_room[room] = result

        source = per_room.get(event.room)

        if source is None:
            continue

        # detection is sustained exceedance, not a single high sample
        source_detected = pd.notna(source["arrival_time"])

        for room, result in per_room.items():

            detected = pd.notna(result["arrival_time"])
            is_source = room == event.room

            # a lag only means something if both ends actually saw the event
            if is_source:
                peak_lag = 0.0
                arrival_lag = 0.0
                xcorr_lag = 0.0
            elif detected and source_detected:
                peak_lag = (
                    result["peak_time"] - source["peak_time"]
                ).total_seconds() / 60.0

                if pd.notna(result["arrival_time"]) and pd.notna(source["arrival_time"]):
                    arrival_lag = (
                        result["arrival_time"] - source["arrival_time"]
                    ).total_seconds() / 60.0
                else:
                    arrival_lag = np.nan

                xcorr_lag = _xcorr_lag_minutes(
                    source["series"], result["series"],
                    source["baseline"], result["baseline"],
                )
            else:
                peak_lag = np.nan
                arrival_lag = np.nan
                xcorr_lag = np.nan

            # like lag, a ratio is only a measurement if both ends saw the
            # event; otherwise it is noise divided by signal
            if is_source:
                attenuation = 1.0
            elif detected and source_detected and source["rise"] > 0:
                attenuation = result["rise"] / source["rise"]
            else:
                attenuation = np.nan

            states = _states_at(conn, room, event.start_time)

            rows.append({
                "event_id": event.id,
                "event_type": event.event_type,
                "subtype": event.subtype,
                "source_room": event.room,
                "room": room,
                "role": "source" if is_source else "transport",
                "start_time": event.start_time,
                "duration_min": duration,
                "baseline": result["baseline"],
                "peak": result["peak"],
                "rise": result["rise"],
                "snr": result["snr"],
                "detected": bool(detected),
                "arrival_lag_min": arrival_lag,
                "peak_lag_min": peak_lag,
                "xcorr_lag_min": xcorr_lag,
                "attenuation": attenuation,
                "clearance_min": result["clearance_min"],
                **states,
            })

    conn.close()

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    return frame.sort_values(["start_time", "role", "room"]).reset_index(drop=True)


def transport_summary(metrics):
    """Average propagation behaviour per source room -> target room pair."""

    if metrics.empty:
        return metrics

    transport = metrics[metrics["role"] == "transport"]
    detected = transport[transport["detected"]]

    if detected.empty:
        return pd.DataFrame()

    summary = (
        detected.groupby(["source_room", "room"])
        .agg(
            events=("event_id", "nunique"),
            median_arrival_lag_min=("arrival_lag_min", "median"),
            median_peak_lag_min=("peak_lag_min", "median"),
            median_xcorr_lag_min=("xcorr_lag_min", "median"),
            xcorr_resolved=("xcorr_lag_min", "count"),
            median_attenuation=("attenuation", "median"),
            median_clearance_min=("clearance_min", "median"),
        )
        .reset_index()
    )

    # how often the signal reached that room at all, detected or not
    attempts = (
        transport.groupby(["source_room", "room"])["event_id"].nunique()
        .rename("events_observed")
        .reset_index()
    )

    summary = summary.merge(attempts, on=["source_room", "room"], how="left")
    summary["detection_rate"] = summary["events"] / summary["events_observed"]

    return summary
