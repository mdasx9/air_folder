import pandas as pd
import streamlit as st

from config import METRICS, ROOMS, TIME_RANGES
from views.common import load_filtered_data, metric_labels, read_selected_columns, room_list


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
