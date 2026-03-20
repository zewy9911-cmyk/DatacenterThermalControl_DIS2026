# Процесна диаграма — Разпределена вградена система за термично управление на ЦД

## Основен управляващ цикъл (всеки 5 секунди)

```mermaid
flowchart TD
    START([▶ Стартиране на системата]) --> INIT

    INIT[Инициализация:\nSensor · Modbus · SNMP · SQLite] --> LOOP

    LOOP([🔄 Основен цикъл — 5 сек]) --> READ_SENSOR

    READ_SENSOR[/📡 Четене на сензор\nBME280 / DHT22\nТемпература & Влажност/]
    READ_SENSOR --> READ_DI

    READ_DI[/🔌 Четене на Modbus DI\nDI-0: Входящ въздух\nDI-1: Изходящ въздух/]
    READ_DI --> CHECK_MODE

    CHECK_MODE{Режим?}
    CHECK_MODE -- АВТО --> TEMP_CHECK
    CHECK_MODE -- РЪЧЕН --> MANUAL_CMD

    MANUAL_CMD[/👤 REST API команди\nОт потребителя/] --> MODBUS_WRITE

    TEMP_CHECK{Температура?}
    TEMP_CHECK -- "T < 20 °C"  --> FAN_OFF
    TEMP_CHECK -- "20 ≤ T < 25 °C" --> FAN_LOW
    TEMP_CHECK -- "25 ≤ T < 30 °C" --> FAN_MED
    TEMP_CHECK -- "T ≥ 30 °C"  --> FAN_HIGH

    FAN_OFF[🔴 Вентилатор: ИЗКЛ\nКлапа 1 Рецирк: ОТВОРЕНА\nКлапа 2 Изпускане: ЗАТВОРЕНА]
    FAN_LOW[🟢 Вентилатор: НИСКА скорост\nКлапа 1 Рецирк: ОТВОРЕНА\nКлапа 2 Изпускане: ЗАТВОРЕНА]
    FAN_MED[🟡 Вентилатор: СРЕДНА скорост\nКлапа 1 Рецирк: ЗАТВОРЕНА\nКлапа 2 Изпускане: ОТВОРЕНА]
    FAN_HIGH[🔴 Вентилатор: ВИСОКА скорост\nКлапа 1 Рецирк: ЗАТВОРЕНА\nКлапа 2 Изпускане: ОТВОРЕНА]

    FAN_OFF & FAN_LOW & FAN_MED & FAN_HIGH --> AIRFLOW_CHECK

    AIRFLOW_CHECK{Проблем с\nвъздушен поток?}
    AIRFLOW_CHECK -- "DI-1 = 0 и\nтребва изпускане" --> FAULT_OVERRIDE
    AIRFLOW_CHECK -- Нормално --> MODBUS_WRITE

    FAULT_OVERRIDE[⚠ Превключи на\nРЕЦИРКУЛАЦИЯ\nлог на предупреждение] --> MODBUS_WRITE

    MODBUS_WRITE[🔧 Modbus RTU запис\nRelay 1-3: скорост вентилатор\nRelay 4-5: клапи]
    MODBUS_WRITE --> SNMP_UPDATE

    SNMP_UPDATE[📶 SNMP обновяване\nOID стойности] --> SNMP_TRAP_CHECK

    SNMP_TRAP_CHECK{Праг\nпресечен?}
    SNMP_TRAP_CHECK -- Да --> SNMP_TRAP
    SNMP_TRAP_CHECK -- Не --> DB_CHECK

    SNMP_TRAP[📤 Изпрати SNMP Trap\nкъм NMS мениджър] --> DB_CHECK

    DB_CHECK{60 сек\nизтекли?}
    DB_CHECK -- Да  --> DB_LOG
    DB_CHECK -- Не  --> WS_BROADCAST

    DB_LOG[💾 SQLite запис\nТемп · Влаж · Вентил · Клапи · Режим] --> WS_BROADCAST

    WS_BROADCAST[📡 WebSocket broadcast\nкъм React dashboard] --> LOOP
```

---

## REST API — ръчни команди (втори поток)

```mermaid
flowchart LR
    CLIENT([🌐 React UI / curl]) -->|POST /api/mode 'manual'| MODE_SET
    MODE_SET[Смени режим → РЪЧЕН] --> FAN_REQ

    FAN_REQ([POST /api/fan\nspeed: 0-3]) --> VALIDATE_FAN
    VALIDATE_FAN{Режим = РЪЧЕН?}
    VALIDATE_FAN -- Да  --> MODBUS_FAN[Modbus: пиши скорост]
    VALIDATE_FAN -- Не  --> ERR403[403 Forbidden]

    VALVE_REQ([POST /api/valve\nvalve_id: 1 or 2]) --> VALIDATE_VALVE
    VALIDATE_VALVE{Режим = РЪЧЕН?}
    VALIDATE_VALVE -- Да  --> MODBUS_VALVE[Modbus: пиши клапа]
    VALIDATE_VALVE -- Не  --> ERR403
```

---

## Хардуерна блок-схема

```mermaid
flowchart LR
    subgraph RPI ["🖥 Raspberry Pi 5"]
        direction TB
        OS[Raspberry Pi OS]
        PY[Python FastAPI + Uvicorn]
        REACT[React Dashboard\nGUI/dist → port 8000]
    end

    subgraph SENSORS ["📡 Сензори"]
        BME[BME280\nI²C 0x76\nТемпература + Влажност]
        AF1[Датчик за въздух\nDI-0 Вход]
        AF2[Датчик за въздух\nDI-1 Изход]
    end

    subgraph MODBUS_DEV ["🔌 Modbus RTU RS-485 модул"]
        R1[Relay 1\nВент. НИСКА]
        R2[Relay 2\nВент. СРЕДНА]
        R3[Relay 3\nВент. ВИСОКА]
        R4[Relay 4\nКлапа 1 Рецирк]
        R5[Relay 5\nКлапа 2 Изпускане]
    end

    subgraph NETWORK ["🌐 Мрежа"]
        NMS[SNMP мениджър\nNMS / Zabbix / PRTG]
        BROWSER[Браузър\nReact UI]
    end

    BME   -->|I²C SDA/SCL| RPI
    AF1   -->|DI-0| MODBUS_DEV
    AF2   -->|DI-1| MODBUS_DEV
    RPI   -->|RS-485 /dev/ttyUSB0| MODBUS_DEV
    R1 & R2 & R3 -->|230VAC / 24VDC| FAN([🌀 Вентилатор\n3 степени])
    R4 -->|24VDC актуатор| V1([♻ Клапа 1\nРециркулация])
    R5 -->|24VDC актуатор| V2([🌬 Клапа 2\nИзпускане])
    RPI -->|UDP 162 SNMP Trap| NMS
    RPI -->|TCP 8000 HTTP/WS| BROWSER
```

