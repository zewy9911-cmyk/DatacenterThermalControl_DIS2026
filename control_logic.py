"""
control_logic.py
Automatic thermal control logic for the datacenter.

Temperature bands  →  Fan speed  →  Valve posture
──────────────────────────────────────────────────
  T < 20 °C           OFF           Recirculation ON  / Exhaust OFF
  20 ≤ T < 25 °C      LOW           Recirculation ON  / Exhaust OFF
  25 ≤ T < 30 °C      MEDIUM        Recirculation OFF / Exhaust ON
  T ≥ 30 °C           HIGH          Recirculation OFF / Exhaust ON

Airflow-fault override:
  If fan is running in exhaust mode but outlet DI is LOW  →  switch to
  recirculation (possible blocked exhaust duct).
"""

from __future__ import annotations

import logging
from enum import StrEnum

import config
from IOControl.modbus_control import FanSpeed, ModbusController, ValveState

logger = logging.getLogger(__name__)


class ControlMode(StrEnum):
    AUTO   = "auto"
    MANUAL = "manual"


class ThermalController:
    """Evaluates sensor data and issues Modbus commands."""

    def __init__(self, modbus: ModbusController):
        self.modbus = modbus
        self.mode   = ControlMode.AUTO

        # Thresholds (mutable via API)
        self.thresholds = {
            "off":    config.TEMP_THRESH_OFF,
            "low":    config.TEMP_THRESH_LOW,
            "medium": config.TEMP_THRESH_MED,
        }

    # ── Mode ─────────────────────────────────────────────────────────────────

    def set_mode(self, mode: str):
        self.mode = ControlMode(mode)
        logger.info("Control mode → %s", self.mode)

    # ── Main update (called every poll cycle) ─────────────────────────────────

    def update(self, temperature: float, humidity: float, airflow: dict):
        if self.mode != ControlMode.AUTO:
            return
        self._auto_control(temperature, humidity, airflow)

    def _auto_control(self, temperature: float, humidity: float, airflow: dict):
        t = self.thresholds

        # Determine target fan speed
        if temperature < t["off"]:
            target_fan = FanSpeed.OFF
        elif temperature < t["low"]:
            target_fan = FanSpeed.LOW
        elif temperature < t["medium"]:
            target_fan = FanSpeed.MEDIUM
        else:
            target_fan = FanSpeed.HIGH

        # Valve logic: exhaust mode for MEDIUM and HIGH
        use_exhaust = target_fan >= FanSpeed.MEDIUM

        # Airflow-fault override: fan running, exhaust mode, but no outlet flow
        airflow_out = airflow.get("airflow_outlet", False)
        airflow_in  = airflow.get("airflow_inlet",  False)
        fault_exhaust = use_exhaust and target_fan != FanSpeed.OFF and not airflow_out and airflow_in
        if fault_exhaust:
            logger.warning("Exhaust airflow not detected → switching to recirculation")
            use_exhaust = False

        recirc_open  = not use_exhaust
        exhaust_open = use_exhaust

        # Apply only what changed
        status = self.modbus.get_status()
        if status["fan_speed"] != int(target_fan):
            self.modbus.set_fan_speed(int(target_fan))
        if status["valve1_open"] != recirc_open:
            self.modbus.set_valve_recirc(recirc_open)
        if status["valve2_open"] != exhaust_open:
            self.modbus.set_valve_exhaust(exhaust_open)

    # ── Manual overrides ──────────────────────────────────────────────────────

    def manual_set_fan(self, speed: int) -> bool:
        if self.mode != ControlMode.MANUAL:
            logger.warning("Rejected manual fan command (not in MANUAL mode)")
            return False
        return self.modbus.set_fan_speed(speed)

    def manual_set_valve(self, valve_id: int, open_: bool) -> bool:
        if self.mode != ControlMode.MANUAL:
            logger.warning("Rejected manual valve command (not in MANUAL mode)")
            return False
        if valve_id == 1:
            return self.modbus.set_valve_recirc(open_)
        if valve_id == 2:
            return self.modbus.set_valve_exhaust(open_)
        return False

    # ── Alerts / recommendations ──────────────────────────────────────────────

    def get_alerts(self, temperature: float, humidity: float) -> list[dict]:
        alerts = []
        if temperature >= config.TEMP_THRESH_MED:
            alerts.append({
                "level":   "critical",
                "message": f"Критична температура: {temperature} °C",
            })
        elif temperature >= config.TEMP_THRESH_LOW:
            alerts.append({
                "level":   "warning",
                "message": f"Повишена температура: {temperature} °C",
            })

        if humidity >= config.HUMIDITY_HIGH_WARN:
            alerts.append({
                "level":   "warning",
                "message": f"Висока влажност: {humidity} %",
            })
        elif humidity <= config.HUMIDITY_LOW_WARN:
            alerts.append({
                "level":   "info",
                "message": f"Ниска влажност: {humidity} %",
            })
        return alerts

