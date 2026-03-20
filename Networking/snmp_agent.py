"""
Networking/snmp_agent.py
SNMP v2c agent + trap sender for temperature, humidity, and actuator states.
Uses pysnmp ≥ 6.x (asyncio-native hlapi).

OID layout under enterprise 1.3.6.1.4.1.54321:
  .1.1.0  temperature   (Integer, unit = 0.1 °C)
  .1.2.0  humidity      (Integer, unit = 0.1 %)
  .2.1.0  fan_speed     (Integer, 0–3)
  .2.2.0  valve_recirc  (Integer, 0/1)
  .2.3.0  valve_exhaust (Integer, 0/1)
  .3.1.0  airflow_in    (Integer, 0/1)
  .3.2.0  airflow_out   (Integer, 0/1)
  .4.1    trap: high temperature
  .4.2    trap: high humidity
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class SNMPAgent:
    """Maintains current MIB values and sends traps on threshold crossings."""

    MIB_VARS: dict[str, tuple[str, str]] = {
        # oid_suffix: (label, description)
        "1.1.0": ("temperature",    "Temperature ×10 (°C)"),
        "1.2.0": ("humidity",       "Humidity ×10 (%)"),
        "2.1.0": ("fan_speed",      "Fan speed 0–3"),
        "2.2.0": ("valve_recirc",   "Valve recirculation 0/1"),
        "2.3.0": ("valve_exhaust",  "Valve exhaust 0/1"),
        "3.1.0": ("airflow_in",     "Inlet airflow DI"),
        "3.2.0": ("airflow_out",    "Outlet airflow DI"),
    }

    def __init__(
        self,
        community: str = "public",
        manager_host: str = "127.0.0.1",
        trap_port: int = 162,
    ):
        self.community    = community
        self.manager_host = manager_host
        self.trap_port    = trap_port
        self._sim         = False

        # Current values
        self._temperature: float = 0.0
        self._humidity:    float = 0.0
        self._fan_speed:   int   = 0
        self._valve1:      int   = 0
        self._valve2:      int   = 0
        self._airflow_in:  int   = 0
        self._airflow_out: int   = 0

        # Trap edge-detection flags
        self._trap_temp_sent = False
        self._trap_hum_sent  = False

        self._check_pysnmp()

    def _check_pysnmp(self):
        try:
            import pysnmp  # noqa: F401
        except ImportError:
            logger.warning("pysnmp not installed — SNMP running in log-only mode.")
            self._sim = True

    # ── Value update (called every control cycle) ─────────────────────────────

    def update(
        self,
        temperature: float,
        humidity: float,
        fan_speed: int,
        valve1: bool,
        valve2: bool,
        airflow_in: bool,
        airflow_out: bool,
    ):
        prev_temp = self._temperature
        prev_hum  = self._humidity

        self._temperature = temperature
        self._humidity    = humidity
        self._fan_speed   = fan_speed
        self._valve1      = int(valve1)
        self._valve2      = int(valve2)
        self._airflow_in  = int(airflow_in)
        self._airflow_out = int(airflow_out)

        # Rising-edge trap: temperature crosses HIGH threshold
        if prev_temp < config.TEMP_THRESH_MED <= temperature and not self._trap_temp_sent:
            asyncio.create_task(self._send_trap(
                config.OID_TRAP_TEMP_HIGH,
                int(temperature * 10),
                f"High temperature: {temperature} °C",
            ))
            self._trap_temp_sent = True
        elif temperature < config.TEMP_THRESH_MED:
            self._trap_temp_sent = False

        # Rising-edge trap: humidity crosses HIGH threshold
        if prev_hum < config.HUMIDITY_HIGH_WARN <= humidity and not self._trap_hum_sent:
            asyncio.create_task(self._send_trap(
                config.OID_TRAP_HUM_HIGH,
                int(humidity * 10),
                f"High humidity: {humidity} %",
            ))
            self._trap_hum_sent = True
        elif humidity < config.HUMIDITY_HIGH_WARN:
            self._trap_hum_sent = False

    # ── SNMP GET response helper ──────────────────────────────────────────────

    def get_value(self, oid_suffix: str) -> Optional[int]:
        mapping = {
            "1.1.0": int(self._temperature * 10),
            "1.2.0": int(self._humidity * 10),
            "2.1.0": self._fan_speed,
            "2.2.0": self._valve1,
            "2.3.0": self._valve2,
            "3.1.0": self._airflow_in,
            "3.2.0": self._airflow_out,
        }
        return mapping.get(oid_suffix)

    # ── Trap sending ──────────────────────────────────────────────────────────

    async def _send_trap(self, trap_oid: str, value: int, description: str):
        if self._sim:
            logger.info("[SIM SNMP TRAP] %s = %d  (%s)", trap_oid, value, description)
            return
        try:
            from pysnmp.hlapi.asyncio import (
                CommunityData, ContextData, Integer32, NotificationType,
                ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget,
                sendNotification,
            )

            error_indication, error_status, error_index, _ = await sendNotification(
                SnmpEngine(),
                CommunityData(self.community, mpModel=1),
                await UdpTransportTarget.create((self.manager_host, self.trap_port)),
                ContextData(),
                "trap",
                NotificationType(ObjectIdentity(trap_oid)).addVarBinds(
                    ObjectType(ObjectIdentity(trap_oid), Integer32(value))
                ),
            )
            if error_indication:
                logger.error("SNMP trap error: %s", error_indication)
            else:
                logger.info("SNMP trap sent: %s", description)
        except Exception as exc:
            logger.error("Failed to send SNMP trap: %s", exc)

    # ── MIB info (for API endpoint) ───────────────────────────────────────────

    def get_mib_info(self) -> dict:
        base = config.SNMP_ENTERPRISE_OID
        return {
            "enterprise_oid": base,
            "community":      self.community,
            "manager":        f"{self.manager_host}:{self.trap_port}",
            "oids": [
                {
                    "oid":         f"{base}.{suffix}",
                    "label":       label,
                    "description": desc,
                    "current":     self.get_value(suffix),
                }
                for suffix, (label, desc) in self.MIB_VARS.items()
            ],
        }

