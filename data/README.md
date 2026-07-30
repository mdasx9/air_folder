# Data

The live database (`air_quality.db`) is **not** committed — it is hundreds
of megabytes and contains continuous household data. This folder holds a
small, anonymised, self-contained sample instead.

| File | Purpose |
|---|---|
| [`DATA_DICTIONARY.md`](DATA_DICTIONARY.md) | Every field, its units, and how to read it |
| `sample/sample_readings.csv` | Raw readings — 4 h, three rooms |
| `sample/sample_events.csv` | Two overlapping labelled cooking events |
| `sample/sample_room_states.csv` | Room-condition change history |
| `sample/sample_labeled_dataset.csv` | The joined long-format table the classifier consumes |

Regenerate from the live database with:

```bash
py tools/make_sample_dataset.py
```

## Anonymisation

Calendar dates are shifted to a synthetic epoch, so the files do not
reveal which real days the household was doing what. **Time-of-day is
preserved** — when an event happens is part of what makes the data
meaningful. Free-text notes are blanked. Sensor values are otherwise
unmodified real measurements.

Before publishing any further data, it is worth remembering what
continuous indoor air quality data reveals: CO₂ tracks occupancy, so a
full export shows when the home is empty, when people sleep, and when they
cook. That is the reason only a short slice is published rather than the
full archive.

## Why the sample looks the way it does

It is a deliberately chosen four-hour window rather than a random slice,
because it contains **two overlapping cooking events**. That exercises the
one join behaviour most likely to surprise someone reusing this data: when
events overlap, an affected reading appears once *per event*, so the
labelled table has more rows (9,340) than there are raw readings (8,002).
De-duplicate on `(timestamp, room)` if your pipeline assumes one row per
reading.
