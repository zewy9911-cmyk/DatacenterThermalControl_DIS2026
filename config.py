# =============================================================================
# config.py — Central configuration for Datacenter Thermal Control System
# Raspberry Pi 5 — Distributed Embedded Thermal Management
# =============================================================================

# ── Node identity ─────────────────────────────────────────────────────────────
NODE_ID   = "datacenter_node_01"   # Unique ID for this Raspberry Pi unit
NODE_NAME = "Сървърна стая А"      # Human-readable location label

# ── Sensor ────────────────────────────────────────────────────────────────────
# Options: "BME280" | "DHT22" | "SHT40_USB"
# SHT40_USB: reads JSON from a WIO Terminal connected via USB-Serial
SENSOR_TYPE        = "SHT40_USB"  # set to "BME280" or "DHT22" for direct I²C/GPIO
SENSOR_I2C_ADDRESS = 0x76         # BME280 primary address (alt: 0x77)
DHT_GPIO_PIN       = 4            # BCM pin for DHT22 data line

# ── WIO Terminal / SHT40 USB-Serial ──────────────────────────────────────────
# The WIO Terminal (ATSAMD51) streams JSON lines over USB-CDC.
# On Raspberry Pi OS the device appears as /dev/ttyACM0 (or ttyACM1 if busy).
WIO_SERIAL_PORT    = "/dev/ttyACM0"   # USB port for the WIO Terminal
WIO_SERIAL_BAUD    = 115200           # must match WIOTerminal.ino SERIAL_BAUD
WIO_SERIAL_TIMEOUT = 3.0              # seconds to wait for a line

# ── GPIO Pin Map (BCM numbering, Raspberry Pi 5) ──────────────────────────────
#
#  Pin layout reference:
#   BME280 SDA  ── GPIO  2 (Pin  3)  [hardware I²C, fixed]
#   BME280 SCL  ── GPIO  3 (Pin  5)  [hardware I²C, fixed]
#   DHT22 DATA  ── GPIO  4 (Pin  7)
#   STATUS LED  ── GPIO 17 (Pin 11)  green — system running
#   ALARM  LED  ── GPIO 27 (Pin 13)  red   — temperature alert
#   MODE BUTTON ── GPIO 22 (Pin 15)  toggles AUTO↔MANUAL
#   FAN TACH    ── GPIO 23 (Pin 16)  tachometer pulse input (optional)
#   VALVE 1 FB  ── GPIO 24 (Pin 18)  valve-1 limit-switch feedback (optional)
#   VALVE 2 FB  ── GPIO 25 (Pin 22)  valve-2 limit-switch feedback (optional)
#
GPIO_DHT22_DATA   = 4    # DHT22 data pin
GPIO_LED_STATUS   = 17   # Green LED: system running / heartbeat
GPIO_LED_ALARM    = 27   # Red LED: temperature or humidity alarm
GPIO_BTN_MODE     = 22   # Pushbutton: short press = toggle AUTO/MANUAL
GPIO_FAN_TACH     = 23   # Fan tachometer input (NPN open-collector pulse)
GPIO_VALVE1_FB    = 24   # Valve 1 feedback (0 = closed, 1 = open)
GPIO_VALVE2_FB    = 25   # Valve 2 feedback (0 = closed, 1 = open)

# Button debounce
GPIO_BTN_DEBOUNCE_MS = 200

# ── Modbus RTU ────────────────────────────────────────────────────────────────
MODBUS_PORT      = "/dev/ttyUSB0"   # RS-485 adapter (or /dev/ttyS0)
MODBUS_BAUDRATE  = 9600
MODBUS_SLAVE_ID  = 1
MODBUS_TIMEOUT   = 1.0
MODBUS_PARITY    = "N"
MODBUS_STOPBITS  = 1
MODBUS_BYTESIZE  = 8

# Coil addresses — Fan speed (one-hot: only one active at a time)
COIL_FAN_LOW    = 0   # Relay 1 → Fan 1st gear  (~33 %)
COIL_FAN_MED    = 1   # Relay 2 → Fan 2nd gear  (~66 %)
COIL_FAN_HIGH   = 2   # Relay 3 → Fan 3rd gear  (100 %)

# Coil addresses — Damper valves
COIL_VALVE_RECIRC  = 3   # Relay 4 → Valve 1 recirculation (въздух вътре)
COIL_VALVE_EXHAUST = 4   # Relay 5 → Valve 2 exhaust       (въздух навън)

# Discrete Input addresses — Airflow detection
DI_AIRFLOW_INLET  = 0   # DI 0 → inlet airflow sensor
DI_AIRFLOW_OUTLET = 1   # DI 1 → outlet airflow sensor

# ── Temperature thresholds (°C) ───────────────────────────────────────────────
TEMP_THRESH_OFF    = 20.0   # Below → Fan OFF,    Recirculation
TEMP_THRESH_LOW    = 25.0   # Below → Fan LOW,    Recirculation
TEMP_THRESH_MED    = 30.0   # Below → Fan MEDIUM, Exhaust
#                             Above → Fan HIGH,   Exhaust

# Humidity alert thresholds (%)
HUMIDITY_HIGH_WARN = 70.0
HUMIDITY_LOW_WARN  = 25.0

# ── SNMP ──────────────────────────────────────────────────────────────────────
SNMP_COMMUNITY    = "public"
SNMP_LISTEN_PORT  = 161
SNMP_TRAP_PORT    = 162
SNMP_MANAGER_HOST = "192.168.1.1"   # IP of NMS / SNMP manager

# Enterprise OID base  (private enterprise: 54321 as example)
SNMP_ENTERPRISE_OID = "1.3.6.1.4.1.54321"
# Sub-OIDs
OID_TEMPERATURE     = f"{SNMP_ENTERPRISE_OID}.1.1.0"   # Integer ×10 (°C)
OID_HUMIDITY        = f"{SNMP_ENTERPRISE_OID}.1.2.0"   # Integer ×10 (%)
OID_FAN_SPEED       = f"{SNMP_ENTERPRISE_OID}.2.1.0"   # 0–3
OID_VALVE_RECIRC    = f"{SNMP_ENTERPRISE_OID}.2.2.0"   # 0/1
OID_VALVE_EXHAUST   = f"{SNMP_ENTERPRISE_OID}.2.3.0"   # 0/1
OID_AIRFLOW_INLET   = f"{SNMP_ENTERPRISE_OID}.3.1.0"   # 0/1
OID_AIRFLOW_OUTLET  = f"{SNMP_ENTERPRISE_OID}.3.2.0"   # 0/1
OID_TRAP_TEMP_HIGH  = f"{SNMP_ENTERPRISE_OID}.4.1"     # Trap
OID_TRAP_HUM_HIGH   = f"{SNMP_ENTERPRISE_OID}.4.2"     # Trap

# ── Storage ───────────────────────────────────────────────────────────────────
DB_PATH        = "Storage/data.db"
LOG_INTERVAL_S = 60          # seconds between DB log inserts

# ── Web server ────────────────────────────────────────────────────────────────
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# ── MQTT ──────────────────────────────────────────────────────────────────────
# Primary telemetry transport. Falls back to SNMP if broker is unreachable.
MQTT_ENABLED      = True
MQTT_BROKER_HOST  = "192.168.1.100"  # IP of the Mosquitto broker
MQTT_BROKER_PORT  = 1883             # 1883 plain, 8883 TLS
MQTT_USERNAME     = ""               # Leave empty if no authentication
MQTT_PASSWORD     = ""
MQTT_TLS          = False            # Set True and configure certs for TLS
MQTT_KEEPALIVE    = 60               # seconds
MQTT_QOS          = 1                # 0=at most once, 1=at least once, 2=exactly once
MQTT_RETAIN       = True             # Retain last value on broker

# Topic hierarchy:  datacenter/<NODE_ID>/<subtopic>
MQTT_TOPIC_BASE   = f"datacenter/{NODE_ID}"

# Reconnect / fallback behaviour
MQTT_RECONNECT_DELAY_S  = 5    # seconds between reconnect attempts
MQTT_MAX_RECONNECTS     = 10   # after this many failures → activate SNMP fallback
MQTT_FALLBACK_TO_SNMP   = True # True = SNMP traps while MQTT is down

# ── Control ───────────────────────────────────────────────────────────────────
SENSOR_POLL_INTERVAL_S = 5   # main loop cadence

