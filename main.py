"""
main.py
FastAPI application — REST API + WebSocket real-time streaming.
Serves the compiled React dashboard from GUI/dist.
Telemetry: MQTT primary → SNMP fallback.
GPIO: Status LED, Alarm LED, Mode button, Fan tachometer, Valve feedback.
"""

from __future__ import annotations

import asyncio
import sys
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

# ── Windows: use SelectorEventLoop to avoid ProactorEventLoop WinError 10054 ─
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from control_logic import ControlMode, ThermalController
from IOControl.modbus_control import ModbusController
from IOControl.gpio_handler import GPIOHandler
from Networking.snmp_agent import SNMPAgent
from Networking.mqtt_client import MQTTClient
from sensor_reader import SensorReader
from Storage.data_logger import DataLogger

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Forward declarations (needed for MQTT command callbacks) ──────────────────
# Filled after controller is created below.
_controller_ref: Optional[ThermalController] = None

# ── MQTT command callbacks ────────────────────────────────────────────────────

def _mqtt_on_fan(speed: int):
    """Remote fan command received via MQTT."""
    if _controller_ref:
        # Switch to manual for remote command, apply, stay manual
        _controller_ref.set_mode("manual")
        _controller_ref.manual_set_fan(speed)
        logger.info("MQTT remote: fan → %d", speed)

def _mqtt_on_valve(valve_id: int, open_: bool):
    """Remote valve command received via MQTT."""
    if _controller_ref:
        _controller_ref.set_mode("manual")
        _controller_ref.manual_set_valve(valve_id, open_)
        logger.info("MQTT remote: valve %d → %s", valve_id, open_)

def _mqtt_on_mode(mode: str):
    """Remote mode switch received via MQTT."""
    if _controller_ref:
        _controller_ref.set_mode(mode)
        logger.info("MQTT remote: mode → %s", mode)

def _mqtt_on_threshold(payload: dict):
    """Remote threshold update received via MQTT."""
    if _controller_ref:
        for key in ("off", "low", "medium"):
            if key in payload:
                _controller_ref.thresholds[key] = float(payload[key])
        logger.info("MQTT remote: thresholds → %s", _controller_ref.thresholds)

# ── Singletons ────────────────────────────────────────────────────────────────

sensor     = SensorReader(
    config.SENSOR_TYPE,
    config.SENSOR_I2C_ADDRESS,
    config.GPIO_DHT22_DATA,
    serial_port    = getattr(config, "WIO_SERIAL_PORT",    "/dev/ttyACM0"),
    serial_baud    = getattr(config, "WIO_SERIAL_BAUD",    115200),
    serial_timeout = getattr(config, "WIO_SERIAL_TIMEOUT", 3.0),
)
modbus     = ModbusController(config.MODBUS_PORT, config.MODBUS_BAUDRATE, config.MODBUS_SLAVE_ID)
controller = ThermalController(modbus)
snmp       = SNMPAgent(config.SNMP_COMMUNITY, config.SNMP_MANAGER_HOST, config.SNMP_TRAP_PORT)
db         = DataLogger(config.DB_PATH)
mqtt       = MQTTClient(
    on_fan_cmd       = _mqtt_on_fan,
    on_valve_cmd     = _mqtt_on_valve,
    on_mode_cmd      = _mqtt_on_mode,
    on_threshold_cmd = _mqtt_on_threshold,
)

# Mode-button callback wired to GPIO handler
def _gpio_mode_toggle():
    """Called by GPIO interrupt when the mode button is pressed."""
    new_mode = "manual" if controller.mode == ControlMode.AUTO else "auto"
    controller.set_mode(new_mode)
    logger.info("GPIO button: mode toggled → %s", new_mode)

gpio = GPIOHandler(on_mode_toggle=_gpio_mode_toggle)

# Wire forward reference
_controller_ref = controller

# WebSocket client registry
_ws_clients: list[WebSocket] = []
_last_state: dict = {}
_last_log_ts: float = 0.0


# ── Broadcast helper ──────────────────────────────────────────────────────────

async def _broadcast(data: dict):
    dead = []
    payload = json.dumps(data, default=str)
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ── Main control loop ─────────────────────────────────────────────────────────

async def _control_loop():
    global _last_state, _last_log_ts
    while True:
        try:
            reading = sensor.read()
            airflow = modbus.read_airflow()
            controller.update(reading.temperature, reading.humidity, airflow)

            status  = modbus.get_status()
            alerts  = controller.get_alerts(reading.temperature, reading.humidity)

            # GPIO: drive alarm LED
            alarm_active = any(a["level"] == "critical" for a in alerts)
            gpio.set_alarm(alarm_active)

            # ── Telemetry: MQTT primary, SNMP fallback ────────────────────────
            state_payload = {
                "timestamp":      datetime.now().isoformat(timespec="seconds"),
                "temperature":    reading.temperature,
                "humidity":       reading.humidity,
                "fan_speed":      status["fan_speed"],
                "fan_speed_name": status["fan_speed_name"],
                "valve1_open":    status["valve1_open"],
                "valve2_open":    status["valve2_open"],
                "airflow_inlet":  airflow["airflow_inlet"],
                "airflow_outlet": airflow["airflow_outlet"],
                "control_mode":   str(controller.mode),
                "alerts":         alerts,
                "simulation":     status["simulation"],
                "source":         reading.source,
            }

            mqtt_ok = mqtt.publish(state_payload)

            # SNMP always updates its internal values; traps only when needed
            snmp.update(
                reading.temperature, reading.humidity,
                status["fan_speed"],
                status["valve1_open"], status["valve2_open"],
                airflow["airflow_inlet"], airflow["airflow_outlet"],
            )

            # Periodic DB log
            now = time.time()
            if now - _last_log_ts >= config.LOG_INTERVAL_S:
                await db.log_reading(
                    reading.temperature, reading.humidity,
                    status["fan_speed"],
                    status["valve1_open"], status["valve2_open"],
                    airflow["airflow_inlet"], airflow["airflow_outlet"],
                    str(controller.mode), reading.source,
                )
                _last_log_ts = now

            # GPIO feedback
            gpio_status = gpio.get_status()

            _last_state = {
                **state_payload,
                "fan_rpm":           gpio_status["fan_rpm"],
                "valve1_feedback":   gpio_status["valve1_feedback"],
                "valve2_feedback":   gpio_status["valve2_feedback"],
                "mqtt_connected":    mqtt.is_connected,
                "mqtt_fallback":     mqtt.using_snmp_fallback,
                "node_id":           config.NODE_ID,
                "node_name":         config.NODE_NAME,
            }

            await _broadcast(_last_state)

        except Exception as exc:
            logger.error("Control loop exception: %s", exc, exc_info=True)

        await asyncio.sleep(config.SENSOR_POLL_INTERVAL_S)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init()
    loop_task = asyncio.create_task(_control_loop())
    logger.info(
        "Datacenter Thermal Control started — http://%s:%d  node=%s",
        config.WEB_HOST, config.WEB_PORT, config.NODE_ID,
    )
    yield
    loop_task.cancel()
    mqtt.disconnect()
    modbus.disconnect()
    gpio.cleanup()
    logger.info("System stopped")


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Datacenter Thermal Control",
    description="Distributed embedded thermal management — Raspberry Pi 5",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class FanRequest(BaseModel):
    speed: int = Field(..., ge=0, le=3, description="0=OFF 1=LOW 2=MEDIUM 3=HIGH")

class ValveRequest(BaseModel):
    valve_id: int  = Field(..., ge=1, le=2)
    open:     bool

class ModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(auto|manual)$")

class ThresholdRequest(BaseModel):
    off:    Optional[float] = None
    low:    Optional[float] = None
    medium: Optional[float] = None

class SimulationRequest(BaseModel):
    enabled:     bool
    temperature: Optional[float] = Field(None, ge=-20, le=80)
    humidity:    Optional[float] = Field(None, ge=0,   le=100)

class WioReadingRequest(BaseModel):
    temperature: float           = Field(..., ge=-40, le=125, description="°C from SHT40")
    humidity:    float           = Field(..., ge=0,   le=100, description="% RH from SHT40")
    source:      str             = Field("SHT40",            description="Reading source label")
    simulation:  bool            = Field(False,              description="True if WIO is simulating")
    node:        Optional[str]   = None


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/status", summary="Current system state")
async def api_status():
    if not _last_state:
        reading = sensor.read()
        return {"temperature": reading.temperature, "humidity": reading.humidity}
    return _last_state

@app.post("/api/fan", summary="Set fan speed (manual mode only)")
async def api_set_fan(req: FanRequest):
    ok = controller.manual_set_fan(req.speed)
    if not ok:
        raise HTTPException(403, "Switch to MANUAL mode first")
    await db.log_event("FAN_CHANGE", f"Fan speed → {req.speed}", "info", float(req.speed))
    return {"success": True, "fan_speed": req.speed}

@app.post("/api/valve", summary="Set valve state (manual mode only)")
async def api_set_valve(req: ValveRequest):
    ok = controller.manual_set_valve(req.valve_id, req.open)
    if not ok:
        raise HTTPException(403, "Switch to MANUAL mode first")
    label = "OPEN" if req.open else "CLOSED"
    await db.log_event("VALVE_CHANGE", f"Valve {req.valve_id} → {label}", "info")
    return {"success": True, "valve_id": req.valve_id, "open": req.open}

@app.post("/api/mode", summary="Switch AUTO / MANUAL control mode")
async def api_set_mode(req: ModeRequest):
    controller.set_mode(req.mode)
    await db.log_event("MODE_CHANGE", f"Mode → {req.mode}", "info")
    return {"success": True, "mode": req.mode}

@app.get("/api/thresholds", summary="Get temperature thresholds")
async def api_get_thresholds():
    return controller.thresholds

@app.post("/api/thresholds", summary="Update temperature thresholds")
async def api_set_thresholds(req: ThresholdRequest):
    if req.off    is not None: controller.thresholds["off"]    = req.off
    if req.low    is not None: controller.thresholds["low"]    = req.low
    if req.medium is not None: controller.thresholds["medium"] = req.medium
    return {"success": True, "thresholds": controller.thresholds}

@app.get("/api/history", summary="Historical readings")
async def api_history(hours: int = 24, limit: int = 500):
    rows = await db.get_readings(hours, limit)
    return {"readings": rows, "count": len(rows)}

@app.get("/api/events", summary="Recent system events")
async def api_events(limit: int = 50):
    rows = await db.get_events(limit)
    return {"events": rows}

@app.get("/api/statistics", summary="24-hour statistics")
async def api_statistics():
    return await db.get_statistics()

@app.get("/api/snmp", summary="SNMP MIB info")
async def api_snmp_info():
    return snmp.get_mib_info()

@app.get("/api/mqtt", summary="MQTT broker connection status")
async def api_mqtt_status():
    return mqtt.get_status()

@app.get("/api/gpio", summary="GPIO pin assignments and live readings")
async def api_gpio_status():
    return gpio.get_status()

@app.get("/api/node", summary="Node identity")
async def api_node():
    return {
        "node_id":         config.NODE_ID,
        "node_name":       config.NODE_NAME,
        "mqtt_topic_base": config.MQTT_TOPIC_BASE,
    }

@app.get("/api/simulation", summary="Get simulation override state")
async def api_get_simulation():
    return sensor.get_simulation_state()

@app.post("/api/simulation", summary="Enable/disable sensor simulation override")
async def api_set_simulation(req: SimulationRequest):
    if req.enabled:
        if req.temperature is None or req.humidity is None:
            raise HTTPException(400, "temperature and humidity required when enabling simulation")
        sensor.set_override(req.temperature, req.humidity)
        await db.log_event("SIMULATION", f"Override enabled: {req.temperature}°C / {req.humidity}%", "info")
    else:
        sensor.clear_override()
        await db.log_event("SIMULATION", "Override disabled — live sensor", "info")
    return sensor.get_simulation_state()


# ── WIO Terminal WiFi push ────────────────────────────────────────────────────

@app.post("/api/wio_reading", summary="Receive live SHT40 reading pushed from WIO Terminal via WiFi")
async def api_wio_reading(req: WioReadingRequest):
    """
    The WIO Terminal calls this every 0.5 s over WiFi.
    The reading immediately becomes the active sensor value used by the
    control loop (priority: override > WIO WiFi push > local sensor > simulation).
    """
    src = req.source if not req.simulation else f"{req.source}_sim"
    sensor.push_external(req.temperature, req.humidity, src)
    return {
        "success": True,
        "received": {
            "temperature": req.temperature,
            "humidity":    req.humidity,
            "source":      src,
            "node":        req.node,
        },
    }

@app.get("/api/wio", summary="WIO Terminal WiFi connection status and last reading")
async def api_wio_status():
    return sensor.get_wio_status()


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    if _last_state:
        await websocket.send_text(json.dumps(_last_state, default=str))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ── Static files (React build) ────────────────────────────────────────────────

_dist = os.path.join(os.path.dirname(__file__), "GUI", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="ui")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return JSONResponse({"message": "API running. Build the React UI: cd GUI && npm run build"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        reload=False,
        ws="wsproto",   # websockets 14+ broke uvicorn's impl; wsproto is stable
    )

