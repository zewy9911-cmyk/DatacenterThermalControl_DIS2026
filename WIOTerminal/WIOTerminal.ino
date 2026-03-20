/**
 * WIOTerminal.ino
 * ─────────────────────────────────────────────────────────────────────────────
 * Seeed Studio WIO Terminal (ATSAMD51P19A)
 * SHT40 Temperature & Humidity Sensor — Datacenter Thermal Monitor
 *
 * Hardware:
 *   • WIO Terminal (ATSAMD51P19A, 120 MHz Cortex-M4)
 *   • Seeed Grove SHT40 sensor connected to the right Grove I²C port
 *     (SDA = GPIO 8 / SCL = GPIO 9 on the WIO Terminal)
 *   • USB-C connected to Raspberry Pi (shows up as /dev/ttyACM0)
 *
 * Outputs JSON lines to USB Serial every READ_INTERVAL_MS milliseconds:
 *   {"node":"wio_sht40_01","temperature":23.45,"humidity":55.30,"source":"SHT40","simulation":false}
 *
 * Libraries required (install via Arduino Library Manager):
 *   1. Seeed Arduino LCD           — "Seeed_Arduino_LCD"     (TFT display)
 *   2. Adafruit SHT4x Library      — "Adafruit SHT4x Library"
 *   3. Adafruit Unified Sensor     — "Adafruit Unified Sensor" (dependency)
 *   4. Wire                        — built-in
 *
 * Board package (Board Manager):
 *   URL: https://files.seeedstudio.com/arduino/package_seeeduino_boards_index.json
 *   Board: "Seeeduino Wio Terminal"
 * ─────────────────────────────────────────────────────────────────────────────
 */

#include <Arduino.h>
#include <Wire.h>
#include <TFT_eSPI.h>      // Seeed_Arduino_LCD re-exports this
#include <Adafruit_SHT4x.h>

// ── Configuration ─────────────────────────────────────────────────────────────
#define SERIAL_BAUD        115200
#define READ_INTERVAL_MS   2000        // sensor poll cadence (ms)
#define NODE_ID            "wio_sht40_01"
#define TEMP_WARN_C        25.0        // yellow warning above this
#define TEMP_CRIT_C        30.0        // red critical above this
#define HUM_WARN_PCT       60.0
#define HUM_CRIT_PCT       70.0

// ── Hardware objects ──────────────────────────────────────────────────────────
TFT_eSPI    tft  = TFT_eSPI();
Adafruit_SHT4x sht4;

// ── State ─────────────────────────────────────────────────────────────────────
float        g_temp      = 0.0f;
float        g_hum       = 0.0f;
bool         g_sensorOk  = false;
bool         g_simMode   = false;
unsigned long g_lastRead = 0;
unsigned long g_readCount = 0;

// ─────────────────────────────────────────────────────────────────────────────
//  Display helpers
// ─────────────────────────────────────────────────────────────────────────────

#define C_BG         TFT_NAVY
#define C_HEADER_BG  0x0451   // dark teal
#define C_CYAN       TFT_CYAN
#define C_WHITE      TFT_WHITE
#define C_GREY       TFT_LIGHTGREY
#define C_GREEN      TFT_GREEN
#define C_YELLOW     TFT_YELLOW
#define C_RED        TFT_RED
#define C_BLACK      TFT_BLACK

/** Pick a colour for a value vs. warning/critical thresholds */
static uint16_t thresholdColor(float val, float warn, float crit) {
    if (val >= crit) return C_RED;
    if (val >= warn) return C_YELLOW;
    return C_GREEN;
}

/** Draw the static header bar */
static void drawHeader() {
    tft.fillRect(0, 0, 320, 38, C_HEADER_BG);
    tft.setTextColor(C_CYAN, C_HEADER_BG);
    tft.setTextSize(2);
    tft.setCursor(6, 10);
    tft.print("  Datacenter Thermal  SHT40");
}

/** Draw one value card (temperature or humidity) */
static void drawCard(int x, int y, int w, int h,
                     const char* label,
                     float value, const char* unit,
                     float warnT, float critT)
{
    uint16_t valColor = thresholdColor(value, warnT, critT);

    tft.fillRoundRect(x, y, w, h, 8, C_BG);
    tft.drawRoundRect(x, y, w, h, 8, C_CYAN);

    // Label
    tft.setTextColor(C_CYAN, C_BG);
    tft.setTextSize(2);
    tft.setCursor(x + (w - 4 * 12) / 2, y + 8);
    tft.print(label);

    // Value
    char buf[12];
    dtostrf(value, 5, 1, buf);
    tft.setTextSize(4);
    tft.setTextColor(valColor, C_BG);
    tft.setCursor(x + 8, y + 42);
    tft.print(buf);

    // Unit
    tft.setTextSize(2);
    tft.setTextColor(C_GREY, C_BG);
    tft.setCursor(x + 14, y + 105);
    tft.print(unit);
}

/** Bottom status bar */
static void drawStatus() {
    tft.fillRect(0, 212, 320, 28, C_BLACK);
    tft.setTextSize(1);
    tft.setCursor(6, 219);
    if (g_simMode) {
        tft.setTextColor(C_YELLOW, C_BLACK);
        tft.print("[SIM]  No SHT40 detected - simulated data  |  ");
    } else {
        tft.setTextColor(C_GREEN, C_BLACK);
        tft.print("[HW]  SHT40 OK  |  ");
    }
    tft.setTextColor(C_GREY, C_BLACK);
    tft.print("Readings: ");
    tft.print(g_readCount);
}

/** Full screen redraw */
static void refreshDisplay() {
    drawCard( 8, 44, 148, 160, "TEMP",
              g_temp, "deg C",
              TEMP_WARN_C, TEMP_CRIT_C);
    drawCard(164, 44, 148, 160, "HUM",
              g_hum, "% RH",
              HUM_WARN_PCT, HUM_CRIT_PCT);
    drawStatus();
}

// ─────────────────────────────────────────────────────────────────────────────
//  JSON serial output
// ─────────────────────────────────────────────────────────────────────────────

static void sendJSON(float temp, float hum, bool sim) {
    Serial.print(F("{\"node\":\""));
    Serial.print(NODE_ID);
    Serial.print(F("\",\"temperature\":"));
    Serial.print(temp, 2);
    Serial.print(F(",\"humidity\":"));
    Serial.print(hum, 2);
    Serial.print(F(",\"source\":\"SHT40\""));
    Serial.print(F(",\"simulation\":"));
    Serial.print(sim ? F("true") : F("false"));
    Serial.println(F("}"));
}

// ─────────────────────────────────────────────────────────────────────────────
//  Simulation fallback (if no SHT40 detected)
// ─────────────────────────────────────────────────────────────────────────────

static void simulateReading(float &temp, float &hum) {
    float t = millis() / 1000.0f;
    temp = 22.0f + 4.0f * sinf(t * 0.05f) + 0.5f * sinf(t * 0.3f);
    hum  = 55.0f + 10.0f * sinf(t * 0.03f);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Button handling (WIO Terminal top-panel buttons)
//    WIO_KEY_A = GPIO WIO_KEY_A (rightmost)  — not used here, reserved
//    WIO_KEY_B = GPIO WIO_KEY_B (middle)     — toggle display brightness
//    WIO_KEY_C = GPIO WIO_KEY_C (leftmost)   — force single-shot read
// ─────────────────────────────────────────────────────────────────────────────

static bool btnCPrev = HIGH;

static void handleButtons() {
    bool btnC = digitalRead(WIO_KEY_C);
    if (btnC == LOW && btnCPrev == HIGH) {
        // Force immediate re-read
        g_lastRead = 0;
    }
    btnCPrev = btnC;
}

// ─────────────────────────────────────────────────────────────────────────────
//  Setup
// ─────────────────────────────────────────────────────────────────────────────

void setup() {
    Serial.begin(SERIAL_BAUD);

    // Buttons (active LOW, internal pull-up)
    pinMode(WIO_KEY_A, INPUT_PULLUP);
    pinMode(WIO_KEY_B, INPUT_PULLUP);
    pinMode(WIO_KEY_C, INPUT_PULLUP);

    // TFT
    tft.begin();
    tft.setRotation(3);         // landscape, USB-C at bottom-right
    tft.fillScreen(C_BG);
    drawHeader();

    // Splash
    tft.setTextColor(C_WHITE, C_BG);
    tft.setTextSize(2);
    tft.setCursor(10, 90);
    tft.print("Initialising SHT40...");

    // I²C + SHT40
    Wire.begin();
    delay(100);

    if (sht4.begin()) {
        sht4.setPrecision(SHT4X_HIGH_PRECISION);
        sht4.setHeater(SHT4X_NO_HEATER);
        g_sensorOk = true;
        g_simMode  = false;

        tft.setTextColor(C_GREEN, C_BG);
        tft.setCursor(10, 120);
        tft.print("SHT40 found at 0x44  OK");
    } else {
        g_sensorOk = false;
        g_simMode  = true;

        tft.setTextColor(C_YELLOW, C_BG);
        tft.setCursor(10, 120);
        tft.print("SHT40 NOT found");
        tft.setCursor(10, 145);
        tft.print("Running in SIMULATION mode");
    }

    delay(1200);
    tft.fillScreen(C_BG);
    drawHeader();
    drawStatus();

    // Print startup JSON for Raspberry Pi log
    Serial.print(F("{\"event\":\"startup\",\"node\":\""));
    Serial.print(NODE_ID);
    Serial.print(F("\",\"sensor\":\"SHT40\",\"simulation\":"));
    Serial.println(g_simMode ? F("true}") : F("false}"));
}

// ─────────────────────────────────────────────────────────────────────────────
//  Loop
// ─────────────────────────────────────────────────────────────────────────────

void loop() {
    handleButtons();

    unsigned long now = millis();
    if (now - g_lastRead >= (unsigned long)READ_INTERVAL_MS) {
        g_lastRead = now;

        if (g_sensorOk) {
            sensors_event_t evtHum, evtTemp;
            g_sensorOk = sht4.getEvent(&evtHum, &evtTemp);
            if (g_sensorOk) {
                g_temp    = evtTemp.temperature;
                g_hum     = evtHum.relative_humidity;
                g_simMode = false;
            } else {
                // Sensor lost mid-run
                simulateReading(g_temp, g_hum);
                g_simMode = true;
            }
        } else {
            simulateReading(g_temp, g_hum);
        }

        g_readCount++;
        refreshDisplay();
        sendJSON(g_temp, g_hum, g_simMode);
    }
}

