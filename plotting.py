import streamlit as st


def plot_metric(df, metric):

    if df.empty:

        st.warning("No data.")

        return

    chart = df.set_index("timestamp")
import streamlit as st


def plot_time_series(df, metric, title=None):
    # plot a metric over time

    if df.empty:
        st.warning("no data available")
        return

    chart_data = (
        df
        .set_index("timestamp")
        [[metric, "node"]]
    )

    nodes = chart_data["node"].unique()

    for node in nodes:

        node_data = (
            chart_data[
                chart_data["node"] == node
            ]
            [[metric]]
        )

        st.line_chart(
            node_data
        )


def display_statistics(stats):
    # display summary statistics

    if stats is None:
        return

    columns = st.columns(
        len(stats)
    )

    for column, (name, value) in zip(
        columns,
        stats.items()
    ):

        column.metric(
            name,
            round(value, 2)
        )


def metric_label(metric):
    # convert database names into display names

    labels = {
        "pm1": "pm1 (µg/m³)",
        "pm25": "pm2.5 (µg/m³)",
        "pm4": "pm4 (µg/m³)",
        "pm10": "pm10 (µg/m³)",
        "voc": "voc index",
        "nox": "nox index",
        "co2": "co₂ (ppm)",
        "temperature": "temperature (°c)",
        "humidity": "humidity (%)"
    }

    return labels.get(
        metric,
        metric
    )
    st.line_chart(chart[metric])