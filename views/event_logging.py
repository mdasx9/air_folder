import pandas as pd
import streamlit as st

import labels
from config import EVENT_TYPES, MAX_BACKDATE_DAYS, MAX_BACKDATE_MINUTES, ROOM_SLUGS, STATE_TYPES
from views.common import format_timestamp


def _datetime_picker(container, label, key, default=None):
    """Date + time inputs side by side, returned as one datetime."""

    default = default or pd.Timestamp.now().floor("min").to_pydatetime()

    picked_date = container.date_input(
        f"{label} date",
        value=default.date(),
        max_value=pd.Timestamp.now().date(),
        key=f"{key}_date",
    )
    picked_time = container.time_input(
        f"{label} time",
        value=default.time(),
        step=60,
        key=f"{key}_time",
    )

    return pd.Timestamp.combine(picked_date, picked_time).to_pydatetime()


SLUG_TO_ROOM = {slug: label for label, slug in ROOM_SLUGS.items()}

# state_type -> (toggle label, value when on, value when off)
STATE_TOGGLES = {
    "window": ("Window open", "open", "closed"),
    "exhaust_fan": ("Exhaust fan on", "on", "off"),
    "purifier": ("Purifier on", "on", "off"),
    "ac": ("AC on", "on", "off"),
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
            st.dataframe(status, width="stretch", hide_index=True)

    with right:
        st.markdown("**Room states**")

        rows = []
        for room_label, slug in ROOM_SLUGS.items():
            row = {"Room": room_label}
            for state_type in STATE_TYPES:
                row[state_type] = state_lookup.get((slug, state_type), "unknown")
            rows.append(row)

        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("'unknown' means no change has been logged yet for that room and state.")



def _render_log_event(open_df):

    st.subheader("Log Event")
    st.caption("Log an event against its SOURCE room only; the export joins in the other rooms automatically.")

    controls = st.columns(4)
    room_label = controls[0].selectbox("Source room", list(ROOM_SLUGS.keys()))
    event_type = controls[1].selectbox("Event type", EVENT_TYPES)
    subtype = controls[2].text_input("Subtype (optional)", placeholder="stovetop, vacuum, person_entered...")
    notes = controls[3].text_input("Notes (optional)")

    start_columns = st.columns([1, 3])
    started_minutes_ago = start_columns[0].number_input(
        "Started (min ago)",
        min_value=0,
        max_value=MAX_BACKDATE_MINUTES,
        value=0,
        help="Leave at 0 for something starting right now; set it if you noticed late.",
    )

    if start_columns[1].button("Start event", type="primary"):
        try:
            labels.start_event(
                ROOM_SLUGS[room_label],
                event_type,
                subtype,
                notes,
                started_minutes_ago=started_minutes_ago,
            )
            st.rerun()
        except labels.DuplicateOpenEventError as err:
            st.error(str(err))

    st.markdown("**Open events**")

    if open_df.empty:
        st.caption("No open events. Start one above when something happens.")
    else:
        for event in open_df.itertuples(index=False):
            description, elapsed, ended_ago, action = st.columns([4, 1, 1, 1])

            subtype_text = f" ({event.subtype})" if event.subtype else ""
            description.write(
                f"**{event.event_type}**{subtype_text} in {SLUG_TO_ROOM.get(event.room, event.room)} "
                f"— started {format_timestamp(event.start_time)}"
            )
            elapsed.write(_elapsed_text(event.start_time))

            ended_minutes_ago = ended_ago.number_input(
                "Ended (min ago)",
                min_value=0,
                max_value=MAX_BACKDATE_MINUTES,
                value=0,
                key=f"ended_ago_{event.id}",
            )

            if action.button("Stop", key=f"stop_event_{event.id}"):
                try:
                    labels.stop_event(event.id, ended_minutes_ago=ended_minutes_ago)
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))

    _render_past_event_form()


def _render_past_event_form():

    with st.expander("Log a completed past event (forgot to log it live?)", expanded=False):
        st.caption(
            "For events that already ended — pick the exact date and time they "
            f"started and finished, up to {MAX_BACKDATE_DAYS} days back."
        )

        controls = st.columns(4)
        room_label = controls[0].selectbox("Source room", list(ROOM_SLUGS.keys()), key="past_room")
        event_type = controls[1].selectbox("Event type", EVENT_TYPES, key="past_type")
        subtype = controls[2].text_input("Subtype (optional)", key="past_subtype")
        notes = controls[3].text_input("Notes (optional)", key="past_notes")

        timing = st.columns(2)
        default_start = (pd.Timestamp.now() - pd.Timedelta(minutes=30)).floor("min").to_pydatetime()
        default_end = (pd.Timestamp.now() - pd.Timedelta(minutes=15)).floor("min").to_pydatetime()

        start_time = _datetime_picker(timing[0], "Started", "past_start", default_start)
        end_time = _datetime_picker(timing[1], "Ended", "past_end", default_end)

        if st.button("Log past event"):
            try:
                labels.log_past_event(
                    ROOM_SLUGS[room_label],
                    event_type,
                    start_time=start_time,
                    end_time=end_time,
                    subtype=subtype,
                    notes=notes,
                )
                st.success(
                    f"Recorded {event_type} in {room_label}: "
                    f"{format_timestamp(start_time)} to {format_timestamp(end_time)}."
                )
            except ValueError as err:
                st.error(str(err))



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

    _render_backdated_state_form()


def _render_backdated_state_form():

    with st.expander("Backdate a state change (changed earlier, logged late?)", expanded=False):
        st.caption(
            "For a change that really happened a while ago — e.g. a window opened an hour "
            "ago but nobody toggled it. The correction slots into history at the time you "
            f"give, so past exports come out right. Up to {MAX_BACKDATE_DAYS} days back."
        )

        controls = st.columns([1, 1, 1, 2])
        room_label = controls[0].selectbox("Room", list(ROOM_SLUGS.keys()), key="backdate_room")
        state_type = controls[1].selectbox(
            "State",
            list(STATE_TOGGLES.keys()),
            format_func=lambda s: STATE_TOGGLES[s][0],
            key="backdate_state",
        )
        state_value = controls[2].selectbox("Became", STATE_TYPES[state_type], key="backdate_value")
        changed_at = _datetime_picker(
            controls[3],
            "Changed",
            "backdate_changed",
            (pd.Timestamp.now() - pd.Timedelta(minutes=30)).floor("min").to_pydatetime(),
        )

        if st.button("Record", key="backdate_submit"):
            try:
                inserted = labels.set_room_state(
                    ROOM_SLUGS[room_label],
                    state_type,
                    state_value,
                    changed_at=changed_at,
                )
                if inserted:
                    st.success(
                        f"Recorded: {room_label} {STATE_TOGGLES[state_type][0].lower()} "
                        f"became '{state_value}' at {format_timestamp(changed_at)}."
                    )
                else:
                    st.info(
                        f"{room_label} {STATE_TOGGLES[state_type][0].lower()} was already "
                        f"'{state_value}' at that time — nothing to record."
                    )
            except ValueError as err:
                st.error(str(err))



def _render_recent_events():

    with st.expander("Recent events (open and closed)", expanded=False):
        recent = labels.recent_events(limit=25)

        if recent.empty:
            st.caption("No events logged yet.")
            return

        recent = recent.copy()
        recent["room"] = recent["room"].map(SLUG_TO_ROOM).fillna(recent["room"])
        st.dataframe(recent, width="stretch", hide_index=True)



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
