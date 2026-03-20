"""
code.py  ─  CircuitPython 10 for Seeed WIO Terminal (ATSAMD51P19A)
════════════════════════════════════════════════════════════════════
Datacenter Thermal Control — SHT40 Temperature & Humidity Monitor

Standalone display (no network needed) + optional WiFi push to the
Raspberry Pi FastAPI server at POST /api/wio_reading.

Configure WiFi & server address in settings.toml on CIRCUITPY root:
    WIFI_SSID      = "YourNetworkName"
    WIFI_PASSWORD  = "YourPassword"
    SERVER_HOST    = "192.168.137.1"   ← Windows hotspot host / server IP
    SERVER_PORT    = "8000"
"""

# ── CircuitPython built-ins ───────────────────────────────────────────────────
import board, busio, digitalio, displayio, fourwire, terminalio
import time, math, json, os
from adafruit_display_text import label
import adafruit_ili9341

# ── Optional HTTP / WiFi backends ──────────────────────────────────────────────
try:
    import adafruit_requests
    _REQ_MOD = True
except ImportError:
    adafruit_requests = None
    _REQ_MOD = False

try:
    import wifi as _builtin_wifi
    import socketpool as _builtin_socketpool
    _HAS_BUILTIN_WIFI = True
except ImportError:
    _builtin_wifi = None
    _builtin_socketpool = None
    _HAS_BUILTIN_WIFI = False

try:
    from adafruit_esp32spi import adafruit_esp32spi as _esp32spi
    from adafruit_esp32spi import adafruit_esp32spi_socketpool as _esp32_socketpool
    _HAS_ESP32SPI_WIFI = True
except ImportError:
    _esp32spi = None
    _esp32_socketpool = None
    _HAS_ESP32SPI_WIFI = False

# ══════════════════════════════════════════════════════════════════════════════
#  Configuration  (overrides come from CIRCUITPY/settings.toml)
# ══════════════════════════════════════════════════════════════════════════════

NODE_ID       = "wio_sht40_01"
READ_INTERVAL = 0.5          # seconds between sensor reads

TEMP_WARN_C   = 25.0
TEMP_CRIT_C   = 30.0
HUM_WARN_PCT  = 60.0
HUM_CRIT_PCT  = 70.0

_SSID        = os.getenv("WIFI_SSID",     "")
_WIFI_PASS   = os.getenv("WIFI_PASSWORD", "")
_SERVER_HOST = os.getenv("SERVER_HOST",   "192.168.137.1")
_SERVER_PORT = os.getenv("SERVER_PORT",   "8000")
_API_URL     = "http://{}:{}/api/wio_reading".format(_SERVER_HOST, _SERVER_PORT)
_STATUS_URL  = "http://{}:{}/api/wio".format(_SERVER_HOST, _SERVER_PORT)

def _env_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return float(default)

def _env_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return int(default)

_HTTP_TIMEOUT      = _env_float("HTTP_TIMEOUT", 3.0)
_PUSH_INTERVAL     = _env_float("PUSH_INTERVAL", 2.0)
_WIFI_RETRY_S      = _env_float("WIFI_RETRY_S", 8.0)
_DHCP_WAIT_S       = _env_float("WIFI_DHCP_WAIT_S", 10.0)
_CONNECT_ATTEMPTS  = _env_int("WIFI_CONNECT_ATTEMPTS", 3)
_RECONN_AFTER      = _env_int("WIFI_FAIL_BEFORE_RESET", 3)
_POWERUP_WAIT_S    = _env_float("WIFI_POWERUP_WAIT_S", 1.8)
_READY_WAIT_S      = _env_float("WIFI_READY_WAIT_S", 1.5)
_RTL_MODE          = os.getenv("RTL_SPI_MODE", "auto").strip().lower()

# ══════════════════════════════════════════════════════════════════════════════
#  Colours (24-bit RGB)
# ══════════════════════════════════════════════════════════════════════════════

C_NAVY   = 0x001040
C_TEAL   = 0x004444
C_CARD   = 0x002070
C_BLACK  = 0x000000
C_CYAN   = 0x00FFFF
C_WHITE  = 0xFFFFFF
C_GREEN  = 0x00CC44
C_YELLOW = 0xFFCC00
C_RED    = 0xFF3300
C_GREY   = 0xAAAAAA

# ══════════════════════════════════════════════════════════════════════════════
#  Display — manual ILI9341 init (CircuitPython 10 locks board.DISPLAY in code.py)
#  rotation=180 confirmed correct for WIO Terminal physical mount.
# ══════════════════════════════════════════════════════════════════════════════

displayio.release_displays()
_spi = busio.SPI(clock=board.TFT_SCK, MOSI=board.TFT_MOSI, MISO=board.TFT_MISO)
_bus = fourwire.FourWire(
    _spi, command=board.TFT_DC, chip_select=board.TFT_CS, reset=board.TFT_RESET
)
display = adafruit_ili9341.ILI9341(_bus, width=320, height=240, rotation=180)

_bl = digitalio.DigitalInOut(board.TFT_BACKLIGHT)
_bl.direction = digitalio.Direction.OUTPUT
_bl.value = True

# ── Layout helpers ────────────────────────────────────────────────────────────

def _rect(x, y, w, h, color):
    bm = displayio.Bitmap(w, h, 1)
    p  = displayio.Palette(1); p[0] = color
    return displayio.TileGrid(bm, pixel_shader=p, x=x, y=y)

def _lbl(text, x, y, color, scale=1):
    return label.Label(terminalio.FONT, text=text, color=color, x=x, y=y, scale=scale)

# ── Build display group ───────────────────────────────────────────────────────
root = displayio.Group()
display.root_group = root

root.append(_rect(0, 0, 320, 240, C_NAVY))          # background

root.append(_rect(0, 0, 320, 38, C_TEAL))            # header bar
root.append(_lbl("Datacenter  SHT40", 52, 5, C_CYAN, scale=2))

# Temperature card  x=8  y=40  148×165
root.append(_rect(8, 40, 148, 165, C_CARD))
root.append(_lbl("TEMP",  58,  52, C_CYAN,  scale=2))
lbl_t = _lbl("---.-", 37, 102, C_WHITE, scale=3)
root.append(lbl_t)
root.append(_lbl("deg C", 52, 164, C_GREY,  scale=2))

# Humidity card  x=164  y=40  148×165
root.append(_rect(164, 40, 148, 165, C_CARD))
root.append(_lbl("HUM",  220,  52, C_CYAN,  scale=2))
lbl_h = _lbl("---.-", 193, 102, C_WHITE, scale=3)
root.append(lbl_h)
root.append(_lbl("% RH", 214, 164, C_GREY,  scale=2))

# Status bar  y=208-239
root.append(_rect(0, 208, 320, 32, C_BLACK))
lbl_status = label.Label(
    terminalio.FONT,
    text="{:<52}".format("Booting..."),
    color=C_GREY, x=6, y=218, scale=1,
)
root.append(lbl_status)

def _set_status(text, color=C_GREY):
    lbl_status.text  = "{:<52}".format(text)
    lbl_status.color = color

# ══════════════════════════════════════════════════════════════════════════════
#  I²C + SHT40
#  busio.I2C raises RuntimeError when no Grove sensor is connected (no pull-ups).
#  Wrapping everything ensures a missing sensor always falls back to simulation.
# ══════════════════════════════════════════════════════════════════════════════

i2c       = None
sensor_ok = False
sim_mode  = False
sht       = None

try:
    i2c = busio.I2C(board.SCL, board.SDA)
    import adafruit_sht4x
    sht = adafruit_sht4x.SHT4x(i2c)
    try:
        # MEDPRECISION: ~4 ms measurement — faster response at 0.5 s interval
        sht.mode = adafruit_sht4x.Mode.NOHEAT_MEDPRECISION
    except AttributeError:
        pass
    sensor_ok = True
    _set_status("[HW]  SHT40 OK", C_GREEN)
except Exception:
    sim_mode = True
    _set_status("[SIM]  SHT40 not found  —  simulation", C_YELLOW)

time.sleep(0.4)

# ══════════════════════════════════════════════════════════════════════════════
#  WiFi + HTTP
# ══════════════════════════════════════════════════════════════════════════════

_wifi_ok      = False
_http         = None          # adafruit_requests.Session
_wifi_fail_n  = 0

_wifi_backend = "disabled"
_wifi_error   = ""
_wifi_iface   = None
_rtl_dir_pin  = None
_rtl_pwr_pin  = None
_rtl_spi      = None
_rtl_cs       = None
_rtl_ready    = None
_rtl_dir_value = None
_last_push_at = -9999.0
_next_wifi_retry_at = 0.0


def _emit_event(event, **extra):
    try:
        payload = {"event": event, "node": NODE_ID}
        payload.update(extra)
        print(json.dumps(payload))
    except Exception:
        pass


def _short_error(exc):
    text = "{}: {}".format(type(exc).__name__, exc)
    return text if len(text) <= 42 else text[:39] + "..."


def _has_rtl_wifi_pins():
    needed = ("RTL_CLK", "RTL_MOSI", "RTL_MISO", "RTL_CS", "RTL_READY", "RTL_PWR")
    for name in needed:
        if not hasattr(board, name):
            return False
    return True


def _rtl_mode_candidates():
    if _RTL_MODE in ("1", "true", "high", "spi_high"):
        return [True]
    if _RTL_MODE in ("0", "false", "low", "spi_low"):
        return [False]
    return [True, False]


def _rtl_ready_value():
    if _rtl_ready is None:
        return None
    try:
        return bool(_rtl_ready.value)
    except Exception:
        return None


def _wait_for_ready_window(timeout_s=None):
    if timeout_s is None:
        timeout_s = _READY_WAIT_S
    if _rtl_ready is None:
        return None
    deadline = time.monotonic() + timeout_s
    seen = []
    while time.monotonic() < deadline:
        val = _rtl_ready_value()
        if not seen or seen[-1] != val:
            seen.append(val)
        time.sleep(0.05)
    return seen


def _rtl_ip_text():
    if _wifi_iface is None:
        return ""
    try:
        return _wifi_iface.pretty_ip(_wifi_iface.ip_address)
    except Exception:
        try:
            return str(_wifi_iface.ip_address)
        except Exception:
            return ""


def _rtl_connected():
    if _wifi_iface is None:
        return False
    try:
        if bool(_wifi_iface.is_connected):
            return True
    except Exception:
        pass
    return bool(_rtl_ip_text())


def _set_retry_timer(delay_s=None):
    global _next_wifi_retry_at
    if delay_s is None:
        delay_s = _WIFI_RETRY_S
    _next_wifi_retry_at = time.monotonic() + max(1.0, delay_s)


def _mark_wifi_down(reason, hard_reset=False, exc=None):
    global _wifi_ok, _http, _wifi_fail_n, _wifi_error, _wifi_iface, _rtl_dir_value
    _wifi_ok = False
    _http = None
    _wifi_fail_n = 0
    if exc is not None:
        _wifi_error = _short_error(exc)
    elif reason:
        _wifi_error = reason
    if hard_reset:
        _wifi_iface = None
        _rtl_dir_value = None
    _set_retry_timer()
    _emit_event("wifi_down", backend=_wifi_backend, reason=reason, error=_wifi_error)


def _init_rtl_wifi(force_reset=False, dir_value=None):
    global _wifi_iface, _http, _wifi_backend, _rtl_dir_pin, _rtl_pwr_pin, _rtl_spi, _rtl_cs, _rtl_ready, _rtl_dir_value

    if not _HAS_ESP32SPI_WIFI:
        raise RuntimeError("adafruit_esp32spi libs not installed")
    if not _has_rtl_wifi_pins():
        raise RuntimeError("RTL WiFi pins not exposed by firmware")

    # 1. Setup pins and SPI bus (only once)
    if _rtl_dir_pin is None and hasattr(board, "RTL_DIR"):
        _rtl_dir_pin = digitalio.DigitalInOut(board.RTL_DIR)
        _rtl_dir_pin.direction = digitalio.Direction.OUTPUT
    if _rtl_dir_pin is not None:
        if dir_value is None:
            if _rtl_dir_value is None:
                dir_value = _rtl_mode_candidates()[0]
            else:
                dir_value = _rtl_dir_value
        _rtl_dir_pin.value = bool(dir_value)
        _rtl_dir_value = bool(dir_value)

    if _rtl_pwr_pin is None:
        _rtl_pwr_pin = digitalio.DigitalInOut(board.RTL_PWR)
        _rtl_pwr_pin.direction = digitalio.Direction.OUTPUT

    if _rtl_spi is None:
        _rtl_spi = busio.SPI(board.RTL_CLK, board.RTL_MOSI, board.RTL_MISO)
        _rtl_cs = digitalio.DigitalInOut(board.RTL_CS)
        _rtl_ready = digitalio.DigitalInOut(board.RTL_READY)
        _rtl_ready.direction = digitalio.Direction.INPUT

    # 2. Reset or Init Interface
    if force_reset or _wifi_iface is None:
        # Power-cycle the RTL8720DN
        _rtl_pwr_pin.value = False
        time.sleep(0.5)
        _rtl_pwr_pin.value = True
        time.sleep(_POWERUP_WAIT_S)

        ready_trace = _wait_for_ready_window()
        _emit_event(
            "rtl_boot",
            dir_value=int(bool(_rtl_dir_value)) if _rtl_dir_value is not None else None,
            ready_trace=ready_trace,
        )

        _wifi_iface = _esp32spi.ESP_SPIcontrol(_rtl_spi, _rtl_cs, _rtl_ready, _rtl_pwr_pin)
        _http = adafruit_requests.Session(_esp32_socketpool.SocketPool(_wifi_iface))
        _wifi_backend = "rtl8720dn_spi"


def _connect_builtin_wifi():
    global _http, _wifi_backend
    if not _builtin_wifi.radio.connected:
        _builtin_wifi.radio.connect(_SSID, _WIFI_PASS)
    _http = adafruit_requests.Session(_builtin_socketpool.SocketPool(_builtin_wifi.radio))
    _wifi_backend = "wifi.radio"
    return str(_builtin_wifi.radio.ipv4_address)


def _probe_server():
    if _http is None:
        raise RuntimeError("HTTP session missing")
    r = None
    try:
        r = _http.get(_STATUS_URL, timeout=_HTTP_TIMEOUT)
        status = getattr(r, "status_code", 200)
        if status < 200 or status >= 300:
            raise RuntimeError("Server probe HTTP {}".format(status))
    finally:
        try:
            if r is not None:
                r.close()
        except Exception:
            pass


def _connect_rtl_wifi():
    global _http, _wifi_backend, _wifi_iface

    _wifi_backend = "rtl8720dn_spi"
    last_exc = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        for dir_value in _rtl_mode_candidates():
            force_reset = attempt > 1 or _wifi_iface is None or _rtl_dir_value != bool(dir_value)
            try:
                _init_rtl_wifi(force_reset=force_reset, dir_value=dir_value)

                if not _rtl_connected():
                    _emit_event(
                        "wifi_assoc",
                        backend="rtl8720dn_spi",
                        ssid=_SSID,
                        attempt=attempt,
                        dir_value=int(bool(dir_value)),
                        ready=_rtl_ready_value(),
                    )
                    _wifi_iface.connect_AP(_SSID, _WIFI_PASS)

                    deadline = time.monotonic() + _DHCP_WAIT_S
                    while time.monotonic() < deadline:
                        if _rtl_connected() and _rtl_ip_text():
                            break
                        time.sleep(0.25)

                ip = _rtl_ip_text()
                if not ip:
                    raise RuntimeError("Connected but no DHCP address")

                _http = adafruit_requests.Session(_esp32_socketpool.SocketPool(_wifi_iface))
                _wifi_backend = "rtl8720dn_spi"
                _probe_server()
                return ip
            except Exception as exc:
                last_exc = exc
                _emit_event(
                    "wifi_assoc_failed",
                    backend="rtl8720dn_spi",
                    attempt=attempt,
                    dir_value=int(bool(dir_value)),
                    ready=_rtl_ready_value(),
                    error=_short_error(exc),
                )
                _wifi_iface = None
                _http = None
                time.sleep(min(1.0 + attempt, 4.0))

    raise last_exc if last_exc is not None else RuntimeError("Unable to connect to WiFi")

def _wifi_connect():
    """Connect to WiFi and create an HTTP session. Safe to call multiple times."""
    global _wifi_ok, _http, _wifi_fail_n, _wifi_backend, _wifi_error

    if not _SSID:
        _wifi_backend = "disabled"
        _wifi_error = "WIFI_SSID missing"
        return

    if not _REQ_MOD:
        _wifi_backend = "disabled"
        _wifi_error = "adafruit_requests missing"
        return

    try:
        _set_status("Connecting to WiFi...", C_YELLOW)
        ip = None

        if _HAS_BUILTIN_WIFI:
            ip = _connect_builtin_wifi()
        elif _HAS_ESP32SPI_WIFI and _has_rtl_wifi_pins():
            _wifi_backend = "rtl8720dn_spi"
            ip = _connect_rtl_wifi()
        else:
            _wifi_backend = "unsupported"
            raise RuntimeError("No supported CircuitPython WiFi stack")

        _wifi_ok     = True
        _wifi_fail_n = 0
        _wifi_error  = ""
        _set_retry_timer(_WIFI_RETRY_S)
        _set_status("WiFi OK [{}] {}".format(_wifi_backend, ip), C_GREEN)
        _emit_event("wifi_connected", backend=_wifi_backend, ip=ip, api=_API_URL)
        time.sleep(0.5)
    except Exception as exc:
        _mark_wifi_down("connect_failed", hard_reset=True, exc=exc)
        _set_status("WiFi FAIL [{}]".format(_wifi_backend), C_RED)
        _emit_event("wifi_error", backend=_wifi_backend, error=_wifi_error, api=_API_URL)
        time.sleep(0.8)

_wifi_connect()    # attempt at startup

# ══════════════════════════════════════════════════════════════════════════════
#  Button C (leftmost top button) — force immediate read
# ══════════════════════════════════════════════════════════════════════════════

_btn = None
for _name in ("WIO_KEY_C", "BUTTON_3"):
    if hasattr(board, _name):
        try:
            _btn = digitalio.DigitalInOut(getattr(board, _name))
            _btn.direction = digitalio.Direction.INPUT
            _btn.pull      = digitalio.Pull.UP
        except Exception:
            _btn = None
        break

# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _color(val, warn, crit):
    if val >= crit: return C_RED
    if val >= warn: return C_YELLOW
    return C_GREEN

def _simulate(t):
    return (round(22.0 + 4.0 * math.sin(t * 0.05) + 0.5 * math.sin(t * 0.30), 2),
            round(55.0 + 10.0 * math.sin(t * 0.03), 2))

def _refresh(temp, hum, sim, count):
    lbl_t.text  = "{:5.1f}".format(temp)
    lbl_t.color = _color(temp, TEMP_WARN_C, TEMP_CRIT_C)
    lbl_h.text  = "{:5.1f}".format(hum)
    lbl_h.color = _color(hum, HUM_WARN_PCT, HUM_CRIT_PCT)
    tag   = "[SIM]" if sim else "[HW] "
    if not _SSID:
        w_tag = " W:CFG"
    elif _wifi_ok:
        w_tag = " W:OK"
    elif _wifi_backend == "unsupported":
        w_tag = " W:USB"
    else:
        w_tag = " W:NO"
    b_tag = " {}".format(_wifi_backend[:8]) if _wifi_backend not in ("disabled", "") else ""
    e_tag = "" if not _wifi_error else " !{}".format(_wifi_error[:10])
    _set_status("{} SHT40{}{}{} | N:{:d}".format(tag, w_tag, b_tag, e_tag, count),
                C_YELLOW if sim else C_GREEN)

def _send_serial(temp, hum, sim):
    """JSON to USB-CDC serial — silently ignored when no host is connected."""
    try:
        print(json.dumps({
            "node": NODE_ID, "temperature": temp,
            "humidity": hum, "source": "SHT40", "simulation": sim,
        }))
    except Exception:
        pass

def _send_http(temp, hum, sim):
    """POST reading to FastAPI server with rate limiting and reconnect handling."""
    global _wifi_ok, _http, _wifi_fail_n, _wifi_error, _last_push_at
    if not _wifi_ok or _http is None:
        return
    now = time.monotonic()
    if now - _last_push_at < _PUSH_INTERVAL:
        return
    if _wifi_backend == "rtl8720dn_spi" and not _rtl_connected():
        _mark_wifi_down("link_lost", hard_reset=True)
        return
    r = None
    try:
        r = _http.post(
            _API_URL,
            json={
                "node":        NODE_ID,
                "temperature": temp,
                "humidity":    hum,
                "source":      "SHT40" if not sim else "SHT40_sim",
                "simulation":  sim,
            },
            timeout=_HTTP_TIMEOUT,
        )
        status = getattr(r, "status_code", 200)
        if status < 200 or status >= 300:
            raise RuntimeError("HTTP {}".format(status))
        _wifi_fail_n = 0
        _wifi_error = ""
        _last_push_at = now
    except Exception as exc:
        _wifi_fail_n += 1
        _wifi_error = _short_error(exc)
        _emit_event("http_error", fail_count=_wifi_fail_n, error=_wifi_error, api=_API_URL)
        if _wifi_fail_n >= _RECONN_AFTER:
            _mark_wifi_down("post_failed", hard_reset=True, exc=exc)
    finally:
        try:
            if r is not None:
                r.close()
        except Exception:
            pass

# ── Startup marker on USB serial ─────────────────────────────────────────────
try:
    print(json.dumps({
        "event": "startup", "node": NODE_ID,
        "sensor": "SHT40", "simulation": sim_mode, "wifi": _wifi_ok,
        "wifi_backend": _wifi_backend, "api": _API_URL,
    }))
except Exception:
    pass

# ══════════════════════════════════════════════════════════════════════════════
#  Main loop — runs forever, completely standalone
# ══════════════════════════════════════════════════════════════════════════════

_last  = -READ_INTERVAL     # force immediate first read
_count = 0
_sim_t = 0.0

while True:
    now   = time.monotonic()
    force = (_btn is not None) and (not _btn.value)

    if force or (now - _last >= READ_INTERVAL):
        _last   = now           # reset interval timer before any blocking calls
        _sim_t += 0.1

        # ── Read sensor ───────────────────────────────────────────────────────
        if sensor_ok:
            try:
                temp, hum = sht.measurements
                temp, hum = round(temp, 2), round(hum, 2)
                sim_mode  = False
            except Exception:
                temp, hum = _simulate(_sim_t)
                sim_mode  = True
        else:
            temp, hum = _simulate(_sim_t)

        _count += 1

        # ── Update display first (always fast) ────────────────────────────────
        _refresh(temp, hum, sim_mode, _count)

        # ── Transmit (both channels are fire-and-forget) ──────────────────────
        _send_serial(temp, hum, sim_mode)
        _send_http(temp, hum, sim_mode)

        # ── WiFi reconnect with time-based backoff ─────────────────────────────
        if not _wifi_ok and _SSID and (now >= _next_wifi_retry_at):
            _wifi_connect()

        if force:
            time.sleep(0.15)    # button debounce
