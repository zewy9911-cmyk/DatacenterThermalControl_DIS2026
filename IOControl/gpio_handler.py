"""
IOControl/gpio_handler.py
Manages physical GPIO pins on the Raspberry Pi 5:
  - Status LED  (GPIO 17) — heartbeat blink when system is running
  - Alarm LED   (GPIO 27) — solid ON when temperature/humidity alert is active
  - Mode button (GPIO 22) — short press toggles AUTO ↔ MANUAL
  - Fan tachometer (GPIO 23) — counts pulses to estimate fan RPM
  - Valve feedback (GPIO 24/25) — reads limit-switch state of each valve

Falls back to a no-op simulation when RPi.GPIO is not available (dev / Windows).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class GPIOHandler:
    """
    Pin assignments (BCM):
        GPIO_LED_STATUS  = 17  — green LED, heartbeat
        GPIO_LED_ALARM   = 27  — red LED, alert
        GPIO_BTN_MODE    = 22  — mode toggle button
        GPIO_FAN_TACH    = 23  — fan tachometer (pulse input)
        GPIO_VALVE1_FB   = 24  — valve 1 limit-switch feedback
        GPIO_VALVE2_FB   = 25  — valve 2 limit-switch feedback
    """

    TACH_PULSES_PER_REV = 2      # most fans: 2 pulses per revolution

    def __init__(self, on_mode_toggle: Optional[Callable] = None):
        self._sim             = False
        self._on_mode_toggle  = on_mode_toggle
        self._alarm_active    = False
        self._heartbeat_task  = None
        self._tach_count      = 0
        self._tach_lock       = threading.Lock()
        self._last_tach_ts    = time.time()
        self._rpm             = 0

        self._init()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init(self):
        try:
            import RPi.GPIO as GPIO
            self._GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)

            # Outputs
            GPIO.setup(config.GPIO_LED_STATUS,  GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(config.GPIO_LED_ALARM,   GPIO.OUT, initial=GPIO.LOW)

            # Inputs
            GPIO.setup(config.GPIO_BTN_MODE,   GPIO.IN,  pull_up_down=GPIO.PUD_UP)
            GPIO.setup(config.GPIO_FAN_TACH,   GPIO.IN,  pull_up_down=GPIO.PUD_UP)
            GPIO.setup(config.GPIO_VALVE1_FB,  GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)
            GPIO.setup(config.GPIO_VALVE2_FB,  GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)

            # Interrupts
            GPIO.add_event_detect(
                config.GPIO_BTN_MODE, GPIO.FALLING,
                callback=self._button_isr,
                bouncetime=config.GPIO_BTN_DEBOUNCE_MS,
            )
            GPIO.add_event_detect(
                config.GPIO_FAN_TACH, GPIO.FALLING,
                callback=self._tach_isr,
            )

            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True
            )
            self._heartbeat_thread.start()

            logger.info(
                "GPIO initialised — LED_STATUS=GPIO%d  LED_ALARM=GPIO%d  "
                "BTN_MODE=GPIO%d  FAN_TACH=GPIO%d  V1_FB=GPIO%d  V2_FB=GPIO%d",
                config.GPIO_LED_STATUS, config.GPIO_LED_ALARM,
                config.GPIO_BTN_MODE,   config.GPIO_FAN_TACH,
                config.GPIO_VALVE1_FB,  config.GPIO_VALVE2_FB,
            )

        except (ImportError, RuntimeError) as exc:
            logger.warning("GPIO unavailable (%s) — simulation mode", exc)
            self._sim = True

    # ── Interrupt service routines ────────────────────────────────────────────

    def _button_isr(self, channel: int):
        logger.info("Mode button pressed (GPIO %d)", channel)
        if self._on_mode_toggle:
            self._on_mode_toggle()

    def _tach_isr(self, channel: int):
        with self._tach_lock:
            self._tach_count += 1

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        """Blink status LED: 1 quick flash per second while running."""
        while True:
            self._set_pin(config.GPIO_LED_STATUS, True)
            time.sleep(0.1)
            self._set_pin(config.GPIO_LED_STATUS, False)
            time.sleep(0.9)

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_alarm(self, active: bool):
        """Turn alarm LED on or off."""
        if self._alarm_active != active:
            self._alarm_active = active
            self._set_pin(config.GPIO_LED_ALARM, active)
            logger.info("Alarm LED → %s", "ON" if active else "OFF")

    def read_valve_feedback(self) -> dict:
        """Read valve limit-switch feedback pins."""
        if self._sim:
            return {"valve1_feedback": None, "valve2_feedback": None}
        GPIO = self._GPIO
        return {
            "valve1_feedback": bool(GPIO.input(config.GPIO_VALVE1_FB)),
            "valve2_feedback": bool(GPIO.input(config.GPIO_VALVE2_FB)),
        }

    def get_fan_rpm(self) -> int:
        """Return estimated fan RPM from tachometer pulses since last call."""
        now = time.time()
        elapsed = now - self._last_tach_ts
        if elapsed < 0.5:            # not enough time elapsed
            return self._rpm

        with self._tach_lock:
            pulses = self._tach_count
            self._tach_count = 0

        self._last_tach_ts = now
        if elapsed > 0 and pulses > 0:
            rps = (pulses / self.TACH_PULSES_PER_REV) / elapsed
            self._rpm = int(rps * 60)
        else:
            self._rpm = 0
        return self._rpm

    def get_status(self) -> dict:
        fb = self.read_valve_feedback()
        return {
            "alarm_active":    self._alarm_active,
            "fan_rpm":         self.get_fan_rpm() if not self._sim else None,
            "valve1_feedback": fb["valve1_feedback"],
            "valve2_feedback": fb["valve2_feedback"],
            "simulation":      self._sim,
            "pins": {
                "led_status":  config.GPIO_LED_STATUS,
                "led_alarm":   config.GPIO_LED_ALARM,
                "btn_mode":    config.GPIO_BTN_MODE,
                "fan_tach":    config.GPIO_FAN_TACH,
                "valve1_fb":   config.GPIO_VALVE1_FB,
                "valve2_fb":   config.GPIO_VALVE2_FB,
                "dht22_data":  config.GPIO_DHT22_DATA,
            },
        }

    def cleanup(self):
        if not self._sim:
            self._set_pin(config.GPIO_LED_STATUS, False)
            self._set_pin(config.GPIO_LED_ALARM,  False)
            try:
                self._GPIO.cleanup()
            except Exception:
                pass
            logger.info("GPIO cleanup done")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _set_pin(self, pin: int, value: bool):
        if self._sim:
            return
        try:
            self._GPIO.output(pin, self._GPIO.HIGH if value else self._GPIO.LOW)
        except Exception as exc:
            logger.error("GPIO write error pin %d: %s", pin, exc)

