# Hardware

Custom PCB carrying an ESP32 and a Sensirion SEN66. Three identical
boards, one per room.

## What goes here

### `pcb/`
Design and manufacturing files:

- `schematic.pdf` — **the most important single file for a reader.** Export
  a PDF alongside the native files so people can inspect the design without
  installing your EDA tool.
- Native design files (`.kicad_sch`, `.kicad_pcb`, or `.sch`/`.brd`)
- `gerbers/` — the zipped Gerber + drill set actually sent to the fab
- `board-render-top.png`, `board-render-bottom.png` — 3D renders

### `bom/`
Bill of materials. `bom-template.csv` has the expected columns — fill it
in and keep the manufacturer part numbers, since that is what makes a
build genuinely reproducible.

### `photos/`
Build photos. Worth capturing:

- Bare PCB as delivered from the fab
- Assembled board, top and bottom
- A node installed in each room (shows real mounting height and placement)
- All three nodes together

## Notes worth recording here

For a build write-up (Hackster/Hackaday) and for the paper's methods
section, these details matter and are easy to forget later:

- Sensor mounting height and distance from walls, per room
- Why each node sits where it does (and what you avoided — vents,
  direct sunlight, cooking splatter, draughts)
- Any enclosure design, and how airflow reaches the sensor inside it
- Power arrangement per node
- Fab house, board specs (layers, thickness, finish), and unit cost
- Anything that went wrong in revision 1 — this is the most-read part of
  any build write-up
