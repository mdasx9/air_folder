import pandas as pd


# =====================================================
# DATA DOWNSAMPLING
# =====================================================

def downsample(df):
    """
    Reduce number of points for plotting while
    preserving trends.

    Used automatically for large datasets.
    """

    if df.empty:
        return df

    df = df.copy()

    if "node" in df.columns and df["node"].nunique() > 1:
        pieces = []

        for node, node_df in df.groupby("node", sort=False):
            sampled = downsample(node_df.drop(columns=["node"]))
            sampled["node"] = node
            pieces.append(sampled)

        result = pd.concat(pieces, ignore_index=True)
        return result.sort_values("timestamp").reset_index(drop=True)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    points = len(df)

    if points < 10000:
        result = df.reset_index()
        return result

    if points < 50000:
        interval = "1min"
    elif points < 200000:
        interval = "5min"
    else:
        interval = "15min"

    numeric_columns = df.select_dtypes(include="number").columns
    result = df[numeric_columns].resample(interval).mean().dropna()
    return result.reset_index()



# =====================================================
# BASIC STATISTICS
# =====================================================

def summary_statistics(df, metric):

    if df.empty:
        return None


    return {
        "Average": df[metric].mean(),
        "Minimum": df[metric].min(),
        "Maximum": df[metric].max(),
        "Median": df[metric].median()
    }



# =====================================================
# DAILY SUMMARY
# =====================================================

def daily_average(df):

    if df.empty:
        return df


    df = df.copy()

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )


    df = df.set_index(
        "timestamp"
    )


    numeric = df.select_dtypes(
        include="number"
    )


    return (
        numeric
        .resample("1D")
        .mean()
        .reset_index()
    )



# =====================================================
# ROLLING AVERAGES
# =====================================================

def rolling_average(
    df,
    metric,
    window="15min"
):

    if df.empty:
        return df


    df = df.copy()


    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )


    df = df.set_index(
        "timestamp"
    )


    df[f"{metric}_rolling"] = (
        df[metric]
        .rolling(window)
        .mean()
    )


    return df.reset_index()



# =====================================================
# POLLUTION EVENTS
# =====================================================

def detect_events(
    df,
    metric,
    threshold
):

    """
    Finds periods where a metric exceeds
    a chosen threshold.

    Example:
    PM2.5 > 35 µg/m³
    """

    if df.empty:
        return pd.DataFrame()


    events = df[
        df[metric] > threshold
    ].copy()


    return events


def summarize_events(
    df,
    metric,
    threshold,
    gap_minutes=10
):

    if df.empty:
        return pd.DataFrame()

    events = detect_events(df, metric, threshold)

    if events.empty:
        return pd.DataFrame()

    events = events.copy()
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    events = events.sort_values("timestamp")

    event_breaks = (
        events["timestamp"]
        .diff()
        .gt(pd.Timedelta(minutes=gap_minutes))
        .cumsum()
    )

    summary = (
        events.groupby(event_breaks)
        .agg(
            start_time=("timestamp", "min"),
            end_time=("timestamp", "max"),
            peak_value=(metric, "max"),
            mean_value=(metric, "mean"),
            num_points=("timestamp", "size")
        )
        .reset_index(drop=True)
    )

    summary["duration_minutes"] = (
        summary["end_time"] - summary["start_time"]
    ).dt.total_seconds() / 60.0

    if "node" in events.columns:
        summary["node"] = events["node"].iloc[0]

    return summary
