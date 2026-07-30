# Indoor Airflow and Pollutant Transport Tracking

A three-room indoor air quality monitoring network built around a custom
ESP32 + Sensirion SEN66 PCB, with a labelling and analysis platform for
answering one question:

> **When a pollution event happens in one room, how does that air actually
> move through the home — how long does it take to reach the other rooms,
> how much of it survives the journey, and how quickly does it clear?**

Most consumer monitors report a number for the room they sit in. With
three synchronised nodes and a log of when events actually happened, each
event becomes a **tracer release** into a known floor plan: the same
kitchen plume is measured simultaneously in three rooms against a single
server clock. Repeated events then give repeated measurements of the same
transport path, which is what makes lag, attenuation, and clearance
measurable rather than anecdotal.

**Status:** hardware and pipeline complete and collecting; transport
analysis implemented and validated on real events (see
[Method validation](#method-validation)); results being prepared for
journal submission and not published here yet.

---

## Contents

- [Architecture](#architecture)
- [The dashboard](#the-dashboard)
- [Hardware](#hardware)
- [Repository layout](#repository-layout)
- [Getting started](#getting-started)
- [Data and methods](#data-and-methods)
- [Method validation](#method-validation)
- [Design decisions worth knowing](#design-decisions-worth-knowing)
- [License](#license)

---

## Architecture

Three identical sensor nodes push readings over WiFi to a local Flask
server, which timestamps and stores them in SQLite. A Streamlit dashboard
reads the same database — for live monitoring, for recording ground-truth
labels, and for exporting the joined dataset that feeds the transport
analysis.

```mermaid
flowchart LR
    subgraph Rooms
        K["Kitchen node<br/>ESP32 + SEN66"]
        L["Living Room node<br/>ESP32 + SEN66"]
        B["Bedroom node<br/>ESP32 + SEN66"]
    end

    K -->|HTTP POST / 5 s| F
    L -->|HTTP POST / 5 s| F
    B -->|HTTP POST / 5 s| F

    F["Flask ingestion server<br/>server.py"] -->|server timestamp| D[("SQLite<br/>air_quality.db")]

    D --> S["Streamlit dashboard<br/>dashboard.py"]
    S -->|"events + room states"| D
    D --> X["Labelled export<br/>dataset.py"]
    X --> M["Transport analysis<br/>transport.py"]

    style D fill:#2b6cb0,color:#fff
    style S fill:#2f855a,color:#fff
    style M fill:#744210,color:#fff
```

Everything runs on a local machine on the home network — no cloud
dependency, no third-party data handling.

**Why the timestamps come from the server.** Nodes never send their own
clocks. Three ESP32s would drift apart within hours, and a drifting clock
silently corrupts the very thing this project measures: the *lag* between
a kitchen event and a bedroom response. One clock means readings and
labels are exactly joinable.

---

## The dashboard

The dashboard is not an afterthought or a viewer — it is the labelling
instrument. Ground-truth labels are the scarce resource in this kind of
research, and their quality is bounded by how easy they are to record at
the moment something happens. It runs on the local network, so whoever is
actually in the kitchen can log an event from their phone while it is
happening, rather than someone reconstructing it later from memory.

<!-- Add screenshots to docs/screenshots/ and they will render here -->

### Live monitor
Per-room online/stale/offline status and current readings across all nine
channels, so a dead node is caught in minutes rather than at the end of the day.

![Live monitor](docs/screenshots/live-monitor.png)

### Event logging
The labelling interface: start/stop events against their source room, per-room
toggles for window, exhaust fan, purifier, and AC, and retroactive entry for
anything noticed late.

![Event logging](docs/screenshots/event-logging.png)

### Analysis and export
Threshold-based event detection, cross-room comparison with lag estimation,
and the labelled dataset export that feeds the transport analysis.

![Analysis and export](docs/screenshots/analysis-export.png)

<!-- Optional: a 30-60s screen recording is the single most convincing artefact here
![Dashboard walkthrough](docs/screenshots/dashboard-demo.gif)
-->

**Pages**

| Page | What it does |
|---|---|
| Live Monitor | Node health and current readings per room |
| Event Logging | Record events and room-state changes; the labelling instrument |
| Historical Analysis | Long-range trends with hover-to-inspect exact timestamps |
| Room Comparison | Two-room overlay, correlation, and lag estimation for transport analysis |
| Event Analysis | Threshold-based episode detection with per-event summaries |
| Data Export | Raw CSV export, plus the joined labelled dataset for modelling |

---

## Hardware

Each node is a custom PCB carrying an ESP32 and a Sensirion SEN66
environmental sensor.

**Sensor channels (SEN66):** PM1.0, PM2.5, PM4.0, PM10, VOC Index,
NOx Index, CO₂ equivalent, temperature, relative humidity.

| Item | Qty per node | Notes |
|---|---|---|
| ESP32 module | 1 | WiFi MCU |
| Sensirion SEN66 | 1 | Multi-channel environmental sensor, I²C |
| Custom PCB | 1 | See [`hardware/pcb/`](hardware/pcb/) |
| Power supply | 1 | USB |

> Schematic, board files, Gerbers, and the full bill of materials live in
> [`hardware/`](hardware/). Build photos in
> [`hardware/photos/`](hardware/photos/).

**Firmware** is in [`firmware/esp32_node/`](firmware/esp32_node/). Each
node is flashed with the same sketch, with `NODE_ID` and `NODE_NAME` set
per board. WiFi credentials and the server address go in `secrets.h` —
copy `secrets.h.example` and fill it in; it is git-ignored, so credentials
never reach the repository. Sampling is every 5 s; Sensirion's recommended
temperature-offset compensation is applied on-device.

### Room layout

The three-room layout — sensor positions, corridor geometry, door and
window placement, and kitchen exhaust — determines what transport analysis
is possible and is the anchor figure for the paper.

![Floor plan](docs/figures/floorplan.png)

---

## Repository layout

```
├── server.py                 Flask ingestion endpoint (POST /data)
├── dashboard.py              Streamlit entry point
├── config.py                 Rooms, metrics, event types, state types
├── database.py               Sensor-data queries
├── labels.py                 Event + room-state schema and logic
├── dataset.py                Labelled export: readings joined to events and states
├── transport.py              Airflow analysis: arrival lag, attenuation, clearance
├── metrics.py                Downsampling, statistics, threshold detection
├── plotting.py               Altair charts with hover inspection
├── views/                    One module per dashboard page
├── migrations/               Idempotent schema migrations, run in order
├── tests/                    Unit tests for labelling and join logic
├── tools/                    Utilities (sample dataset generator)
├── firmware/esp32_node/      ESP32 sketch
├── hardware/                 PCB, BOM, build photos
├── docs/                     Figures and dashboard screenshots
└── data/                     Sample dataset and data dictionary
```

---

## Getting started

**Requirements:** Python 3.10+ (developed on 3.14), an ESP32 toolchain for
the firmware.

```bash
py -m pip install -r requirements.txt
```

Apply the schema migrations (safe to re-run; they create tables and
indexes and enable WAL mode):

```bash
py migrations/migrate_add_labels.py
py migrations/migrate_add_logged_at.py
py migrations/migrate_add_ac_state.py
py migrations/migrate_add_sensor_index.py
py migrations/migrate_enable_wal.py
```

Run the ingestion server (creates the database on first run):

```bash
py server.py
```

Run the dashboard in a second terminal:

```bash
py -m streamlit run dashboard.py
```

The dashboard is then reachable at `http://localhost:8501`, and from any
device on the same network at `http://<your-machine-ip>:8501` — which is
how events get logged from the room where they happen.

Run the tests:

```bash
py -m unittest discover -s tests -v
```

---

## Data and methods

A sample slice of real data — four hours, three rooms, two overlapping
labelled cooking events — is in [`data/sample/`](data/sample/), with every
field documented in [`data/DATA_DICTIONARY.md`](data/DATA_DICTIONARY.md).
Calendar dates are shifted to a synthetic epoch; time-of-day and the
sensor values themselves are unmodified.

**Labelling model.** Events are logged once, against their *source* room
only. Room-level conditions (window, exhaust fan, purifier, AC) are logged
as a change history rather than a snapshot. The export then joins each
sensor reading to any overlapping event, tags it `source` or `transport`
depending on whether it is the event's own room, and attaches the
conditions active in that room at that moment via an as-of join.

**Transport metrics.** [`transport.py`](transport.py) turns each event
into one row per room:

| Metric | Meaning |
|---|---|
| `arrival_lag_min` | Minutes between the level rising clear of baseline in the source room and doing so here — *how long the air took to arrive* |
| `xcorr_lag_min` | Independent lag estimate from baseline-subtracted cross-correlation of the whole curve |
| `peak_lag_min` | Lag between peak times (kept for comparison; noisier than arrival) |
| `attenuation` | This room's rise ÷ the source room's rise — *how much survived the trip* |
| `clearance_min` | Time from peak to falling halfway back to baseline — *how fast the room recovers* |
| `snr`, `detected` | Whether the event was measurably present here at all |

Arrival is defined as the level crossing `baseline + 3σ` **and staying
there** for two minutes. The persistence requirement is not cosmetic: over
the ~1,000 samples in an event window, the largest value of pure noise
clears 3σ by chance often enough that a peak-only test reports flat rooms
as detections.

Where an event was not detected in a room, lag and attenuation are
reported as missing rather than computed — a ratio of noise to signal
would look like a measurement without being one.

---

## Method validation

Run against the events logged so far — 18 closed events, almost all
cooking in the kitchen — using PM2.5. These are method-validation numbers
on a small sample, not published findings.

**The signal does travel, and it is measurable.** The event was detected
in the living room in 83% of events and the bedroom in 78%, with median
arrival lags of about 5 minutes to each.

**Event strength controls how trustworthy a lag is.** Stratifying by
source-room signal-to-noise:

| Source SNR | n | Median arrival lag | IQR | Physically sensible (lag > 0) |
|---|---|---|---|---|
| weak (< 25) | 15 | 8.1 min | 18.9 min | 67% |
| medium (25–100) | 4 | 2.0 min | 7.6 min | 50% |
| strong (≥ 100) | 8 | 3.3 min | **5.1 min** | **88%** |

Weak events produce lags scattered across a 19-minute spread, a third of
them pointing the wrong way in time. Strong events tighten to a 5-minute
spread with 88% in the physically sensible direction. The practical
conclusion is that transport analysis should be restricted to events that
clear an SNR floor, and that deliberately staging strong events is worth
more than accumulating weak ones.

**An open question in the data.** The living room frequently registers a
*larger* PM2.5 rise than the kitchen where the cooking happened — median
attenuation 1.44, above 1 in most events. Air does not gain particles in
transit, so this points at something in the setup rather than the
atmosphere: most likely kitchen node placement (a plume rising past the
sensor, or a local draught clearing it), possibly unit-to-unit calibration
differences. **It needs resolving before any attenuation figure is
reported as a result**, since the kitchen node is the reference every
attenuation is measured against. The bedroom, by contrast, behaves as
expected (median 0.87).

Reproduce with:

```python
from transport import event_transport_metrics, transport_summary
metrics = event_transport_metrics(metric="pm25")
print(transport_summary(metrics))
```

---

## Design decisions worth knowing

Choices that are load-bearing for data integrity, and the reasoning behind
each:

- **Server-generated timestamps only.** One clock for readings and labels;
  no cross-device drift in the lag measurements.
- **Background rows are kept.** Readings with no event are exported with an
  empty `event_type` rather than dropped — they are what "ordinary air"
  looks like, and the baseline every rise is measured against.
- **Missing beats fabricated.** Lag and attenuation are reported only when
  the event was actually detected at both ends; otherwise they come back
  empty rather than as a number computed from noise.
- **Unknown is not a default.** Before a room's first recorded state
  change, its window/fan/purifier/AC state is exported as `NULL`, never
  assumed. A wrong assumption is worse than an honest gap.
- **Overlapping events duplicate a row rather than dropping a label.**
- **`logged_at` provenance.** Every label records when it was *entered*
  alongside when it *happened*, so retroactively recalled labels remain
  identifiable and their effect can be tested rather than assumed.
- **Detection runs on full-resolution data.** Charts thin points for
  rendering speed, but statistics and event detection always use every
  sample, so no peak is averaged away before it is counted.
- **WAL journal mode.** Readers and writers no longer block each other;
  before this, a long dashboard query could lock the database and cause
  the ingestion server to silently drop sensor readings.

---

## License

[MIT](LICENSE) — free to use, modify, and build on, with attribution.

If this work is useful in your own research, a citation is appreciated.
Findings are being prepared for journal submission; this repository is the
code and hardware companion.
