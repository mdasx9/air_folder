import pandas as pd
import streamlit as st

from config import ROOMS, TIME_RANGES
from metrics import downsample
from plotting import plot_correlation, plot_time_series
from views.common import load_filtered_data, metric_column, metric_labels, room_list


def _aligned_pivot(df, metric, room_a, room_b, freq="5min"):
    aligned = df[["timestamp", "node", metric]].copy()
    aligned["timestamp"] = pd.to_datetime(aligned["timestamp"]).dt.floor(freq)

    pivot = (
        aligned.pivot_table(
            index="timestamp",
            columns="node",
            values=metric,
            aggfunc="mean",
        )
        .sort_index()
        .dropna(subset=[room_a, room_b])
    )

    return pivot


def _best_lag_minutes(pivot, room_a, room_b, step_minutes=5, max_lag_steps=24):
    if pivot.empty or room_a not in pivot.columns or room_b not in pivot.columns:
        return None

    a = pivot[room_a].astype(float)
    b = pivot[room_b].astype(float)
    best = None

    for lag in range(-max_lag_steps, max_lag_steps + 1):
        corr = a.corr(b.shift(lag))
        if pd.isna(corr):
            continue
        if best is None or abs(corr) > abs(best["corr"]):
            best = {"lag_steps": lag, "corr": corr}

    if best is None:
        return None

    best["lag_minutes"] = best["lag_steps"] * step_minutes
    return best


def render():
    st.header("Room Comparison")
    st.caption("Compare pollutant behavior between rooms and estimate which room appears to react first.")

    controls = st.columns(4)
    room_a = controls[0].selectbox("Room A", room_list(), index=0)
    room_b_choices = [room for room in ROOMS if room != room_a]
    room_b = controls[1].selectbox("Room B", room_b_choices, index=0)
    selected_metric_label = controls[2].selectbox("Measurement", metric_labels(), index=1)
    time_range_label = controls[3].selectbox("Time range", list(TIME_RANGES.keys()), index=2)

    selected_metric = metric_column(selected_metric_label)
    data = load_filtered_data(
        nodes=[room_a, room_b],
        time_range_label=time_range_label,
        columns=[selected_metric],
    )

    if data.empty:
        st.info("No data available for the chosen rooms and time range.")
        return

    sampled = downsample(data)

    plot_time_series(
        sampled[["timestamp", "node", selected_metric]],
        selected_metric,
        title=f"{selected_metric_label} overlay",
    )

    pivot = _aligned_pivot(sampled, selected_metric, room_a, room_b)
    if pivot.empty:
        st.info("Not enough overlapping timestamps to compute correlation or delay.")
        return

    correlation_df = pivot[[room_a, room_b]].reset_index(drop=True)
    plot_correlation(
        correlation_df,
        room_a,
        room_b,
        title=f"{selected_metric_label} correlation",
    )

    lag = _best_lag_minutes(pivot, room_a, room_b)
    if lag is None:
        st.info("Delay estimation was not possible for this filter set.")
    else:
        st.metric(
            "Best alignment",
            f"{lag['lag_minutes']:+.0f} minutes",
            f"Correlation {lag['corr']:.2f}",
        )
        st.caption(
            f"Positive values mean {room_b} appears to lag {room_a}; negative values mean {room_b} appears to lead {room_a}."
        )

    with st.expander("Aligned samples", expanded=False):
        st.dataframe(pivot[[room_a, room_b]], width="stretch")
