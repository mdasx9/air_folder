import altair as alt
import pandas as pd
import streamlit as st


# Points sent to the browser per series. Above roughly this, rendering
# (not querying) is what makes a page feel slow, and the extra points are
# narrower than a screen pixel anyway.
MAX_PLOT_POINTS = 1500

HOVER_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


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


def _thin_for_display(long_df, max_points=MAX_PLOT_POINTS):
    """
    Average points into time bins so each series stays under max_points.

    Display only — callers that compute statistics or detect events should
    do so on the raw data before calling this.
    """

    series_count = max(long_df["series"].nunique(), 1)
    per_series = len(long_df) / series_count

    if per_series <= max_points:
        return long_df

    span_seconds = (
        long_df["timestamp"].max() - long_df["timestamp"].min()
    ).total_seconds()

    if span_seconds <= 0:
        return long_df

    bin_seconds = max(int(span_seconds / max_points), 1)

    binned = long_df.copy()
    binned["timestamp"] = binned["timestamp"].dt.floor(f"{bin_seconds}s")

    return (
        binned.groupby(["timestamp", "series", "series_key"], as_index=False, observed=True)["value"]
        .mean()
    )


def _build_hover_chart(long_df, value_title, legend=True):
    """
    Line chart with a shared hover rule that reports the exact timestamp
    (to the second) and every series' value at that moment.
    """

    names = list(dict.fromkeys(long_df["series"]))

    # pivot field names go straight into the Vega spec, where dots and
    # spaces in a name (e.g. "PM2.5 (ug/m3)") would be read as accessors,
    # so pivot on a safe key and show the real name as the tooltip title
    key_lookup = {name: f"s{index}" for index, name in enumerate(names)}
    long_df = long_df.copy()
    long_df["series_key"] = long_df["series"].map(key_lookup)

    long_df = _thin_for_display(long_df)

    hover = alt.selection_point(
        fields=["timestamp"],
        nearest=True,
        on="pointerover",
        empty=False,
        clear="pointerout",
    )

    base = alt.Chart(long_df).encode(
        x=alt.X("timestamp:T", title=None),
        y=alt.Y("value:Q", title=value_title, scale=alt.Scale(zero=False)),
    )

    color = alt.Color("series:N", title=None) if legend else alt.Color(
        "series:N", title=None, legend=None
    )

    lines = base.mark_line(interpolate="monotone").encode(color=color)

    points = base.mark_circle(size=55).encode(
        color=color,
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
    )

    tooltips = [
        alt.Tooltip("timestamp:T", title="Time", format=HOVER_TIME_FORMAT)
    ] + [
        alt.Tooltip(f"{key_lookup[name]}:Q", title=name, format=".2f")
        for name in names
    ]

    rule = (
        alt.Chart(long_df)
        .transform_pivot("series_key", value="value", groupby=["timestamp"])
        .mark_rule(color="#9aa0a6")
        .encode(
            x=alt.X("timestamp:T", title=None),
            opacity=alt.condition(hover, alt.value(0.35), alt.value(0)),
            tooltip=tooltips,
        )
        .add_params(hover)
    )

    return lines + points + rule


def _render(chart):
    st.altair_chart(chart.interactive(bind_y=False), width="stretch")


def plot_time_series(df, metric, title=None):
    if df.empty:
        st.warning("No data available.")
        return

    chart_title = title or metric_label(metric)
    st.subheader(chart_title)

    chart_data = _ensure_timestamp(df)

    if "node" in chart_data.columns:
        long_df = chart_data.rename(columns={"node": "series", metric: "value"})
        long_df = long_df[["timestamp", "series", "value"]].dropna(subset=["value"])
        multi_room = long_df["series"].nunique() > 1
    else:
        long_df = chart_data[["timestamp", metric]].rename(columns={metric: "value"})
        long_df["series"] = metric_label(metric)
        long_df = long_df.dropna(subset=["value"])
        multi_room = False

    if long_df.empty:
        st.warning("No data available.")
        return

    _render(_build_hover_chart(long_df, metric_label(metric), legend=multi_room))


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

    long_df = chart_data.rename(columns={metric: "value"})[["timestamp", "value"]]
    long_df["series"] = metric_label(metric)
    long_df = long_df.dropna(subset=["value"])

    if long_df.empty:
        st.warning("No data available.")
        return

    chart = _build_hover_chart(long_df, metric_label(metric), legend=False)

    # a constant reference line, not a data series - keeps it out of the
    # hover tooltip and out of the point-thinning maths
    threshold_line = (
        alt.Chart(pd.DataFrame({"threshold": [threshold]}))
        .mark_rule(color="#e8734a", strokeDash=[6, 4])
        .encode(y=alt.Y("threshold:Q", title=metric_label(metric)))
    )

    _render(chart + threshold_line)
