"""
sensor_reader.py
Reads temperature and humidity from:
  • BME280  — I²C (smbus2 + bme280)
  • DHT22   — GPIO (adafruit_dht)
  • SHT40_USB — Seeed WIO Terminal over USB-Serial (pyserial)
               The WIO Terminal sketch streams JSON lines:
               {"node":"…","temperature":23.4,"humidity":55.3,"source":"SHT40","simulation":false}

Falls back to a deterministic simulation when hardware is unavailable.
"""

import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SensorData:
    temperature: float
    humidity: float
    timestamp: float = field(default_factory=time.time)
    source: str = "sensor"      # "sensor" | "simulation" | "cached"


class SensorReader:
    """Unified reader for BME280 (I²C), DHT22 (GPIO) and SHT40_USB (WIO Terminal)."""

    def __init__(
        self,
        sensor_type: str = "BME280",
        i2c_address: int = 0x76,
        gpio_pin: int = 4,
        serial_port: str = "/dev/ttyACM0",
        serial_baud: int = 115200,
        serial_timeout: float = 3.0,
    ):
        self.sensor_type    = sensor_type.upper()
        self.i2c_address    = i2c_address
        self.gpio_pin       = gpio_pin
        self.serial_port    = serial_port
        self.serial_baud    = serial_baud
        self.serial_timeout = serial_timeout

        self._sensor = None
        self._bus    = None
        self._serial = None
        self._calibration = None
        self._simulation = False
        self._last: Optional[SensorData] = None

        # External push (WIO Terminal WiFi → /api/wio_reading)
        self._external: Optional[SensorData] = None
        self._external_ts: float = 0.0
        self._EXTERNAL_MAX_AGE = 10.0   # fall back to local sensor after 10 s silence

        # Simulation override (set via API)
        self._override_active = False
        self._override_temp: float = 22.0
        self._override_hum: float  = 55.0

        # Simulation state
        self._sim_base_temp = 22.0
        self._sim_t = 0.0

        self._init()

    # ── Initialisation ──────────────────────────────────────────────────────

    def _init(self):
        try:
            if self.sensor_type == "BME280":
                self._init_bme280()
            elif self.sensor_type == "DHT22":
                self._init_dht22()
            elif self.sensor_type == "SHT40_USB":
                self._init_sht40_usb()
            else:
                raise ValueError(f"Unknown sensor type: {self.sensor_type}")
        except Exception as exc:
            logger.warning("Sensor init failed (%s). Simulation mode active.", exc)
            self._simulation = True

    def _init_bme280(self):
        import smbus2
        import bme280

        self._bus = smbus2.SMBus(1)
        self._calibration = bme280.load_calibration_params(self._bus, self.i2c_address)
        logger.info("BME280 initialised at I²C 0x%02X", self.i2c_address)

    def _init_dht22(self):
        import adafruit_dht
        import board

        _pin_map = {
            4: board.D4, 17: board.D17, 18: board.D18,
            22: board.D22, 23: board.D23, 24: board.D24,
        }
        pin = _pin_map.get(self.gpio_pin)
        if pin is None:
            raise ValueError(f"GPIO pin {self.gpio_pin} not in pin_map")
        self._sensor = adafruit_dht.DHT22(pin)
        logger.info("DHT22 initialised on GPIO %d", self.gpio_pin)

    def _init_sht40_usb(self):
        """Open USB-Serial port to the WIO Terminal running WIOTerminal.ino."""
        import serial  # pyserial

        self._serial = serial.Serial(
            port=self.serial_port,
            baudrate=self.serial_baud,
            timeout=self.serial_timeout,
        )
        # Flush stale bytes (WIO Terminal may already be streaming)
        self._serial.reset_input_buffer()
        logger.info(
            "SHT40_USB initialised on %s @ %d baud",
            self.serial_port, self.serial_baud,
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def read(self) -> SensorData:
        """Return the latest SensorData (never raises).

        Priority order:
          1. Simulation override  (set via /api/simulation)
          2. External WiFi push   (WIO Terminal → /api/wio_reading, max 10 s stale)
          3. Local hardware read  (BME280 / DHT22 / SHT40_USB)
          4. Simulation fallback
        """
        if self._override_active:
            return SensorData(
                round(self._override_temp, 2),
                round(self._override_hum,  2),
                source="simulation_override",
            )

        # WiFi-pushed reading from WIO Terminal (fresher than 10 s)
        if self._external is not None:
            age = time.time() - self._external_ts
            if age < self._EXTERNAL_MAX_AGE:
                return self._external

        if self._simulation:
            return self._simulate()
        try:
            if self.sensor_type == "BME280":
                return self._read_bme280()
            if self.sensor_type == "SHT40_USB":
                return self._read_sht40_usb()
            return self._read_dht22()
        except Exception as exc:
            logger.error("Sensor read error: %s", exc)
            if self._last:
                return SensorData(self._last.temperature, self._last.humidity, source="cached")
            return self._simulate()

    # ── Simulation override API ───────────────────────────────────────────────

    def set_override(self, temperature: float, humidity: float):
        """Force fixed sensor values (used by the simulation API endpoint)."""
        self._override_active = True
        self._override_temp   = float(temperature)
        self._override_hum    = float(humidity)
        logger.info("Sensor override: %.1f °C / %.1f %%", temperature, humidity)

    def clear_override(self):
        """Remove the forced values; resume live/simulated readings."""
        self._override_active = False
        logger.info("Sensor override cleared")

    # ── WIO Terminal WiFi push API ────────────────────────────────────────────

    def push_external(self, temperature: float, humidity: float,
                      source: str = "SHT40_wifi") -> None:
        """Store a reading pushed from the WIO Terminal via WiFi HTTP POST.

        Takes priority over local sensor/simulation for up to
        _EXTERNAL_MAX_AGE seconds after the last push.
        """
        self._external    = SensorData(
            round(float(temperature), 2),
            round(float(humidity),    2),
            source=source,
        )
        self._external_ts = time.time()
        self._last        = self._external
        logger.debug("External push: %.2f °C / %.2f %%  src=%s", temperature, humidity, source)

    def get_wio_status(self) -> dict:
        """Return the age and values of the last WIO Terminal WiFi push."""
        if self._external is None:
            return {"connected": False, "age_s": None, "temperature": None, "humidity": None}
        age = round(time.time() - self._external_ts, 1)
        return {
            "connected":   age < self._EXTERNAL_MAX_AGE,
            "age_s":       age,
            "temperature": self._external.temperature,
            "humidity":    self._external.humidity,
            "source":      self._external.source,
        }

    def get_simulation_state(self) -> dict:
        return {
            "enabled":     self._override_active,
            "temperature": self._override_temp if self._override_active else None,
            "humidity":    self._override_hum  if self._override_active else None,
            "hw_sim":      self._simulation,
        }

    # ── Hardware reads ───────────────────────────────────────────────────────

    def _read_bme280(self) -> SensorData:
        import bme280

        data = bme280.sample(self._bus, self.i2c_address, self._calibration)
        result = SensorData(round(data.temperature, 2), round(data.humidity, 2))
        self._last = result
        return result

    def _read_dht22(self) -> SensorData:
        result = SensorData(
            round(self._sensor.temperature, 2),
            round(self._sensor.humidity, 2),
        )
        self._last = result
        return result

    def _read_sht40_usb(self) -> SensorData:
        """
        Read one JSON line from the WIO Terminal USB-Serial.
        Expected format:
            {"node":"…","temperature":23.45,"humidity":55.30,"source":"SHT40","simulation":false}
        Non-data lines (e.g. startup events) are silently skipped.
        """
        # Drain up to 5 lines looking for a data frame
        for _ in range(5):
            raw = self._serial.readline()
            if not raw:
                raise TimeoutError("No data from WIO Terminal (timeout)")
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace").strip())
            except json.JSONDecodeError:
                continue  # malformed line, try next
            if "temperature" not in obj or "humidity" not in obj:
                continue  # startup / event line, skip
            source = "SHT40_sim" if obj.get("simulation", False) else "SHT40"
            result = SensorData(
                round(float(obj["temperature"]), 2),
                round(float(obj["humidity"]), 2),
                source=source,
            )
            self._last = result
            return result
        raise RuntimeError("No valid SHT40 JSON frame received in 5 attempts")

    # ── Simulation ───────────────────────────────────────────────────────────

    def _simulate(self) -> SensorData:
        """Produce a slowly drifting realistic temperature/humidity curve."""
        self._sim_t += 0.05
        temp = self._sim_base_temp + 4.0 * math.sin(self._sim_t * 0.3) + \
               0.5 * math.sin(self._sim_t * 1.7)
        hum = 55.0 + 10.0 * math.sin(self._sim_t * 0.2)
        result = SensorData(round(temp, 2), round(hum, 2), source="simulation")
        self._last = result
        return result

