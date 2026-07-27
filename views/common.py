from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from config import METRICS, ROOMS, TIME_RANGES
from database import load_data


def metric_labels():
    return list(METRICS.keys())


def metric_column(label):
    return METRICS[label]


def room_list():
    return list(ROOMS)


def time_range_hours(label):
    return TIME_RANGES[label]


def default_date_window(days=7):
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


@st.cache_data(ttl=30, show_spinner=False)
def _cached_load_data(nodes_key, hours, start_time, end_time, columns_key):
    nodes = list(nodes_key) if nodes_key else None
    columns = list(columns_key) if columns_key else None
    return load_data(
        nodes=nodes,
        hours=hours,
        start_time=start_time,
        end_time=end_time,
        columns=columns,
    )


def load_filtered_data(
    nodes=None,
    time_range_label="Last 24 Hours",
    start_date=None,
    end_date=None,
    columns=None,
):
    columns_key = tuple(columns) if columns else ()

    if time_range_label == "Custom" and start_date and end_date:
        start_time = datetime.combine(start_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
        end_time = datetime.combine(end_date, datetime.max.time()).strftime("%Y-%m-%d %H:%M:%S")
        return _cached_load_data(tuple(nodes or []), None, start_time, end_time, columns_key)

    hours = time_range_hours(time_range_label)
    return _cached_load_data(tuple(nodes or []), hours, None, None, columns_key)


def format_timestamp(value):
    if pd.isna(value):
        return "n/a"
    if not isinstance(value, pd.Timestamp):
        value = pd.to_datetime(value)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def read_selected_columns(df, selected_metrics):
    columns = ["timestamp", "node"] + selected_metrics
    existing = [column for column in columns if column in df.columns]
    return df[existing].copy()
