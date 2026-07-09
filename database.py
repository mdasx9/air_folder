import sqlite3
import pandas as pd

from datetime import datetime, timedelta

from config import DATABASE_PATH, OFFLINE_THRESHOLD_SECONDS


# =====================================================
# CONNECTION
# =====================================================

def get_connection():

    return sqlite3.connect(
        DATABASE_PATH,
        check_same_thread=False
    )


# =====================================================
# DATABASE INFORMATION
# =====================================================

def count_measurements():

    conn = get_connection()

    query = """
    SELECT COUNT(*)
    FROM sensor_data
    """

    result = conn.execute(query).fetchone()[0]

    conn.close()

    return result



def latest_timestamp():

    conn = get_connection()

    query = """
    SELECT MAX(timestamp)
    FROM sensor_data
    """

    result = conn.execute(query).fetchone()[0]

    conn.close()

    if result:
        return pd.to_datetime(result)

    return None



def get_nodes():

    conn = get_connection()

    query = """
    SELECT DISTINCT node
    FROM sensor_data
    ORDER BY node
    """

    df = pd.read_sql_query(
        query,
        conn
    )

    conn.close()

    return df["node"].tolist()



# =====================================================
# DATA LOADING
# =====================================================

def load_data(
    nodes=None,
    hours=None,
    start_time=None,
    end_time=None
):

    conn = get_connection()

    query = """
    SELECT *
    FROM sensor_data
    WHERE 1=1
    """

    params = []


    if nodes:

        placeholders = ",".join(
            ["?"] * len(nodes)
        )

        query += f"""
        AND node IN ({placeholders})
        """

        params.extend(nodes)



    if hours:

        cutoff = datetime.now() - timedelta(
            hours=hours
        )

        query += """
        AND timestamp >= ?
        """

        params.append(
            cutoff.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )


    elif start_time and end_time:

        query += """
        AND timestamp BETWEEN ? AND ?
        """

        params.extend(
            [
                start_time,
                end_time
            ]
        )


    query += """
    ORDER BY timestamp
    """


    df = pd.read_sql_query(
        query,
        conn,
        params=params,
        parse_dates=[
            "timestamp"
        ]
    )


    conn.close()

    return df



# =====================================================
# LATEST DATA
# =====================================================

def latest_readings(limit=50):

    conn = get_connection()

    query = """
    SELECT *
    FROM sensor_data
    ORDER BY timestamp DESC
    LIMIT ?
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=[limit],
        parse_dates=[
            "timestamp"
        ]
    )

    conn.close()

    return df



# =====================================================
# LIVE NODE STATUS
# =====================================================

def node_status():

    nodes = get_nodes()

    results = []

    now = datetime.now()


    for node in nodes:

        conn = get_connection()

        query = """
        SELECT MAX(timestamp)
        FROM sensor_data
        WHERE node = ?
        """

        last_seen = conn.execute(
            query,
            [node]
        ).fetchone()[0]

        conn.close()


        if last_seen:

            last_seen = pd.to_datetime(
                last_seen
            )

            seconds_ago = (
                now - last_seen
            ).total_seconds()

            online = (
                seconds_ago <
                OFFLINE_THRESHOLD_SECONDS
            )


            results.append(
                {
                    "node": node,
                    "last_seen": last_seen,
                    "seconds_ago": seconds_ago,
                    "online": online
                }
            )


    return pd.DataFrame(results)



# =====================================================
# CURRENT SENSOR VALUES
# =====================================================

def current_values(node):

    conn = get_connection()

    query = """
    SELECT *
    FROM sensor_data
    WHERE node = ?
    ORDER BY timestamp DESC
    LIMIT 1
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=[node],
        parse_dates=[
            "timestamp"
        ]
    )

    conn.close()

    return df



# =====================================================
# EXPORT
# =====================================================

def export_data():

    return load_data()