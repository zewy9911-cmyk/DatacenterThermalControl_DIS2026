# Разпределена вградена система за термично управление на ЦД
### Distributed Embedded System for Datacenter Thermal Control
**Platform:** Raspberry Pi 5 | **Version:** 1.0.0 | **Date:** March 2026

---

## Quick Start

```bash
# 1. Install (on Raspberry Pi)
bash install.sh

# 2. Manual start
source venv/bin/activate
python main.py

# 3. Open in browser
http://<RPi-IP>:8000
```

## Project Structure

```
DatacenterThermalControl/
├── main.py                     # FastAPI server — REST + WebSocket
├── config.py                   # All configuration constants
├── sensor_reader.py            # BME280 / DHT22 sensor reader
├── control_logic.py            # Automatic thermal control logic
├── requirements.txt            # Python dependencies
├── install.sh                  # Raspberry Pi setup script
├── datacenter_thermal.service  # systemd service
│
├── IOControl/
│   └── modbus_control.py       # Modbus RTU — fan (3 speeds) + 2 valves + DI
│
├── Networking/
│   └── snmp_agent.py           # SNMP v2c agent + trap sender
│
├── Storage/
│   └── data_logger.py          # Async SQLite logger (aiosqlite)
│
├── GUI/                        # React + Vite dashboard
│   ├── src/
│   │   ├── App.jsx             # Root layout
│   │   ├── hooks/useWebSocket.js
│   │   ├── api/client.js
│   │   └── components/
│   │       ├── SensorGauges.jsx
│   │       ├── FanControl.jsx
│   │       ├── ValveControl.jsx
│   │       ├── AirflowStatus.jsx
│   │       ├── ModeToggle.jsx
│   │       ├── AlertsPanel.jsx
│   │       └── HistoricalChart.jsx
│   └── dist/                   # Production build (after npm run build)
│
└── docs/
    ├── documentation_bg.md     # Full documentation in Bulgarian
    ├── process_datagram.md     # Mermaid process flowcharts
    └── presentation.html       # Standalone 8-slide HTML presentation
```

## Features

| Module | Feature |
|--------|---------|
| **Sensor** | BME280 (I²C) or DHT22 (GPIO) — temperature + humidity |
| **Modbus RTU** | Fan 3-speed control via relay coils 0–2 |
| **Modbus RTU** | Valve 1 (Recirculation) — coil 3 |
| **Modbus RTU** | Valve 2 (Exhaust/outdoor) — coil 4 |
| **Modbus DI** | Airflow detection sensors — DI 0, DI 1 |
| **SNMP v2c** | Reports temp, humidity, fan, valves via OID 1.3.6.1.4.1.54321.x |
| **SNMP Traps** | Auto-sent on T≥30°C or RH≥70% |
| **SQLite** | Every-60s logging, 24h history, statistics |
| **WebSocket** | Real-time state broadcast every 5 seconds |
| **React UI** | Radial gauges, fan selector, valve toggles, history chart |
| **Auto Control** | T<20:OFF | 20-25:LOW | 25-30:MED | ≥30:HIGH + valve logic |
| **Simulation** | Fully functional without hardware |

## Control Logic

```
T < 20°C   →  Fan OFF    + Valve1(Recirc) OPEN  + Valve2(Exhaust) CLOSED
20 ≤ T < 25 →  Fan LOW    + Valve1 OPEN  + Valve2 CLOSED
25 ≤ T < 30 →  Fan MEDIUM + Valve1 CLOSED + Valve2 OPEN
T ≥ 30°C   →  Fan HIGH   + Valve1 CLOSED + Valve2 OPEN

Fault override: if exhaust mode but no outlet airflow detected → switch to recirculation
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Current system state |
| POST | `/api/fan` | `{"speed": 0-3}` (manual mode) |
| POST | `/api/valve` | `{"valve_id": 1-2, "open": true}` (manual mode) |
| POST | `/api/mode` | `{"mode": "auto" \| "manual"}` |
| GET | `/api/history` | `?hours=24` historical data |
| GET | `/api/statistics` | 24h min/max/avg |
| GET | `/api/snmp` | SNMP MIB info |
| WS | `/ws` | Real-time stream |
| — | `/docs` | Swagger UI |

## Development

```bash
# Backend
pip install -r requirements.txt
python main.py

# Frontend (separate terminal)
cd GUI
npm install
npm run dev     # dev server on :5173 with proxy to :8000

# Production build
cd GUI && npm run build
```

## Documentation
- 📄 [Bulgarian Documentation](docs/documentation_bg.md)
- 📊 [Process Datagram](docs/process_datagram.md)
- 🎯 [Presentation](docs/presentation.html) — open in browser

