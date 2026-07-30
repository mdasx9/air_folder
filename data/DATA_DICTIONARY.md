# Data Dictionary

Every field produced by this project, in the order a reader meets them:
raw sensor readings, the two labelling tables, and the joined dataset the
classifier consumes.

All timestamps are **server-generated** and stored as text in
`YYYY-MM-DD HH:MM:SS` (local time, no timezone suffix). Nodes do not send
their own clocks, so sensor readings and labels share one time base and
can be joined exactly.

---

## 1. `sensor_data` — raw readings

One row per node per sample. Nominal interval is 5 s; the true interval is
closer to 5.3–5.5 s because the firmware waits 5 s *plus* the time taken
to read the sensor and POST.

| Column | Type | Units | Notes |
|---|---|---|---|
| `id` | integer | — | Auto-increment primary key |
| `timestamp` | text | — | When the server received the reading |
| `node` | text | — | Room name: `Kitchen`, `Living Room`, `Bedroom` |
| `pm1` | real | µg/m³ | Particulate matter ≤ 1.0 µm |
| `pm25` | real | µg/m³ | Particulate matter ≤ 2.5 µm |
| `pm4` | real | µg/m³ | Particulate matter ≤ 4.0 µm |
| `pm10` | real | µg/m³ | Particulate matter ≤ 10 µm |
| `voc` | real | index | Sensirion VOC Index, ~1–500, 100 = recent baseline |
| `nox` | real | index | Sensirion NOx Index, ~1–500, 1 = baseline |
| `co2` | real | ppm | CO₂ equivalent |
| `temperature` | real | °C | With Sensirion's recommended offset compensation applied on-device |
| `humidity` | real | % RH | Relative humidity |

**Reading the index channels.** VOC and NOx are *not* concentrations. They
are adaptive indices scored against a rolling baseline the sensor learns,
so a value of 100 means "typical for this room lately", not a fixed
chemical amount. This matters for interpretation: after a long quiet
period the baseline drifts, so identical cooking events can produce
different index peaks on different days. Absolute comparisons across weeks
are unsafe; within-event dynamics are the useful signal.

---

## 2. `events` — discrete labelled episodes

One row per event, logged against its **source room only**. Propagation to
other rooms is derived at join time, not logged by hand.

| Column | Type | Notes |
|---|---|---|
| `id` | integer | Primary key |
| `room` | text | Source room slug: `kitchen`, `living_room`, `bedroom` |
| `event_type` | text | `cooking`, `cleaning`, `candle`, `occupancy_change` |
| `subtype` | text, nullable | Free text, e.g. `frying`, `vacuum`, `person_entered` |
| `start_time` | text | When the event began |
| `end_time` | text, nullable | `NULL` while the event is still open |
| `notes` | text, nullable | Free text (blanked in the public sample) |
| `logged_at` | text | When the row was actually entered — see provenance below |

**Constraint.** A partial unique index forbids two *open* events of the
same `(room, event_type)` at once. Closed events are unconstrained, so the
same event type can recur any number of times.

**Provenance (`logged_at`).** For a label entered live, `logged_at ≈
start_time`. For one entered retroactively, they differ — the gap is how
long after the fact it was recalled. This makes recalled labels
identifiable, so their effect on model performance can be tested rather
than assumed. Both events in the sample were logged ~2 h after the fact,
so they carry that signature.

---

## 3. `room_states` — continuous conditions

A change log, not a snapshot: one row each time a condition actually
changes. Repeated identical values are rejected at write time, so the
table stays sparse and every row is a real transition.

| Column | Type | Notes |
|---|---|---|
| `id` | integer | Primary key |
| `room` | text | `kitchen`, `living_room`, `bedroom` |
| `state_type` | text | `window`, `exhaust_fan`, `purifier`, `ac` |
| `state_value` | text | `open`/`closed` for windows; `on`/`off` for the rest |
| `changed_at` | text | When the condition changed |
| `logged_at` | text | When the row was entered (see provenance above) |

**Querying it.** The state at any moment is the most recent change at or
before that moment ("as-of" join). Before a room's first recorded change
the state is genuinely **unknown** and is returned as `NULL` — never
assumed to be a default. Treat `NULL` as missing data, not as "closed".

---

## 4. `sample_labeled_dataset.csv` — the joined training table

Produced by `build_labeled_dataset(start, end, buffer_minutes)`. Tidy long
format: **one row per room per timestamp per overlapping event**. Rooms are
deliberately *not* pivoted into columns — that happens downstream in
feature extraction, where the shape differs for classification
(source-room only) versus transport analysis (all rooms).

| Column | Notes |
|---|---|
| `timestamp` | Reading time |
| `room` | Room slug of this reading |
| `pm1` … `humidity` | The nine sensor channels, as above |
| `event_id` | Matching event, or empty for background rows |
| `event_type` | Event class, or **empty = the background/no-event class** |
| `subtype` | Event subtype, if any |
| `role` | `source` if this reading's room is the event's room, else `transport`; empty for background |
| `window`, `exhaust_fan`, `purifier`, `ac` | Conditions in **this reading's own room** at this timestamp, via the as-of join; empty = unknown |

Three behaviours worth knowing before modelling:

1. **Background rows are kept on purpose.** A reading with no overlapping
   event is returned with an empty `event_type`. These are the negative
   examples; dropping them would leave a classifier that has never seen
   ordinary air.
2. **Buffered windows.** Each event contributes readings from
   `[start − buffer, end + buffer]`, so pre-event baseline and
   post-event decay are captured. The sample uses ±10 minutes.
3. **Overlapping events duplicate a reading.** If two events overlap, the
   affected readings appear once per event rather than one label being
   silently dropped. The sample contains exactly this case — `fry
   salmon/rice` and `quinoa` overlap — which is why it has more rows
   (9,340) than raw readings (8,002). **De-duplicate on
   `(timestamp, room)` if your pipeline assumes one row per reading.**

---

## 5. The sample files

A four-hour evening window, all three rooms, containing two overlapping
cooking events.

| File | Rows | Contents |
|---|---|---|
| `sample_readings.csv` | 8,002 | Raw readings, three rooms |
| `sample_events.csv` | 2 | The two overlapping cooking events |
| `sample_room_states.csv` | 39 | Full state history up to the window end |
| `sample_labeled_dataset.csv` | 9,340 | The joined table described above |

**Anonymisation.** Calendar dates are shifted to a synthetic epoch
(the window is published as 2024-03-01) so the files do not reveal which
real days the household was doing what. **Time-of-day is preserved**,
because when an event happens is part of what makes the data meaningful.
Free-text notes are blanked. Sensor values are otherwise unmodified real
measurements. Regenerate with `py tools/make_sample_dataset.py`.

`sample_room_states.csv` intentionally includes state changes from *before*
the window: an as-of join needs the last change preceding the window to
know the state at its start.
