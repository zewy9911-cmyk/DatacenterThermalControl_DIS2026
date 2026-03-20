"""
IOControl/modbus_control.py
Modbus RTU controller for fan (3 speeds) + 2 damper valves + airflow DI sensors.
Uses pymodbus ≥ 3.6 API.
Falls back to simulation when no serial adapter is present.
"""

from __future__ import annotations

import logging
from enum import IntEnum
from typing import List, Optional

logger = logging.getLogger(__name__)


# ── Enumerations ─────────────────────────────────────────────────────────────

class FanSpeed(IntEnum):
    OFF    = 0
    LOW    = 1   # 1st gear  ~33 %
    MEDIUM = 2   # 2nd gear  ~66 %
    HIGH   = 3   # 3rd gear  100 %


class ValveState(IntEnum):
    CLOSED = 0
    OPEN   = 1


# ── Controller ───────────────────────────────────────────────────────────────

class ModbusController:
    """
    Coil map (one-based Relay numbering in comments):
        Coil 0 — Relay 1 — Fan LOW
        Coil 1 — Relay 2 — Fan MEDIUM
        Coil 2 — Relay 3 — Fan HIGH
        Coil 3 — Relay 4 — Valve 1 (Recirculation)
        Coil 4 — Relay 5 — Valve 2 (Exhaust / outdoor)

    Discrete Input map:
        DI 0 — Airflow inlet sensor
        DI 1 — Airflow outlet sensor
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        slave_id: int = 1,
        timeout: float = 1.0,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
    ):
        self.port     = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.timeout  = timeout
        self.parity   = parity
        self.stopbits = stopbits
        self.bytesize = bytesize

        self._client    = None
        self._sim       = False

        # Cached state
        self._fan_speed   = FanSpeed.OFF
        self._valve1      = ValveState.CLOSED
        self._valve2      = ValveState.CLOSED
        self._airflow_in  = False
        self._airflow_out = False

        self._connect()

    # ── Connection ────────────────────────────────────────────────────────────

    def _connect(self):
        try:
            from pymodbus.client import ModbusSerialClient

            self._client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
            )
            if self._client.connect():
                logger.info("Modbus connected on %s", self.port)
            else:
                raise OSError("connect() returned False")
        except Exception as exc:
            logger.warning("Modbus unavailable (%s). Simulation active.", exc)
            self._sim = True

    def disconnect(self):
        if self._client and not self._sim:
            self._client.close()
            logger.info("Modbus disconnected")

    # ── Low-level helpers ────────────────────────────────────────────────────

    def _write_coil(self, address: int, value: bool) -> bool:
        if self._sim:
            logger.debug("[SIM] coil[%d] = %s", address, value)
            return True
        try:
            res = self._client.write_coil(address, value, slave=self.slave_id)
            return not res.isError()
        except Exception as exc:
            logger.error("write_coil(%d) failed: %s", address, exc)
            return False

    def _write_coils(self, address: int, values: List[bool]) -> bool:
        if self._sim:
            logger.debug("[SIM] coils[%d..%d] = %s", address, address + len(values) - 1, values)
            return True
        try:
            res = self._client.write_coils(address, values, slave=self.slave_id)
            return not res.isError()
        except Exception as exc:
            logger.error("write_coils(%d) failed: %s", address, exc)
            return False

    def _read_discrete_inputs(self, address: int, count: int = 2) -> Optional[List[bool]]:
        if self._sim:
            # Simulate based on fan running
            running = self._fan_speed != FanSpeed.OFF
            return [running, running and self._valve2 == ValveState.OPEN]
        try:
            res = self._client.read_discrete_inputs(address, count, slave=self.slave_id)
            if not res.isError():
                return list(res.bits[:count])
            return None
        except Exception as exc:
            logger.error("read_discrete_inputs(%d) failed: %s", address, exc)
            return None

    # ── Fan control ───────────────────────────────────────────────────────────

    def set_fan_speed(self, speed: int) -> bool:
        """
        Set fan to one of 4 states.
        Only one coil (0, 1, 2) is HIGH at a time; all three are LOW for OFF.
        """
        speed = FanSpeed(speed)
        coils = [
            speed == FanSpeed.LOW,
            speed == FanSpeed.MEDIUM,
            speed == FanSpeed.HIGH,
        ]
        success = self._write_coils(0, coils)
        if success:
            self._fan_speed = speed
            logger.info("Fan → %s", speed.name)
        return success

    # ── Valve control ─────────────────────────────────────────────────────────

    def set_valve_recirc(self, open_: bool) -> bool:
        """Valve 1 — Recirculation (air stays inside the room)."""
        success = self._write_coil(3, open_)
        if success:
            self._valve1 = ValveState.OPEN if open_ else ValveState.CLOSED
            logger.info("Valve-1 (recirc) → %s", "OPEN" if open_ else "CLOSED")
        return success

    def set_valve_exhaust(self, open_: bool) -> bool:
        """Valve 2 — Exhaust (air directed outside)."""
        success = self._write_coil(4, open_)
        if success:
            self._valve2 = ValveState.OPEN if open_ else ValveState.CLOSED
            logger.info("Valve-2 (exhaust) → %s", "OPEN" if open_ else "CLOSED")
        return success

    # ── Airflow sensors ───────────────────────────────────────────────────────

    def read_airflow(self) -> dict:
        """Read both airflow DI sensors."""
        values = self._read_discrete_inputs(0, 2)
        if values:
            self._airflow_in  = values[0]
            self._airflow_out = values[1]
        return {
            "airflow_inlet":  self._airflow_in,
            "airflow_outlet": self._airflow_out,
        }

    # ── Status snapshot ───────────────────────────────────────────────────────

    def get_status(self) -> dict:
        return {
            "fan_speed":      int(self._fan_speed),
            "fan_speed_name": self._fan_speed.name,
            "valve1_open":    self._valve1 == ValveState.OPEN,
            "valve2_open":    self._valve2 == ValveState.OPEN,
            "airflow_inlet":  self._airflow_in,
            "airflow_outlet": self._airflow_out,
            "simulation":     self._sim,
        }

