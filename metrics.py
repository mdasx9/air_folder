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

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )


    df = df.set_index(
        "timestamp"
    )


    points = len(df)


    # Small datasets:
    # keep raw data
    if points < 10000:

        return df.reset_index()



    # Larger datasets:
    # average into time bins

    if points < 50000:

        interval = "1min"


    elif points < 200000:

        interval = "5min"


    else:

        interval = "15min"



    numeric_columns = df.select_dtypes(
        include="number"
    ).columns


    result = (
        df[numeric_columns]
        .resample(interval)
        .mean()
        .dropna()
    )


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