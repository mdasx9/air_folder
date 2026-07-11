import pandas as pd
import streamlit as st


def metric_label(metric):
    labels = {
        "pm1": "PM1 (ug/m3)",
        "pm25": "PM2.5 (ug/m3)",
        "pm4": "PM4 (ug/m3)",
        "pm10": "PM10 (ug/m3)",
        "voc": "VOC index",
        "nox": "NOx index",
        "co2": "CO2 (ppm)",
        "temperature": "Temperature (C)",
        "humidity": "Humidity (%)",
    }

    return labels.get(metric, metric)


def display_statistics(stats):
    if stats is None or len(stats) == 0:
        return

    columns = st.columns(len(stats))

    for column, (name, value) in zip(columns, stats.items()):
        column.metric(name, round(value, 2))


def _ensure_timestamp(df):
    result = df.copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"])
    return result


def plot_time_series(df, metric, title=None):
    if df.empty:
        st.warning("No data available.")
        return

    chart_title = title or metric_label(metric)
    st.subheader(chart_title)

    chart_data = _ensure_timestamp(df)

    if "node" in chart_data.columns and chart_data["node"].nunique() > 1:
        # nodes sample on independent clocks, so raw timestamps rarely
        # coincide across rooms; snapping to a shared grid keeps the pivot
        # dense (NaN holes break the plotted line at every point)
        chart_data["timestamp"] = chart_data["timestamp"].dt.floor("30s")
        wide = chart_data.pivot_table(
            index="timestamp",
            columns="node",
            values=metric,
            aggfunc="mean",
        ).sort_index()
        st.line_chart(wide)
        return

    st.line_chart(chart_data.set_index("timestamp")[[metric]])


def plot_correlation(df, x_metric, y_metric, title=None):
    if df.empty:
        st.warning("No data available.")
        return

    chart_title = title or f"{metric_label(x_metric)} vs {metric_label(y_metric)}"
    st.subheader(chart_title)

    chart_data = df[[x_metric, y_metric]].dropna()
    st.scatter_chart(chart_data)


def plot_threshold_overlay(df, metric, threshold, title=None):
    if df.empty:
        st.warning("No data available.")
        return

    chart_title = title or f"{metric_label(metric)} with threshold"
    st.subheader(chart_title)

    chart_data = _ensure_timestamp(df[["timestamp", metric]].copy())
    chart_data["threshold"] = threshold
    st.line_chart(chart_data.set_index("timestamp")[[metric, "threshold"]])
