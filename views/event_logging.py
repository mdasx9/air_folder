import pandas as pd
import streamlit as st

import labels
from config import EVENT_TYPES, ROOM_SLUGS, STATE_TYPES
from views.common import format_timestamp


SLUG_TO_ROOM = {slug: label for label, slug in ROOM_SLUGS.items()}

# state_type -> (toggle label, value when on, value when off)
STATE_TOGGLES = {
    "window": ("Window open", "open", "closed"),
    "exhaust_fan": ("Exhaust fan on", "on", "off"),
    "purifier": ("Purifier on", "on", "off"),
}


def _elapsed_text(start_time):

    elapsed = pd.Timestamp.now() - start_time
    minutes = elapsed.total_seconds() / 60

    if minutes < 90:
        return f"{minutes:.0f} min"

    return f"{minutes / 60:.1f} h"



def _render_status(open_df, state_lookup):

    st.subheader("Current logging status")

    left, right = st.columns(2)

    with left:
        st.markdown("**Active events**")

        if open_df.empty:
            st.caption("No events currently open.")
        else:
            status = pd.DataFrame(
                {
                    "Room": open_df["room"].map(SLUG_TO_ROOM),
                    "Event": open_df["event_type"],
                    "Subtype": open_df["subtype"],
                    "Started": open_df["start_time"].map(format_timestamp),
                    "Elapsed": open_df["start_time"].map(_elapsed_text),
                }
            )
            st.dataframe(status, use_container_width=True, hide_index=True)

    with right:
        st.markdown("**Room states**")

        rows = []
        for room_label, slug in ROOM_SLUGS.items():
            row = {"Room": room_label}
            for state_type in STATE_TYPES:
                row[state_type] = state_lookup.get((slug, state_type), "unknown")
            rows.append(row)

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("'unknown' means no change has been logged yet for that room and state.")



def _render_log_event(open_df):

    st.subheader("Log Event")
    st.caption("Log an event against its SOURCE room only; the export joins in the other rooms automatically.")

    controls = st.columns(4)
    room_label = controls[0].selectbox("Source room", list(ROOM_SLUGS.keys()))
    event_type = controls[1].selectbox("Event type", EVENT_TYPES)
    subtype = controls[2].text_input("Subtype (optional)", placeholder="stovetop, vacuum, person_entered...")
    notes = controls[3].text_input("Notes (optional)")

    if st.button("Start event", type="primary"):
        try:
            labels.start_event(ROOM_SLUGS[room_label], event_type, subtype, notes)
            st.rerun()
        except labels.DuplicateOpenEventError as err:
            st.error(str(err))

    st.markdown("**Open events**")

    if open_df.empty:
        st.caption("No open events. Start one above when something happens.")
        return

    for event in open_df.itertuples(index=False):
        description, elapsed, action = st.columns([4, 1, 1])

        subtype_text = f" ({event.subtype})" if event.subtype else ""
        description.write(
            f"**{event.event_type}**{subtype_text} in {SLUG_TO_ROOM.get(event.room, event.room)} "
            f"— started {format_timestamp(event.start_time)}"
        )
        elapsed.write(_elapsed_text(event.start_time))

        if action.button("Stop", key=f"stop_event_{event.id}"):
            labels.stop_event(event.id)
            st.rerun()



def _render_room_states(state_lookup):

    st.subheader("Room State")
    st.caption("Flip a toggle when the real state changes; a row is only written when the value actually changes.")

    never_logged = []

    for room_label, slug in ROOM_SLUGS.items():
        with st.container(border=True):
            st.markdown(f"**{room_label}**")

            columns = st.columns(len(STATE_TOGGLES))

            for column, (state_type, (label, on_value, off_value)) in zip(
                columns, STATE_TOGGLES.items()
            ):
                known_value = state_lookup.get((slug, state_type))
                current = known_value == on_value

                toggled = column.toggle(
                    label,
                    value=current,
                    key=f"state_{slug}_{state_type}",
                )

                if known_value is None:
                    column.caption("not logged yet")
                    never_logged.append((slug, state_type))

                if toggled != current:
                    labels.set_room_state(
                        slug,
                        state_type,
                        on_value if toggled else off_value,
                    )
                    st.rerun()

    if never_logged:
        st.info(
            f"{len(never_logged)} room/state pairs have no history yet — exports return "
            "'unknown' for them until their first record. Set the toggles to match "
            "reality, then record a baseline."
        )
        if st.button("Record current toggle positions as baseline"):
            for slug, state_type in never_logged:
                label, on_value, off_value = STATE_TOGGLES[state_type]
                is_on = st.session_state.get(f"state_{slug}_{state_type}", False)
                labels.set_room_state(slug, state_type, on_value if is_on else off_value)
            st.rerun()



def _render_recent_events():

    with st.expander("Recent events (open and closed)", expanded=False):
        recent = labels.recent_events(limit=25)

        if recent.empty:
            st.caption("No events logged yet.")
            return

        recent = recent.copy()
        recent["room"] = recent["room"].map(SLUG_TO_ROOM).fillna(recent["room"])
        st.dataframe(recent, use_container_width=True, hide_index=True)



def render():
    st.header("Event Logging")
    st.caption("Ground-truth labels for the classifier: what happened, where, and what the room conditions were.")

    open_df = labels.open_events()

    states = labels.current_room_states()
    state_lookup = {
        (row.room, row.state_type): row.state_value
        for row in states.itertuples(index=False)
    }

    _render_status(open_df, state_lookup)
    st.divider()
    _render_log_event(open_df)
    st.divider()
    _render_room_states(state_lookup)
    _render_recent_events()
