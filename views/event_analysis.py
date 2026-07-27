import streamlit as st

from config import ROOMS, TIME_RANGES
from metrics import detect_events, summarize_events
from plotting import plot_threshold_overlay
from views.common import load_filtered_data, metric_column, metric_labels, room_list


# rendering tens of thousands of rows into a table is the slowest thing
# this page can do, and nobody scrolls past the first few hundred
MAX_TABLE_ROWS = 500

DEFAULT_THRESHOLDS = {
    "pm1": 15.0,
    "pm25": 35.0,
    "pm4": 50.0,
    "pm10": 50.0,
    "voc": 100.0,
    "nox": 100.0,
    "co2": 1000.0,
    "temperature": 27.0,
    "humidity": 65.0,
}


def render():
    st.header("Event Analysis")
    st.caption("Highlight pollution episodes so cooking, cleaning, ventilation, and occupancy changes are easier to study.")

    controls = st.columns(3)
    selected_rooms = controls[0].multiselect("Rooms", room_list(), default=ROOMS[:1])
    selected_metric_label = controls[1].selectbox("Measurement", metric_labels(), index=1)
    time_range_label = controls[2].selectbox("Time range", list(TIME_RANGES.keys()), index=2)

    selected_metric = metric_column(selected_metric_label)
    default_threshold = DEFAULT_THRESHOLDS.get(selected_metric, 1.0)
    threshold = st.number_input(
        f"Threshold for {selected_metric_label}",
        value=float(default_threshold),
    )

    if not selected_rooms:
        st.info("Select at least one room to inspect events.")
        return

    for room in selected_rooms:
        st.subheader(room)

        # only the metric under inspection is needed; pulling all nine
        # channels roughly doubles the query cost for no benefit
        room_data = load_filtered_data(
            nodes=[room],
            time_range_label=time_range_label,
            columns=[selected_metric],
        )

        if room_data.empty:
            st.info("No data available for this room and time range.")
            continue

        plot_threshold_overlay(
            room_data,
            selected_metric,
            threshold,
            title=f"{room} - {selected_metric_label}",
        )

        # detection runs on the full-resolution data (the chart thins
        # points for display only, so peaks are never averaged away here)
        exceedances = detect_events(room_data, selected_metric, threshold)
        event_windows = summarize_events(
            room_data,
            selected_metric,
            threshold,
            events=exceedances,
        )

        col_a, col_b = st.columns(2)
        col_a.metric("Threshold exceedances", len(exceedances))
        col_b.metric("Detected events", len(event_windows))

        if event_windows.empty:
            st.info("No event windows crossed the selected threshold.")
            continue

        st.dataframe(event_windows, width="stretch")

        with st.expander("Rows above threshold", expanded=False):
            st.dataframe(exceedances.head(MAX_TABLE_ROWS), width="stretch")
            if len(exceedances) > MAX_TABLE_ROWS:
                st.caption(
                    f"Showing the first {MAX_TABLE_ROWS:,} of {len(exceedances):,} rows. "
                    "Use Data Export for the complete set."
                )
