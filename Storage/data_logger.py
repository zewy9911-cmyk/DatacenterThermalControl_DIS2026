"""
Storage/data_logger.py
Async SQLite logger for sensor readings and system events (aiosqlite).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_READINGS = """
CREATE TABLE IF NOT EXISTS readings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    temperature   REAL    NOT NULL,
    humidity      REAL    NOT NULL,
    fan_speed     INTEGER NOT NULL DEFAULT 0,
    valve_recirc  INTEGER NOT NULL DEFAULT 0,
    valve_exhaust INTEGER NOT NULL DEFAULT 0,
    airflow_in    INTEGER NOT NULL DEFAULT 0,
    airflow_out   INTEGER NOT NULL DEFAULT 0,
    control_mode  TEXT    NOT NULL DEFAULT 'auto',
    source        TEXT    NOT NULL DEFAULT 'sensor'
)
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now')),
    event_type TEXT NOT NULL,
    severity   TEXT NOT NULL DEFAULT 'info',
    message    TEXT NOT NULL,
    value      REAL
)
"""

_CREATE_IDX_R = "CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(timestamp)"
_CREATE_IDX_E = "CREATE INDEX IF NOT EXISTS idx_events_ts  ON events(timestamp)"


class DataLogger:
    """Async SQLite data logger."""

    def __init__(self, db_path: str = "Storage/data.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    # ── Initialisation ───────────────────────────────────────────────────────

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(_CREATE_READINGS)
            await db.execute(_CREATE_EVENTS)
            await db.execute(_CREATE_IDX_R)
            await db.execute(_CREATE_IDX_E)
            await db.commit()
        logger.info("Database ready: %s", self.db_path)

    # ── Write helpers ────────────────────────────────────────────────────────

    async def log_reading(
        self,
        temperature: float,
        humidity: float,
        fan_speed: int,
        valve_recirc: bool,
        valve_exhaust: bool,
        airflow_in: bool,
        airflow_out: bool,
        control_mode: str = "auto",
        source: str = "sensor",
    ):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT INTO readings
                       (temperature, humidity, fan_speed, valve_recirc, valve_exhaust,
                        airflow_in, airflow_out, control_mode, source)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (temperature, humidity, fan_speed,
                     int(valve_recirc), int(valve_exhaust),
                     int(airflow_in), int(airflow_out),
                     control_mode, source),
                )
                await db.commit()
        except Exception as exc:
            logger.error("log_reading failed: %s", exc)

    async def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = "info",
        value: float | None = None,
    ):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO events (event_type, severity, message, value) VALUES (?,?,?,?)",
                    (event_type, severity, message, value),
                )
                await db.commit()
        except Exception as exc:
            logger.error("log_event failed: %s", exc)

    # ── Query helpers ────────────────────────────────────────────────────────

    async def get_readings(self, hours: int = 24, limit: int = 500) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """SELECT * FROM readings
                       WHERE timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
                       ORDER BY timestamp ASC LIMIT ?""",
                    (f"-{hours} hours", limit),
                )
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("get_readings failed: %s", exc)
            return []

    async def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)
                )
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("get_events failed: %s", exc)
            return []

    async def get_statistics(self) -> dict[str, Any]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """SELECT
                           ROUND(AVG(temperature), 2), ROUND(MIN(temperature), 2), ROUND(MAX(temperature), 2),
                           ROUND(AVG(humidity),    2), ROUND(MIN(humidity),    2), ROUND(MAX(humidity),    2),
                           COUNT(*)
                       FROM readings
                       WHERE timestamp >= strftime('%Y-%m-%dT%H:%M:%S', 'now', '-24 hours')"""
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "avg_temp":   row[0] or 0,
                        "min_temp":   row[1] or 0,
                        "max_temp":   row[2] or 0,
                        "avg_hum":    row[3] or 0,
                        "min_hum":    row[4] or 0,
                        "max_hum":    row[5] or 0,
                        "total_rows": row[6] or 0,
                    }
        except Exception as exc:
            logger.error("get_statistics failed: %s", exc)
        return {}

