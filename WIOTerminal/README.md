# WIO Terminal — SHT40 Monitor (CircuitPython, no IDE needed)

Part of the **Datacenter Thermal Control** system.  
The WIO Terminal reads the Seeed Grove SHT40 sensor, shows a live dashboard
on its 320×240 display, and can stream readings either over:

- **USB serial** to the Raspberry Pi / PC host, or
- **WiFi HTTP POST** directly to the FastAPI server running on the host.

> **No Arduino IDE, no compilation, no toolchain.**  
> After a one-time firmware flash you only ever copy text files to a USB drive.

---

## Hardware

| Component | Details |
|-----------|---------|
| **MCU** | Seeed Studio WIO Terminal (ATSAMD51P19A, Cortex-M4 @ 120 MHz) |
| **Sensor** | Seeed Grove SHT40 Temperature & Humidity |
| **Sensor connection** | Right-side Grove I²C port (SDA/SCL) |
| **RPi connection** | USB-C → USB-A → `/dev/ttyACM0` on Raspberry Pi OS |
| **Display** | Built-in 2.4″ TFT 320×240 ILI9341 |

### Wiring — SHT40 Grove → WIO Terminal (right Grove port)

```
SHT40 Grove   →   WIO Terminal
   VCC        →   3.3 V
   GND        →   GND
   SDA        →   SDA
   SCL        →   SCL
```

---

## Deployment — 3 steps, no IDE

### Step 1 — Flash CircuitPython (one-time, ~2 minutes)

1. Download the WIO Terminal CircuitPython UF2 from:  
   **https://circuitpython.org/board/seeeduino_wio_terminal**  
   (choose the latest stable 9.x release)

2. Enter bootloader mode on the WIO Terminal:  
   **Double-press** the power slider towards `OFF` rapidly.  
   The RGB LED will pulse green and a USB drive called **`WIO-BOOT`** appears.

3. Drag-and-drop the downloaded `.uf2` file onto `WIO-BOOT`.  
   The device reboots automatically.  
   A new USB drive called **`CIRCUITPY`** appears — firmware done.

> You only do this step once. After this, just copy files.

---

### Step 2 — Copy libraries

Download the **Adafruit CircuitPython Bundle** matching your firmware version:  
**https://circuitpython.org/libraries**

Unzip the bundle and copy **only** these items into `CIRCUITPY/lib/`:

| Copy from bundle | Destination |
|------------------|-------------|
| `adafruit_sht4x.mpy` | `CIRCUITPY/lib/adafruit_sht4x.mpy` |
| `adafruit_display_text/` folder | `CIRCUITPY/lib/adafruit_display_text/` |
| `adafruit_ili9341.mpy` | `CIRCUITPY/lib/adafruit_ili9341.mpy` |
| `adafruit_bus_device/` folder | `CIRCUITPY/lib/adafruit_bus_device/` |
| `adafruit_esp32spi/` folder | `CIRCUITPY/lib/adafruit_esp32spi/` |
| `adafruit_requests.mpy` | `CIRCUITPY/lib/adafruit_requests.mpy` |

See `circuitpython_libraries.txt` for the exact directory layout.

> Without `adafruit_esp32spi/` and `adafruit_requests.mpy`, WiFi mode will fail.

---

### Step 3 — Copy the program

Copy `code.py` from this folder to the **root** of `CIRCUITPY`:

```
CIRCUITPY/
├── code.py                      ← copy from WIOTerminal/code.py
└── lib/
    ├── adafruit_sht4x.mpy
    ├── adafruit_ili9341.mpy
    ├── adafruit_bus_device/
    ├── adafruit_display_text/
    ├── adafruit_esp32spi/
    └── adafruit_requests.mpy
```

The WIO Terminal auto-runs `code.py` immediately on save — **done**.

To update the code later: open `CIRCUITPY/code.py` in any text editor,
edit and save — the device restarts and runs the new version instantly.

### Step 4 — Configure WiFi push to a Windows hotspot host

Create `CIRCUITPY/settings.toml` from `settings_template.toml` and set:

```toml
WIFI_SSID = "YourHotspotName"
WIFI_PASSWORD = "YourHotspotPassword"
SERVER_HOST = "192.168.137.1"
SERVER_PORT = "8000"
```

Optional stability tuning:

```toml
HTTP_TIMEOUT = "3.0"
PUSH_INTERVAL = "2.0"
WIFI_RETRY_S = "8.0"
WIFI_DHCP_WAIT_S = "10.0"
WIFI_CONNECT_ATTEMPTS = "3"
WIFI_FAIL_BEFORE_RESET = "3"
WIFI_POWERUP_WAIT_S = "1.8"
WIFI_READY_WAIT_S = "1.5"
RTL_SPI_MODE = "auto"
```

For **Windows Mobile Hotspot**, use these settings for best compatibility:

1. Set the hotspot **band to 2.4 GHz**.
2. Use a simple **SSID/password** with only letters/numbers.
3. Make sure the PC stays awake while the hotspot is enabled.
4. Confirm the FastAPI server opens at:

```text
http://192.168.137.1:8000/api/wio
```

If that URL works from another device on the hotspot, the server side is ready.

If the wireless coprocessor still fails before associating, keep:

```toml
RTL_SPI_MODE = "auto"
```

This makes the updated code try both `RTL_DIR` polarities, because some WIO setups appear to require the opposite SPI/UART mode-select level.

---

## Display layout

```
┌────────────────────────────────────────────────────┐
│              Datacenter  SHT40                     │  ← dark teal header
├──────────────────────┬─────────────────────────────┤
│                      │                             │
│       TEMP           │        HUM                  │  ← cyan label
│                      │                             │
│       23.4           │       55.3                  │  ← large coloured value
│                      │                             │
│       deg C          │       % RH                  │  ← grey unit
│                      │                             │
├──────────────────────┴─────────────────────────────┤
│ [HW]  SHT40  |  Readings: 42                      │  ← status bar
└────────────────────────────────────────────────────┘
```

### Colour coding

| Colour | Temperature | Humidity |
|--------|-------------|---------|
| 🟢 Green | < 25 °C | < 60 % |
| 🟡 Yellow | 25–29.9 °C | 60–69.9 % |
| 🔴 Red | ≥ 30 °C | ≥ 70 % |

Status bar shows `[SIM]` in yellow when no SHT40 is detected and
simulated data is being streamed.

---

## Serial output (USB → Raspberry Pi)

Every `READ_INTERVAL` seconds (default: 2 s) the WIO Terminal prints one line:

```json
{"node":"wio_sht40_01","temperature":23.45,"humidity":55.30,"source":"SHT40","simulation":false}
```

A startup marker is printed once on boot:

```json
{"event":"startup","node":"wio_sht40_01","sensor":"SHT40","simulation":false}
```

`"simulation": true` means the SHT40 was not found; values are synthetic.

---

## Host integration

`sensor_reader.py` reads this serial stream when `SENSOR_TYPE = "SHT40_USB"`.

Set in `config.py`:

```python
SENSOR_TYPE     = "SHT40_USB"
WIO_SERIAL_PORT = "/dev/ttyACM0"   # verify with:  ls /dev/ttyACM*
WIO_SERIAL_BAUD = 115200
```

Full data path:

```
SHT40 → I²C → WIO Terminal → USB Serial (JSON) →
  sensor_reader.py → FastAPI → MQTT/SNMP → WebSocket → React dashboard → SQLite
```

WiFi push path:

```text
SHT40 → I²C → WIO Terminal → WiFi POST /api/wio_reading →
  sensor_reader.push_external() → FastAPI → MQTT/SNMP → WebSocket → React dashboard
```

## Windows hotspot troubleshooting

If the WIO joins the hotspot inconsistently:

1. Verify the hotspot is **2.4 GHz**, not 5 GHz.
2. Keep `SERVER_HOST = "192.168.137.1"` in `settings.toml`.
3. Confirm `http://192.168.137.1:8000/api/wio` is reachable from a phone/laptop on the same hotspot.
4. Use the updated `code.py`, which now:
   - retries WiFi association,
   - waits longer for DHCP,
   - tries both `RTL_DIR` SPI-mode polarities automatically,
   - records `RTL_READY` behavior during boot,
   - probes the server after connect,
   - sends HTTP less aggressively (`PUSH_INTERVAL = 2.0` by default),
   - resets the RTL8720DN coprocessor after repeated failures.
5. If needed, increase:

```toml
WIFI_DHCP_WAIT_S = "15.0"
WIFI_RETRY_S = "12.0"
PUSH_INTERVAL = "3.0"
```

---

## Button reference

| Button (top panel) | Action |
|--------------------|--------|
| **C** — leftmost | Force an immediate sensor read |
| **B** — middle | Reserved |
| **A** — rightmost | Reserved |

---

## Updating the code

Edit `CIRCUITPY/code.py` in any text editor (Notepad, VS Code, nano, vim…).
Save the file — the WIO Terminal auto-restarts and runs the new version.
No build step. No upload command. No IDE.

---

## Updating CircuitPython firmware

Re-enter bootloader (double-press power slider) and repeat Step 1.  
Your `code.py` and `lib/` files survive unless you deliberately delete them.

---

## Arduino fallback

`WIOTerminal.ino` contains an Arduino IDE sketch with identical serial output.  
Use it only if CircuitPython is unsuitable for your deployment.  
See comments at the top of that file for Arduino IDE board/library setup.
