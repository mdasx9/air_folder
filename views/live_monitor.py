import streamlit as st

from config import OFFLINE_THRESHOLD_SECONDS, ROOMS
from database import current_values, latest_timestamp, node_status
from plotting import metric_label
from views.common import format_timestamp


def _status_copy(online, seconds_ago):
    if online:
        return "Online", "success"
    if seconds_ago is None:
        return "No data", "error"
    if seconds_ago < OFFLINE_THRESHOLD_SECONDS * 3:
        return "Stale", "warning"
    return "Offline", "error"


def render():
    st.header("Live Monitor")
    st.caption("Quickly verify that every room is still reporting and see the latest reading from each node.")

    status_df = node_status()
    status_lookup = {
        row.node: row
        for row in status_df.itertuples(index=False)
    }

    latest = latest_timestamp()
    if latest is not None:
        st.info(f"Latest database timestamp: {format_timestamp(latest)}")

    summary_columns = st.columns(3)
    summary_columns[0].metric("Configured rooms", len(ROOMS))
    summary_columns[1].metric("Rooms with data", len(status_df))
    summary_columns[2].metric(
        "Online rooms",
        int(status_df["online"].sum()) if not status_df.empty else 0,
    )

    st.write("")

    for room in ROOMS:
        room_status = status_lookup.get(room)
        reading = current_values(room)

        with st.container(border=True):
            header_left, header_right = st.columns([3, 1])
            header_left.subheader(room)

            if room_status is None:
                header_right.error("No data")
                st.warning("This room has not reported any readings yet.")
                continue

            label, tone = _status_copy(
                bool(room_status.online),
                float(room_status.seconds_ago) if room_status.seconds_ago is not None else None,
            )
            getattr(header_right, tone)(label)

            detail_columns = st.columns(3)
            detail_columns[0].metric("Last update", format_timestamp(room_status.last_seen))
            detail_columns[1].metric("Seconds ago", f"{room_status.seconds_ago:.1f}")
            detail_columns[2].metric("Status", label)

            if reading.empty:
                st.warning("No current reading found for this room.")
                continue

            row = reading.iloc[0]
            metric_columns = st.columns(6)
            metric_columns[0].metric("PM2.5", f"{row['pm25']:.1f}")
            metric_columns[1].metric("CO2", f"{row['co2']:.0f}")
            metric_columns[2].metric("VOC", f"{row['voc']:.0f}")
            metric_columns[3].metric("NOx", f"{row['nox']:.0f}")
            metric_columns[4].metric("Temperature", f"{row['temperature']:.2f} °C")
            metric_columns[5].metric("Humidity", f"{row['humidity']:.2f} %")

            with st.expander("More metrics", expanded=False):
                extra_columns = st.columns(2)
                extra_columns[0].metric(metric_label("pm1"), f"{row['pm1']:.1f}")
                extra_columns[1].metric(metric_label("pm4"), f"{row['pm4']:.1f}")
