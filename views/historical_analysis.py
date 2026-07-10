import streamlit as st

from config import ROOMS, TIME_RANGES
from metrics import daily_average, downsample, summary_statistics
from plotting import display_statistics, plot_time_series
from views.common import load_filtered_data, metric_column, metric_labels, room_list


def render():
    st.header("Historical Analysis")
    st.caption("Explore long-term trends, compare rooms, and inspect raw history with automatic downsampling.")

    controls = st.columns(3)
    selected_rooms = controls[0].multiselect(
        "Rooms",
        room_list(),
        default=ROOMS,
    )
    selected_metric_label = controls[1].selectbox(
        "Pollutant / measurement",
        metric_labels(),
        index=1,
    )
    time_range_label = controls[2].selectbox(
        "Time range",
        list(TIME_RANGES.keys()),
        index=2,
    )

    selected_metric = metric_column(selected_metric_label)
    data = load_filtered_data(
        nodes=selected_rooms or None,
        time_range_label=time_range_label,
    )

    if data.empty:
        st.info("No matching data for the selected filters.")
        return

    sampled = downsample(data)
    stats = summary_statistics(sampled, selected_metric)
    display_statistics(stats)

    plot_time_series(
        sampled[["timestamp", "node", selected_metric]] if "node" in sampled.columns else sampled[["timestamp", selected_metric]],
        selected_metric,
        title=f"{selected_metric_label} over time",
    )

    with st.expander("Daily averages", expanded=False):
        if len(sampled) > 1:
            st.dataframe(daily_average(sampled), use_container_width=True)
        else:
            st.info("Not enough data to compute a daily average.")

    with st.expander("Filtered rows", expanded=False):
        st.dataframe(
            sampled[["timestamp", "node", selected_metric]] if "node" in sampled.columns else sampled[["timestamp", selected_metric]],
            use_container_width=True,
        )
