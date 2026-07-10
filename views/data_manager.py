from datetime import datetime

import pandas as pd
import streamlit as st

from config import METRICS, ROOMS, TIME_RANGES
from dataset import build_labeled_dataset
from views.common import default_date_window, load_filtered_data, metric_labels, read_selected_columns, room_list


def render():
    st.header("Data Manager")
    st.caption("Export filtered data for offline analysis or modeling.")

    controls = st.columns(3)
    selected_rooms = controls[0].multiselect("Rooms", room_list(), default=ROOMS)
    time_range_label = controls[1].selectbox("Time range", list(TIME_RANGES.keys()), index=2)
    selected_metrics_labels = controls[2].multiselect(
        "Measurements",
        metric_labels(),
        default=["PM2.5", "CO2"],
    )

    if not selected_metrics_labels:
        st.info("Choose at least one measurement to export.")
        return

    selected_metrics = [METRICS[label] for label in selected_metrics_labels]
    data = load_filtered_data(
        nodes=selected_rooms or None,
        time_range_label=time_range_label,
    )

    if data.empty:
        st.info("No data available for the selected export filters.")
        return

    export_df = read_selected_columns(data, selected_metrics)
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")

    summary_columns = st.columns(3)
    summary_columns[0].metric("Rows", len(export_df))
    summary_columns[1].metric("Rooms", export_df["node"].nunique() if "node" in export_df.columns else 0)
    summary_columns[2].metric("Columns", len(export_df.columns))

    st.dataframe(export_df.head(200), use_container_width=True)

    file_name = f"air_quality_export_{time_range_label.replace(' ', '_').lower()}.csv"
    st.download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=file_name,
        mime="text/csv",
    )

    st.divider()
    _render_labeled_export()


def _render_labeled_export():
    st.subheader("Labeled ML dataset")
    st.caption(
        "Sensor readings from all rooms joined with logged events (source/transport role) "
        "and as-of room states. Rows with no event are kept as the background class."
    )

    default_start, default_end = default_date_window(days=7)

    controls = st.columns(3)
    start_date = controls[0].date_input("Start date", value=default_start)
    end_date = controls[1].date_input("End date", value=default_end)
    buffer_minutes = controls[2].number_input(
        "Buffer around events (minutes)",
        min_value=0,
        max_value=120,
        value=10,
    )

    if st.button("Build labeled dataset"):
        start_time = datetime.combine(start_date, datetime.min.time())
        end_time = datetime.combine(end_date, datetime.max.time())
        st.session_state["labeled_dataset"] = build_labeled_dataset(
            start_time,
            end_time,
            buffer_minutes=buffer_minutes,
        )

    labeled = st.session_state.get("labeled_dataset")
    if labeled is None:
        return

    if labeled.empty:
        st.info("No sensor readings in the selected date range.")
        return

    event_rows = labeled["event_type"].notna()

    summary = st.columns(3)
    summary[0].metric("Rows", len(labeled))
    summary[1].metric("Event-labeled rows", int(event_rows.sum()))
    summary[2].metric("Background rows", int((~event_rows).sum()))

    st.dataframe(labeled.head(200), use_container_width=True)

    st.download_button(
        "Download labeled CSV",
        data=labeled.to_csv(index=False).encode("utf-8"),
        file_name="labeled_dataset.csv",
        mime="text/csv",
    )
