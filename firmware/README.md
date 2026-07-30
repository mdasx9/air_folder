# Firmware

ESP32 sketch for a sensor node. All three nodes run the same code; only
the per-board configuration differs.

## Per-node configuration

Edit these at the top of `esp32_node/esp32_node/esp32_node.ino` before
flashing each board:

```cpp
const int NODE_ID   = 3;            // 1, 2, 3
const char* NODE_NAME = "Bedroom";  // must match a room name in config.py

const char* ssid     = "...";       // WiFi
const char* password = "...";

const char* serverName = "http://<server-ip>:5000/data";
```

`NODE_NAME` must match the room names in the project's `config.py`
(`Kitchen`, `Living Room`, `Bedroom`) — it is the key the database joins on.

> **Before publishing:** the committed sketch contains WiFi credentials and
> a local server IP. Replace them with placeholders, or move them into an
> untracked `secrets.h`, before making the repository public.

## Dependencies

- ESP32 board support (Arduino IDE or PlatformIO)
- `SensirionI2cSen66`
- `WiFi`, `HTTPClient` (bundled with the ESP32 core)

## Behaviour

- Reads the SEN66 every 5 s and POSTs JSON to the Flask server
- Applies Sensirion's recommended temperature-offset compensation on-device
- Converts raw integers to physical units before sending (PM ÷10, RH ÷100,
  temperature ÷200)
- Sends no timestamp — the server supplies it, so all nodes share one clock

## Known limitation

`connectWiFi()` calls `WiFi.begin()` once and then waits indefinitely for a
connection. If the ESP32's WiFi stack wedges after certain router events,
the node stops reporting until it is power-cycled, and no data is recorded
in the meantime. Observed in practice: two nodes silent for 8.5 hours after
a single router event while the third kept reporting.

A reconnect timeout plus `ESP.restart()` after repeated failures would turn
that into a ~30 s gap. Not yet implemented — power-cycling is the current
workaround.
