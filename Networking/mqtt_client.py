"""
Networking/mqtt_client.py
MQTT publisher / subscriber for multi-node datacenter telemetry.

Architecture
────────────
  Each Raspberry Pi is a "node". All nodes publish to a shared Mosquitto broker.
  Nodes can also subscribe to remote control commands from any other client.

Topic layout  (base = "datacenter/<NODE_ID>")
────────────────────────────────────────────
  <base>/status              JSON full state (retained)
  <base>/sensors/temperature float (retained)
  <base>/sensors/humidity    float (retained)
  <base>/actuators/fan_speed 0–3   (retained)
  <base>/actuators/valve1    0/1   (retained)
  <base>/actuators/valve2    0/1   (retained)
  <base>/airflow/inlet       0/1   (retained)
  <base>/airflow/outlet      0/1   (retained)
  <base>/alerts              JSON array (non-retained)

  <base>/cmd/fan_speed       {"speed": 0-3}
  <base>/cmd/valve           {"valve_id": 1-2, "open": true}
  <base>/cmd/mode            {"mode": "auto"|"manual"}
  <base>/cmd/thresholds      {"off": 20, "low": 25, "medium": 30}

Fallback
────────
  If MQTT_MAX_RECONNECTS attempts fail, `using_snmp_fallback` becomes True.
  The caller (main.py) then routes telemetry through the SNMP agent instead.
  MQTT reconnection continues in the background; fallback is cleared on success.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class MQTTClient:
    """Thread-safe paho-mqtt wrapper with automatic reconnect and SNMP fallback."""

    def __init__(
        self,
        on_fan_cmd:       Optional[Callable[[int],        None]] = None,
        on_valve_cmd:     Optional[Callable[[int, bool],  None]] = None,
        on_mode_cmd:      Optional[Callable[[str],        None]] = None,
        on_threshold_cmd: Optional[Callable[[dict],       None]] = None,
    ):
        self._on_fan_cmd       = on_fan_cmd
        self._on_valve_cmd     = on_valve_cmd
        self._on_mode_cmd      = on_mode_cmd
        self._on_threshold_cmd = on_threshold_cmd

        self._client           = None
        self._connected        = False
        self._sim              = False
        self._reconnect_count  = 0
        self._using_fallback   = False
        self._lock             = threading.Lock()

        # Build topic strings
        base = config.MQTT_TOPIC_BASE
        self._topics = {
            "status":     f"{base}/status",
            "temp":       f"{base}/sensors/temperature",
            "hum":        f"{base}/sensors/humidity",
            "fan":        f"{base}/actuators/fan_speed",
            "valve1":     f"{base}/actuators/valve1",
            "valve2":     f"{base}/actuators/valve2",
            "af_in":      f"{base}/airflow/inlet",
            "af_out":     f"{base}/airflow/outlet",
            "alerts":     f"{base}/alerts",
            "cmd_fan":    f"{base}/cmd/fan_speed",
            "cmd_valve":  f"{base}/cmd/valve",
            "cmd_mode":   f"{base}/cmd/mode",
            "cmd_thresh": f"{base}/cmd/thresholds",
        }

        if config.MQTT_ENABLED:
            self._init()
        else:
            logger.info("MQTT disabled in config — using SNMP only")
            self._sim = True

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init(self):
        try:
            import paho.mqtt.client as mqtt

            self._client = mqtt.Client(
                client_id=config.NODE_ID,
                clean_session=False,
                protocol=mqtt.MQTTv311,
            )

            self._client.on_connect    = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message    = self._on_message

            if config.MQTT_USERNAME:
                self._client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)

            if config.MQTT_TLS:
                self._client.tls_set()

            # Last Will — broker publishes this if we drop unexpectedly
            lwt = json.dumps({
                "node_id":  config.NODE_ID,
                "node_name": config.NODE_NAME,
                "status":   "offline",
            })
            self._client.will_set(
                self._topics["status"], lwt,
                qos=config.MQTT_QOS, retain=True,
            )

            self._client.reconnect_delay_set(
                min_delay=config.MQTT_RECONNECT_DELAY_S,
                max_delay=config.MQTT_RECONNECT_DELAY_S * 4,
            )

            self._connect()

        except ImportError:
            logger.warning("paho-mqtt not installed — MQTT disabled, using SNMP")
            self._sim = True
        except Exception as exc:
            logger.error("MQTT init failed: %s", exc)
            self._activate_fallback()

    def _connect(self):
        try:
            self._client.connect_async(
                config.MQTT_BROKER_HOST,
                config.MQTT_BROKER_PORT,
                keepalive=config.MQTT_KEEPALIVE,
            )
            self._client.loop_start()
            logger.info(
                "MQTT connecting to %s:%d as '%s'",
                config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT, config.NODE_ID,
            )
        except Exception as exc:
            logger.warning("MQTT initial connect failed: %s", exc)
            self._reconnect_count += 1
            self._check_fallback_threshold()

    # ── paho callbacks ────────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            with self._lock:
                self._connected       = True
                self._reconnect_count = 0
                self._using_fallback  = False

            logger.info(
                "MQTT connected ✓ broker=%s:%d",
                config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT,
            )

            # Subscribe to all command topics
            cmd_topics = [
                (self._topics["cmd_fan"],    config.MQTT_QOS),
                (self._topics["cmd_valve"],  config.MQTT_QOS),
                (self._topics["cmd_mode"],   config.MQTT_QOS),
                (self._topics["cmd_thresh"], config.MQTT_QOS),
            ]
            client.subscribe(cmd_topics)
            logger.debug("MQTT subscribed to command topics")

        else:
            rc_messages = {
                1: "incorrect protocol version",
                2: "invalid client identifier",
                3: "server unavailable",
                4: "bad username or password",
                5: "not authorised",
            }
            logger.error("MQTT connection refused: %s (rc=%d)", rc_messages.get(rc, "unknown"), rc)
            with self._lock:
                self._connected = False
            self._reconnect_count += 1
            self._check_fallback_threshold()

    def _on_disconnect(self, client, userdata, rc):
        with self._lock:
            self._connected = False

        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly (rc=%d) — auto-reconnecting", rc)
            self._reconnect_count += 1
            self._check_fallback_threshold()
        else:
            logger.info("MQTT disconnected cleanly")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic   = msg.topic
            logger.info("MQTT cmd ← %s : %s", topic, payload)

            if topic == self._topics["cmd_fan"] and self._on_fan_cmd:
                speed = int(payload.get("speed", 0))
                self._on_fan_cmd(speed)

            elif topic == self._topics["cmd_valve"] and self._on_valve_cmd:
                vid  = int(payload.get("valve_id", 1))
                open_ = bool(payload.get("open", False))
                self._on_valve_cmd(vid, open_)

            elif topic == self._topics["cmd_mode"] and self._on_mode_cmd:
                self._on_mode_cmd(str(payload.get("mode", "auto")))

            elif topic == self._topics["cmd_thresh"] and self._on_threshold_cmd:
                self._on_threshold_cmd(payload)

        except Exception as exc:
            logger.error("MQTT message handler error: %s", exc)

    # ── Fallback logic ────────────────────────────────────────────────────────

    def _check_fallback_threshold(self):
        if (
            config.MQTT_FALLBACK_TO_SNMP
            and self._reconnect_count >= config.MQTT_MAX_RECONNECTS
        ):
            self._activate_fallback()

    def _activate_fallback(self):
        if not self._using_fallback:
            self._using_fallback = True
            logger.warning(
                "MQTT fallback active after %d attempts — telemetry via SNMP",
                self._reconnect_count,
            )

    # ── Publish ───────────────────────────────────────────────────────────────

    def publish(self, state: dict) -> bool:
        """
        Publish full system state to MQTT.
        Returns True if published successfully, False if MQTT unavailable.
        """
        if self._sim or not self._connected:
            return False

        try:
            qos    = config.MQTT_QOS
            retain = config.MQTT_RETAIN
            t      = self._topics

            # Full JSON status
            full_payload = json.dumps({
                **state,
                "node_id":   config.NODE_ID,
                "node_name": config.NODE_NAME,
            }, default=str)
            self._client.publish(t["status"],  full_payload,                          qos=qos, retain=retain)

            # Individual scalar topics (useful for simple subscribers / dashboards)
            self._client.publish(t["temp"],    str(state.get("temperature", 0)),      qos=qos, retain=retain)
            self._client.publish(t["hum"],     str(state.get("humidity",    0)),      qos=qos, retain=retain)
            self._client.publish(t["fan"],     str(state.get("fan_speed",   0)),      qos=qos, retain=retain)
            self._client.publish(t["valve1"],  str(int(state.get("valve1_open", False))), qos=qos, retain=retain)
            self._client.publish(t["valve2"],  str(int(state.get("valve2_open", False))), qos=qos, retain=retain)
            self._client.publish(t["af_in"],   str(int(state.get("airflow_inlet",  False))), qos=qos, retain=retain)
            self._client.publish(t["af_out"],  str(int(state.get("airflow_outlet", False))), qos=qos, retain=retain)

            # Alerts (non-retained — only relevant when they fire)
            alerts = state.get("alerts", [])
            if alerts:
                self._client.publish(t["alerts"], json.dumps(alerts), qos=qos, retain=False)

            return True

        except Exception as exc:
            logger.error("MQTT publish error: %s", exc)
            self._reconnect_count += 1
            self._check_fallback_threshold()
            return False

    # ── Status / helpers ──────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._sim

    @property
    def using_snmp_fallback(self) -> bool:
        """True when MQTT is down and SNMP is the active telemetry path."""
        return self._using_fallback or self._sim

    def get_status(self) -> dict:
        return {
            "enabled":          config.MQTT_ENABLED,
            "connected":        self._connected,
            "broker":           f"{config.MQTT_BROKER_HOST}:{config.MQTT_BROKER_PORT}",
            "node_id":          config.NODE_ID,
            "node_name":        config.NODE_NAME,
            "reconnect_count":  self._reconnect_count,
            "using_snmp_fallback": self.using_snmp_fallback,
            "simulation":       self._sim,
            "topic_base":       config.MQTT_TOPIC_BASE,
        }

    def disconnect(self):
        if self._client and not self._sim:
            try:
                self._client.publish(
                    self._topics["status"],
                    json.dumps({"node_id": config.NODE_ID, "status": "offline"}),
                    qos=1, retain=True,
                )
                time.sleep(0.3)
            except Exception:
                pass
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTT disconnected")

