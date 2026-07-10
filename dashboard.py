import streamlit as st

from config import REFRESH_SECONDS, ROOMS
from database import count_measurements, get_nodes, latest_timestamp
from views import (
    render_data_manager,
    render_event_analysis,
    render_event_logging,
    render_historical_analysis,
    render_live_monitor,
    render_room_comparison,
)
from views.common import format_timestamp


st.set_page_config(
    page_title="Indoor Air Quality Research Platform",
    layout="wide",
)


PAGES = {
    "Live Monitor": render_live_monitor,
    "Event Logging": render_event_logging,
    "Historical Analysis": render_historical_analysis,
    "Room Comparison": render_room_comparison,
    "Event Analysis": render_event_analysis,
    "Data Export": render_data_manager,
}


def main():
    st.title("Indoor Air Quality Research Platform")
    st.caption(
        "ESP32 sensors feed Flask and SQLite; this dashboard turns that stream into a research workflow."
    )

    latest = latest_timestamp()
    measurements = count_measurements()
    nodes = get_nodes()

    overview = st.columns(4)
    overview[0].metric("Configured rooms", len(ROOMS))
    overview[1].metric("Rooms with data", len(nodes))
    overview[2].metric("Measurements", f"{measurements:,}")
    overview[3].metric("Latest update", format_timestamp(latest) if latest is not None else "n/a")

    with st.sidebar:
        st.header("Navigation")
        page_name = st.radio("View", list(PAGES.keys()))
        st.divider()
        st.subheader("Pipeline")
        st.write("SEN66 → ESP32 → Flask → SQLite → Streamlit")
        st.caption(f"Dashboard refresh target: every {REFRESH_SECONDS} seconds")
        if latest is not None:
            st.caption(f"Latest data: {format_timestamp(latest)}")

    PAGES[page_name]()


if __name__ == "__main__":
    main()
