# Документация — Разпределена вградена система за термично управление на център за данни

**Версия:** 1.1.0 | **Дата:** Март 2026 | **Платформа:** Raspberry Pi 5  
**Курс:** Разпределени Вградени Системи | **Тип:** Курсов проект  
**Студенти:** Стефани Узунова 616551 · Владимир Върбанов 616602 · Данаил Атанасов 616614

---

## Съдържание

1. [Описание на системата](#1-описание-на-системата)
2. [Хардуерни изисквания](#2-хардуерни-изисквания)
3. [GPIO разпределение на пиновете](#3-gpio-разпределение-на-пиновете)
4. [Modbus RTU адресна карта](#4-modbus-rtu-адресна-карта)
5. [Електрическа схема и свързване](#5-електрическа-схема-и-свързване)
6. [Инсталация на софтуера](#6-инсталация-на-софтуера)
7. [Конфигурация](#7-конфигурация)
8. [Стартиране на системата](#8-стартиране-на-системата)
9. [Логика на управление](#9-логика-на-управление)
10. [MQTT брокер и multi-node поддръжка](#10-mqtt-брокер-и-multi-node-поддръжка)
11. [REST API референция](#11-rest-api-референция)
12. [WebSocket протокол](#12-websocket-протокол)
13. [SNMP агент и OID таблица](#13-snmp-агент-и-oid-таблица)
14. [Симулационен режим](#14-симулационен-режим)
15. [База данни](#15-база-данни)
16. [Потребителски интерфейс](#16-потребителски-интерфейс)
17. [Системна услуга (systemd)](#17-системна-услуга-systemd)
18. [Отстраняване на неизправности](#18-отстраняване-на-неизправности)

---

## 1. Описание на системата

Системата представлява **разпределена вградена система за термично управление** на център за данни, реализирана на **Raspberry Pi 5**. Тя включва два основни модула:

### Модул 1 — Следене на температурата и влажността
- Непрекъснато четене на данни от сензор **BME280** (или DHT22) чрез I²C интерфейс
- Докладване на стойностите чрез **SNMP v2c** и **MQTT** протоколи
- Съхранение на данните в локална **SQLite** база данни
- Визуализация в реално време в **React уеб интерфейс**

### Модул 2 — Управление на вентилацията
- Управление на **вентилатор с 3 степени** чрез **Modbus RTU** релейни изходи (coils 0–2, one-hot)
- Управление на **2 клапи** (coils 3–4): Клапа 1 = Рециркулация / Клапа 2 = Изпускане навън
- Детекция на въздушен поток чрез **Modbus DI 0 и DI 1**
- GPIO управление: Статус LED, Alarm LED, Режимен бутон, Тахометър, Valve feedback
- **MQTT брокер** (Mosquitto) за координация между множество Pi устройства
- При неналичен MQTT брокер — автоматичен **fallback към SNMP**

---

## 2. Хардуерни изисквания

| Компонент | Модел / Спецификация | Брой |
|-----------|---------------------|------|
| Едноплаткови компютър | Raspberry Pi 5 (4 GB RAM) | 1 |
| Сензор температура/влажност | BME280 (I²C, 3.3V) | 1 |
| Алт. сензор | DHT22 (GPIO 4) | 1 |
| RS-485 USB адаптер | CH340 или FT232 | 1 |
| Modbus RTU релеен модул | 8-канален, 5A/230VAC (RS-485) | 1 |
| Вентилатор | 3-степенен AC/DC | 1 |
| Актуатори за клапи | 24 VDC моторизирани | 2 |
| Въздушни датчици | NPN/PNP дигитален изход | 2 |
| Статус LED (зелен) | 3mm или 5mm, 3.3V | 1 |
| Alarm LED (червен) | 3mm или 5mm, 3.3V | 1 |
| Бутон | Нормално отворен, PU | 1 |

---

## 3. GPIO разпределение на пиновете

Всички пинове са в **BCM номерация** (не физическа).

| GPIO (BCM) | Физ. пин | Посока | Функция |
|-----------|----------|--------|---------|
| GPIO 2 (SDA) | Pin 3 | Двупосочен | BME280 — I²C Data |
| GPIO 3 (SCL) | Pin 5 | Изход | BME280 — I²C Clock |
| GPIO 4 | Pin 7 | Вход | DHT22 данни (алт. сензор) |
| GPIO 17 | Pin 11 | Изход | Статус LED — зелен (heartbeat 0.1s ON / 0.9s OFF) |
| GPIO 27 | Pin 13 | Изход | Alarm LED — червен (T° критична или RH висока) |
| GPIO 22 | Pin 15 | Вход (PU) | Бутон — превключване АВТО ↔ РЪЧЕН (дебаунс 200 ms) |
| GPIO 23 | Pin 16 | Вход | Тахометър на вентилатора (NPN open-collector, 2 импулса/об.) |
| GPIO 24 | Pin 18 | Вход (PD) | Обратна връзка Клапа 1 (лимитен превключвател) |
| GPIO 25 | Pin 22 | Вход (PD) | Обратна връзка Клапа 2 (лимитен превключвател) |

> **PU** = Pull-Up вграден | **PD** = Pull-Down вграден

Конфигурация в `config.py`:
```python
GPIO_LED_STATUS  = 17
GPIO_LED_ALARM   = 27
GPIO_BTN_MODE    = 22
GPIO_FAN_TACH    = 23
GPIO_VALVE1_FB   = 24
GPIO_VALVE2_FB   = 25
GPIO_DHT22_DATA  = 4
GPIO_BTN_DEBOUNCE_MS = 200
```

---

## 4. Modbus RTU адресна карта

**Порт:** `/dev/ttyUSB0` | **Baud:** 9600 | **Slave ID:** 1 | **Parity:** N | **Stop:** 1

| Тип | Адрес | Функция |
|-----|-------|---------|
| Coil | 0 | Вентилатор НИСКА (~33%) |
| Coil | 1 | Вентилатор СРЕДНА (~66%) |
| Coil | 2 | Вентилатор ВИСОКА (100%) |
| Coil | 3 | Клапа 1 — Рециркулация |
| Coil | 4 | Клапа 2 — Изпускане навън |
| DI | 0 | Датчик входящ въздушен поток |
| DI | 1 | Датчик изходящ въздушен поток |

> Само **един** от Coil 0, 1, 2 трябва да е активен едновременно (one-hot логика).

---

## 5. Електрическа схема и свързване

### BME280 → Raspberry Pi 5 (I²C)

| BME280 пин | RPi 5 пин | Описание |
|-----------|-----------|----------|
| VIN/VCC | Pin 1 (3.3V) | Захранване |
| GND | Pin 6 (GND) | Маса |
| SDA | Pin 3 (GPIO2) | Data |
| SCL | Pin 5 (GPIO3) | Clock |

### USB-RS485 → Modbus RTU модул

| RS-485 адаптер | Modbus модул |
|----------------|-------------|
| A (+) | A (+) |
| B (-) | B (-) |

---

## 6. Инсталация на софтуера

### 6.1 Системни изисквания
- Raspberry Pi OS 64-bit (Bookworm+)
- Python 3.11+
- Node.js 20+ и npm 10+

### 6.2 Автоматична инсталация
```bash
bash install.sh
# → пита дали да инсталира Mosquitto MQTT брокер
# → активира I²C, инсталира зависимости, изгражда React, инсталира systemd
```

### 6.3 Python зависимости
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Ключови пакети: `fastapi`, `uvicorn[standard]`, `pymodbus>=3.6`, `pysnmp>=6.1`, `paho-mqtt>=1.6.1,<3.0`, `aiosqlite`, `wsproto`, `smbus2`, `RPi.GPIO`

### 6.4 React Dashboard
```bash
cd GUI && npm install && npm run build
```

---

## 7. Конфигурация

Всички настройки са в `config.py`:

```python
# Идентификация на Pi устройството
NODE_ID   = "datacenter_node_01"
NODE_NAME = "Сървърна стая А"

# Сензор
SENSOR_TYPE        = "BME280"   # или "DHT22"
SENSOR_I2C_ADDRESS = 0x76

# Modbus
MODBUS_PORT     = "/dev/ttyUSB0"
MODBUS_BAUDRATE = 9600
MODBUS_SLAVE_ID = 1

# Температурни прагове (°C)
TEMP_THRESH_OFF  = 20.0
TEMP_THRESH_LOW  = 25.0
TEMP_THRESH_MED  = 30.0

# MQTT
MQTT_ENABLED      = True
MQTT_BROKER_HOST  = "192.168.1.100"
MQTT_BROKER_PORT  = 1883
MQTT_USERNAME     = ""
MQTT_PASSWORD     = ""
MQTT_MAX_RECONNECTS    = 10
MQTT_FALLBACK_TO_SNMP  = True

# SNMP
SNMP_COMMUNITY    = "public"
SNMP_MANAGER_HOST = "192.168.1.1"

# Уеб сървър
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000
```

---

## 8. Стартиране на системата

### Ръчно стартиране
```bash
source venv/bin/activate
python main.py
```
Уеб интерфейс: `http://<RPi-IP>:8000`

### systemd (автоматично при зареждане)
```bash
sudo systemctl enable datacenter_thermal
sudo systemctl start  datacenter_thermal
journalctl -u datacenter_thermal -f
```

---

## 9. Логика на управление

### 9.1 Автоматичен режим

| Температура | Вентилатор | Клапа 1 (Рецирк.) | Клапа 2 (Изпускане) |
|------------|------------|------------------|---------------------|
| T < 20 °C | ИЗКЛЮЧЕН | ✅ ОТВОРЕНА | ❌ ЗАТВОРЕНА |
| 20 ≤ T < 25 °C | НИСКА | ✅ ОТВОРЕНА | ❌ ЗАТВОРЕНА |
| 25 ≤ T < 30 °C | СРЕДНА | ❌ ЗАТВОРЕНА | ✅ ОТВОРЕНА |
| T ≥ 30 °C | ВИСОКА | ❌ ЗАТВОРЕНА | ✅ ОТВОРЕНА |

### 9.2 Fault override
Ако DI-1 (изходящ поток) = 0, докато системата е в режим изпускане и DI-0 (входящ) = 1 → автоматично превключване на рециркулация + лог запис.

### 9.3 Ръчен режим
В ръчен режим операторът управлява вентилатора и клапите директно чрез REST API, MQTT команди или физически бутон (GPIO 22).

---

## 10. MQTT брокер и multi-node поддръжка

### 10.1 Инсталация на Mosquitto
```bash
sudo apt-get install -y mosquitto mosquitto-clients
sudo systemctl enable mosquitto
```

### 10.2 Топик структура
```
datacenter/{NODE_ID}/status              ← пълно JSON (retained)
datacenter/{NODE_ID}/sensors/temperature
datacenter/{NODE_ID}/sensors/humidity
datacenter/{NODE_ID}/actuators/fan_speed
datacenter/{NODE_ID}/actuators/valve1
datacenter/{NODE_ID}/actuators/valve2
datacenter/{NODE_ID}/airflow/inlet
datacenter/{NODE_ID}/airflow/outlet
datacenter/{NODE_ID}/alerts

datacenter/{NODE_ID}/cmd/fan_speed       ← {"speed": 0-3}
datacenter/{NODE_ID}/cmd/valve           ← {"valve_id": 1-2, "open": true}
datacenter/{NODE_ID}/cmd/mode            ← {"mode": "auto"|"manual"}
datacenter/{NODE_ID}/cmd/thresholds      ← {"off": 20, "low": 25, "medium": 30}
```

### 10.3 Fallback логика
- При > `MQTT_MAX_RECONNECTS` (по подразбиране 10) неуспешни опита → `using_snmp_fallback = True`
- SNMP продължава да изпраща трапове
- При успешна MQTT връзка fallback се деактивира автоматично
- Статус: `GET /api/mqtt`

### 10.4 Тест с mosquitto_sub
```bash
mosquitto_sub -h 192.168.1.100 -t "datacenter/#" -v
# Изпрати команда за вентилатор:
mosquitto_pub -h 192.168.1.100 -t "datacenter/datacenter_node_01/cmd/fan_speed" -m '{"speed":2}'
```

---

## 11. REST API референция

Базов URL: `http://<IP>:8000/api`

| Метод | Път | Описание |
|-------|-----|----------|
| GET | `/status` | Пълно текущо състояние |
| POST | `/fan` | `{"speed": 0-3}` — ръчен режим |
| POST | `/valve` | `{"valve_id": 1-2, "open": true}` |
| POST | `/mode` | `{"mode": "auto"|"manual"}` |
| GET/POST | `/thresholds` | Прагове за температура |
| GET | `/history` | `?hours=24&limit=500` |
| GET | `/statistics` | 24ч min/max/avg |
| GET | `/events` | Системни събития |
| GET | `/snmp` | SNMP MIB информация |
| GET | `/mqtt` | MQTT статус на връзката |
| GET | `/gpio` | GPIO пинове и live стойности |
| GET | `/node` | Node ID и MQTT топик база |
| GET/POST | `/simulation` | Симулационен override |
| WS | `ws://<IP>:8000/ws` | Real-time stream |

---

## 12. WebSocket протокол

Съобщение всеки 5 секунди:
```json
{
  "timestamp": "2026-03-20T14:30:00",
  "temperature": 26.4, "humidity": 58.2,
  "fan_speed": 2, "fan_speed_name": "MEDIUM",
  "valve1_open": false, "valve2_open": true,
  "airflow_inlet": true, "airflow_outlet": true,
  "control_mode": "auto",
  "fan_rpm": 1450,
  "valve1_feedback": false, "valve2_feedback": true,
  "mqtt_connected": true, "mqtt_fallback": false,
  "node_id": "datacenter_node_01",
  "alerts": [{"level": "warning", "message": "Повишена температура: 26.4 °C"}],
  "simulation": false, "source": "sensor"
}
```

---

## 13. SNMP агент и OID таблица

**Enterprise OID:** `1.3.6.1.4.1.54321` | **Community:** `public` | **UDP:** 161/162

| OID | Описание | Формат |
|-----|----------|--------|
| `.1.1.0` | Температура | Integer ×10 (264 = 26.4°C) |
| `.1.2.0` | Влажност | Integer ×10 (582 = 58.2%) |
| `.2.1.0` | Скорост вентилатор | 0–3 |
| `.2.2.0` | Клапа 1 | 0/1 |
| `.2.3.0` | Клапа 2 | 0/1 |
| `.3.1.0` | Датчик вход | 0/1 |
| `.3.2.0` | Датчик изход | 0/1 |
| `.4.1` | Trap: T ≥ 30°C | — |
| `.4.2` | Trap: RH ≥ 70% | — |

---

## 14. Симулационен режим

### 14.1 Хардуерна симулация (автоматична)
При липса на реален хардуер системата стартира автоматично в симулационен режим:
- `sensor_reader.py` — генерира реалистични стойности (синусоидален drift)
- `modbus_control.py` — симулира relay/DI операции с лог съобщения

### 14.2 Ръчен override (API + UI)
```bash
# Включи симулация с конкретни стойности
curl -X POST http://localhost:8000/api/simulation \
  -H "Content-Type: application/json" \
  -d '{"enabled": true, "temperature": 31.5, "humidity": 68}'

# Изключи симулация (върни към live сензор)
curl -X POST http://localhost:8000/api/simulation \
  -d '{"enabled": false}'
```

### 14.3 SimulationPanel в React UI
- Слайдер температура (10–45°C) с цветова лента
- Слайдер влажност (10–95%)
- Предварителен преглед на логиката (вентилатор + клапи)
- Бързи сценарии: Нормална / Топло / Горещо / Критично / Вис. влажност
- Индикатор `⚗ СИМУЛАЦИЯ` в заглавието

---

## 15. База данни

**Тип:** SQLite 3 | **Файл:** `Storage/data.db`

Таблица `readings`: id, timestamp, temperature, humidity, fan_speed, valve_recirc, valve_exhaust, airflow_in, airflow_out, control_mode, source

Таблица `events`: id, timestamp, event_type, severity, message, value

---

## 16. Потребителски интерфейс

`http://<IP>:8000` — Тъмна тема с следните панели:
- **Сензори** — радиални циферблати + badge ⚗ при симулация
- **Режим** — АВТО/РЪЧЕН превключвател с описание
- **Вентилатор** — 4 бутона OFF/НИСКА/СРЕДНА/ВИСОКА
- **Клапи** — 2 toggle превключвателя
- **Въздушен поток** — DI-0 и DI-1 индикатори
- **GPIO обратна връзка** — RPM + позиции на клапите
- **Известия** — цветово кодирани предупреждения
- **История** — Recharts линейна графика (1/6/12/24ч)
- **Симулационен модул** — слайдери + сценарии

---

## 17. Системна услуга (systemd)

```bash
sudo cp datacenter_thermal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable datacenter_thermal
sudo systemctl start  datacenter_thermal
sudo systemctl status datacenter_thermal
journalctl -u datacenter_thermal -f
```

---

## 18. Отстраняване на неизправности

| Проблем | Причина | Решение |
|---------|---------|---------|
| WebSocket 404 / `No WS library` | websockets 16+ несъвместим с uvicorn | wsproto вече е в requirements.txt; `pip install wsproto` |
| `WinError 10054` | Windows ProactorEventLoop | Добавено `WindowsSelectorEventLoopPolicy` в main.py |
| Simulation mode active | Сензорът не е намерен | Нормално! Проверете I²C: `i2cdetect -y 1` |
| Modbus unavailable | RS-485 адаптерът липсва | `ls /dev/ttyUSB*` — нормално без хардуер |
| MQTT не се свързва | Грешен IP или брокерът не работи | `MQTT_BROKER_HOST` в config.py; `sudo systemctl status mosquitto` |
| SNMP trap не пристига | Firewall или грешен IP | Проверете `SNMP_MANAGER_HOST` |
| React build не се зарежда | GUI/dist не е изграден | `cd GUI && npm run build` |


Системата представлява **разпределена вградена система за термично управление** на център за данни, реализирана на **Raspberry Pi 5**. Тя включва два основни модула:

### Модул 1 — Следене на температурата и влажността
- Непрекъснато четене на данни от сензор **BME280** (или DHT22) чрез I²C интерфейс
- Докладване на стойностите чрез **SNMP v2c** протокол към мрежов мениджмент сървър (NMS)
- Съхранение на данните в локална **SQLite** база данни
- Визуализация в реално време в **React уеб интерфейс**

### Модул 2 — Управление на вентилацията
- Управление на **вентилатор с 3 степени** (НИСКА / СРЕДНА / ВИСОКА) чрез **Modbus RTU** релейни изходи
- Управление на **2 клапи**:
  - **Клапа 1 (Рециркулация)** — въздухът се върти вътре в стаята
  - **Клапа 2 (Изпускане)** — горещият въздух се извежда навън
- Автоматичен или ръчен режим на управление
- Детекция на въздушен поток чрез **дискретни входове (DI)** на Modbus модула

---

## 2. Хардуерни изисквания

| Компонент | Модел / Спецификация | Брой |
|-----------|---------------------|------|
| Едноплаткови компютър | Raspberry Pi 5 (4 GB RAM) | 1 |
| Сензор температура/влажност | BME280 (I²C, 3.3V) | 1 |
| RS-485 USB адаптер | CH340 или FT232 USB-to-RS485 | 1 |
| Modbus RTU релеен модул | 8-канален, 5A/230VAC (RS-485) | 1 |
| Вентилатор | 3-фазен или 3-степенен AC/DC вентилатор | 1 |
| Актуатори за клапи | 24VDC/230VAC моторизирани клапи | 2 |
| Въздушни датчици | Дигитални датчици за поток (NPN/PNP изход) | 2 |
| Захранване | 5V/5A USB-C за RPi5 | 1 |

### Алтернативен сензор
Вместо BME280 може да се използва **DHT22** (GPIO 4). Промяна в `config.py`:
```python
SENSOR_TYPE = "DHT22"
DHT_GPIO_PIN = 4
```

---

## 3. Електрическа схема и свързване

### BME280 → Raspberry Pi 5 (I²C)

| BME280 пин | RPi 5 пин | Описание |
|-----------|-----------|----------|
| VIN/VCC   | Pin 1 (3.3V) | Захранване |
| GND       | Pin 6 (GND)  | Маса |
| SDA       | Pin 3 (GPIO2, SDA1) | Data |
| SCL       | Pin 5 (GPIO3, SCL1) | Clock |

### USB-RS485 адаптер → Modbus релеен модул

| RS-485 | Modbus модул |
|--------|-------------|
| A (+)  | A (+) |
| B (-)  | B (-) |
| GND    | GND (ако е изолиран) |

### Modbus релеен модул — изходи

| Relay | Функция | Свързан елемент |
|-------|---------|----------------|
| Relay 1 (Coil 0) | Вентилатор НИСКА | Вход "Speed 1" на вентилатор |
| Relay 2 (Coil 1) | Вентилатор СРЕДНА | Вход "Speed 2" на вентилатор |
| Relay 3 (Coil 2) | Вентилатор ВИСОКА | Вход "Speed 3" на вентилатор |
| Relay 4 (Coil 3) | Клапа 1 (Рециркулация) | Актуатор клапа 1 |
| Relay 5 (Coil 4) | Клапа 2 (Изпускане) | Актуатор клапа 2 |

### Modbus релеен модул — дискретни входове (DI)

| DI вход | Функция |
|---------|---------|
| DI 0 | Датчик за въздушен поток — вход |
| DI 1 | Датчик за въздушен поток — изход |

> ⚠ **Важно:** Само един от трите relay за вентилатора трябва да е активен едновременно!

---

## 4. Инсталация на софтуера

### 4.1 Изисквания

- Raspberry Pi OS (64-bit, Bookworm или по-нова)
- Python 3.11+
- Node.js 20+ и npm 10+

### 4.2 Клониране и подготовка

```bash
git clone <repo_url> /home/pi/datacenter_thermal
cd /home/pi/datacenter_thermal
```

### 4.3 Python зависимости

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4.4 Активиране на I²C (за BME280)

```bash
sudo raspi-config
# Interface Options → I2C → Enable
# Или директно:
sudo sh -c 'echo "dtparam=i2c_arm=on" >> /boot/firmware/config.txt'
sudo reboot
# Проверка:
i2cdetect -y 1   # трябва да се вижда 0x76
```

### 4.5 Изграждане на React интерфейса

```bash
cd GUI
npm install
npm run build
cd ..
```

---

## 5. Конфигурация

Всички настройки се намират в `config.py`:

```python
# Сензор
SENSOR_TYPE        = "BME280"    # или "DHT22"
SENSOR_I2C_ADDRESS = 0x76

# Modbus
MODBUS_PORT     = "/dev/ttyUSB0"
MODBUS_BAUDRATE = 9600
MODBUS_SLAVE_ID = 1

# Температурни прагове (°C)
TEMP_THRESH_OFF  = 20.0   # под тази стойност — вентилатор ИЗКЛ
TEMP_THRESH_LOW  = 25.0   # под тази стойност — НИСКА скорост
TEMP_THRESH_MED  = 30.0   # под тази стойност — СРЕДНА; над — ВИСОКА

# SNMP
SNMP_COMMUNITY    = "public"
SNMP_MANAGER_HOST = "192.168.1.1"   # IP на NMS сървъра

# Уеб сървър
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000
```

---

## 6. Стартиране на системата

### Ръчно стартиране

```bash
cd /home/pi/datacenter_thermal
source venv/bin/activate
python main.py
```

Уеб интерфейсът се достъпва на: `http://<IP_на_RPi>:8000`

### Автоматично стартиране при зареждане (systemd)

```bash
sudo cp datacenter_thermal.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable datacenter_thermal
sudo systemctl start  datacenter_thermal
sudo systemctl status datacenter_thermal
```

---

## 7. Логика на управление

### 7.1 Автоматичен режим

| Температура | Скорост на вентилатор | Клапа 1 (Рецирк.) | Клапа 2 (Изпускане) |
|------------|----------------------|------------------|---------------------|
| T < 20 °C  | ИЗКЛЮЧЕН (0)         | ОТВОРЕНА ✅       | ЗАТВОРЕНА ❌         |
| 20 ≤ T < 25 °C | НИСКА (1)       | ОТВОРЕНА ✅       | ЗАТВОРЕНА ❌         |
| 25 ≤ T < 30 °C | СРЕДНА (2)      | ЗАТВОРЕНА ❌      | ОТВОРЕНА ✅          |
| T ≥ 30 °C  | ВИСОКА (3)           | ЗАТВОРЕНА ❌      | ОТВОРЕНА ✅          |

### 7.2 Логика на клапите

**Режим РЕЦИРКУЛАЦИЯ** (T < 25 °C):
- Въздухът циркулира вътре в стаята
- Подходящ за равномерно разпределение на охладения въздух

**Режим ИЗПУСКАНЕ** (T ≥ 25 °C):
- Горещият въздух се извежда извън стаята
- Свеж охладен въздух влиза от климатичната система

### 7.3 Защита при повреда на въздушен поток

Ако системата е в режим на изпускане, но **DI-1 (изходящ поток) не се засича**, а **DI-0 (входящ поток) е активен** — системата автоматично превключва на рециркулация и записва предупреждение в логовете.

### 7.4 Ръчен режим

В ръчен режим операторът може директно да:
- Задава скоростта на вентилатора (0–3)
- Отваря/затваря всяка клапа независимо
- Системата НЕ прилага автоматична логика

---

## 8. REST API референция

Базов URL: `http://<IP>:8000/api`

| Метод | Път | Описание | Тяло |
|-------|-----|----------|------|
| GET | `/status` | Текущо състояние на системата | — |
| POST | `/fan` | Задай скорост на вентилатор | `{"speed": 0-3}` |
| POST | `/valve` | Управлявай клапа | `{"valve_id": 1-2, "open": true/false}` |
| POST | `/mode` | Смени режим | `{"mode": "auto" \| "manual"}` |
| GET | `/thresholds` | Вземи температурни прагове | — |
| POST | `/thresholds` | Задай температурни прагове | `{"off": 20, "low": 25, "medium": 30}` |
| GET | `/history` | Исторически данни | `?hours=24&limit=500` |
| GET | `/events` | Системни събития | `?limit=50` |
| GET | `/statistics` | 24-часова статистика | — |
| GET | `/snmp` | SNMP MIB информация | — |

### Пример — задаване на скорост (curl):

```bash
# Смени в ръчен режим
curl -X POST http://192.168.1.100:8000/api/mode \
     -H "Content-Type: application/json" \
     -d '{"mode":"manual"}'

# Задай ВИСОКА скорост
curl -X POST http://192.168.1.100:8000/api/fan \
     -H "Content-Type: application/json" \
     -d '{"speed":3}'
```

---

## 9. WebSocket протокол

**Endpoint:** `ws://<IP>:8000/ws`

Системата излъчва JSON съобщение **на всеки 5 секунди**:

```json
{
  "timestamp":      "2026-03-20T14:30:00",
  "temperature":    26.4,
  "humidity":       58.2,
  "fan_speed":      2,
  "fan_speed_name": "MEDIUM",
  "valve1_open":    false,
  "valve2_open":    true,
  "airflow_inlet":  true,
  "airflow_outlet": true,
  "control_mode":   "auto",
  "alerts": [
    { "level": "warning", "message": "Повишена температура: 26.4 °C" }
  ],
  "simulation":     false,
  "source":         "sensor"
}
```

---

## 10. SNMP агент и OID таблица

**Enterprise OID основа:** `1.3.6.1.4.1.54321`
**SNMP версия:** v2c
**Community:** `public` (конфигурируемо)
**Trap порт:** 162

| OID | Описание | Стойност |
|-----|----------|---------|
| `1.3.6.1.4.1.54321.1.1.0` | Температура | Integer × 10 (напр. 264 = 26.4 °C) |
| `1.3.6.1.4.1.54321.1.2.0` | Влажност | Integer × 10 (напр. 582 = 58.2 %) |
| `1.3.6.1.4.1.54321.2.1.0` | Скорост на вентилатор | 0=ИЗКЛ, 1=НИС, 2=СР, 3=ВИСОК |
| `1.3.6.1.4.1.54321.2.2.0` | Клапа 1 (рециркулация) | 0=ЗАТВОРЕНА, 1=ОТВОРЕНА |
| `1.3.6.1.4.1.54321.2.3.0` | Клапа 2 (изпускане) | 0=ЗАТВОРЕНА, 1=ОТВОРЕНА |
| `1.3.6.1.4.1.54321.3.1.0` | Датчик входящ въздух | 0/1 |
| `1.3.6.1.4.1.54321.3.2.0` | Датчик изходящ въздух | 0/1 |

### SNMP Traps (автоматично изпращани)

| Trap OID | Условие |
|----------|---------|
| `1.3.6.1.4.1.54321.4.1` | Температура ≥ 30 °C (нарастващ ред) |
| `1.3.6.1.4.1.54321.4.2` | Влажност ≥ 70 % (нарастващ ред) |

### Тест с Net-SNMP

```bash
# GET температура
snmpget -v2c -c public 192.168.1.100:161 1.3.6.1.4.1.54321.1.1.0

# Слушай trap-ове
snmptrapd -f -Lo -c /etc/snmp/snmptrapd.conf
```

---

## 11. База данни

**Тип:** SQLite 3
**Файл:** `Storage/data.db`

### Таблица `readings`

| Колона | Тип | Описание |
|--------|-----|----------|
| `id` | INTEGER | Автоматичен ключ |
| `timestamp` | DATETIME | Дата и час на записа |
| `temperature` | REAL | Температура в °C |
| `humidity` | REAL | Влажност в % |
| `fan_speed` | INTEGER | Скорост на вентилатор (0–3) |
| `valve_recirc` | INTEGER | Клапа 1 (0/1) |
| `valve_exhaust` | INTEGER | Клапа 2 (0/1) |
| `airflow_in` | INTEGER | Входящ поток (0/1) |
| `airflow_out` | INTEGER | Изходящ поток (0/1) |
| `control_mode` | TEXT | "auto" или "manual" |
| `source` | TEXT | "sensor", "simulation", "cached" |

### Примерни заявки

```sql
-- Средна температура за последните 24 часа
SELECT AVG(temperature) FROM readings
WHERE timestamp >= datetime('now', '-24 hours');

-- Брой случаи на критична температура
SELECT COUNT(*) FROM readings WHERE temperature >= 30;
```

---

## 12. Потребителски интерфейс

Интерфейсът е достъпен на `http://<IP>:8000` и включва:

- **Сензорни индикатори** — радиални циферблати за температура и влажност с цветово кодиране
- **Превключвател АВТО/РЪЧЕН** — определя кой управлява системата
- **Управление на вентилатора** — 4 бутона: ИЗКЛ / НИСКА / СРЕДНА / ВИСОКА
- **Управление на клапите** — 2 toggle превключвателя (само в ръчен режим)
- **Датчици за въздушен поток** — визуален статус на DI входовете
- **Известия** — цветово кодирани предупреждения (зелен/жълт/червен)
- **Историческа графика** — линейна графика за последните 1/6/12/24 часа

---

## 13. Системна услуга (systemd)

Файлът `datacenter_thermal.service` трябва да се постави в `/etc/systemd/system/`.

```ini
[Unit]
Description=Datacenter Thermal Control
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/datacenter_thermal
ExecStart=/home/pi/datacenter_thermal/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Команди за управление:
```bash
sudo systemctl start   datacenter_thermal   # Стартиране
sudo systemctl stop    datacenter_thermal   # Спиране
sudo systemctl restart datacenter_thermal   # Рестартиране
sudo systemctl status  datacenter_thermal   # Статус
journalctl -u datacenter_thermal -f         # Логове в реално време
```

---

## 14. Отстраняване на неизправности

| Проблем | Причина | Решение |
|---------|---------|---------|
| "Simulation mode active" в логовете | Сензорът не е намерен | Провери I²C: `i2cdetect -y 1` |
| "Modbus unavailable" | RS-485 адаптерът не е намерен | Провери `ls /dev/ttyUSB*` |
| Интерфейсът не се зарежда | React build не е изграден | Изпълни `cd GUI && npm run build` |
| SNMP trap не пристига | Firewall или грешен IP | Провери `SNMP_MANAGER_HOST` в config.py |
| Вентилаторът не се стартира | Relay не се задейства | Провери Modbus адреса и baudrate |
| WebSocket "Изключен" | FastAPI не работи | Провери `systemctl status datacenter_thermal` |

### Активиране на verbose логове

```bash
# В main.py, промени:
logging.basicConfig(level=logging.DEBUG, ...)
```

