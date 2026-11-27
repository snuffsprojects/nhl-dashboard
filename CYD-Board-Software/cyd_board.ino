/*
 * bedside_vgk_ticker.cpp
 * For ESP32 2.8" Smart Display (Cheap Yellow Display / CYD)
 * Targets: New ESP32 Arduino Core LEDC API Standards
 */

#include <WiFi.h>

// FORCE PUBSUBCLIENT TO ALLOCATE PLENTY OF BUFFER MEMORY FOR HOCKEY JSON DATA
// This must be declared BEFORE including PubSubClient.h or the library will ignore it!
#define MQTT_MAX_PACKET_SIZE 512

#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include "secrets.h"

// === HARDWARE CONFIGURATION ===
#define LCD_BACKLIGHT_PIN 21  // Standard CYD screen backlight control pin

// === MQTT BROKER PROFILE ===
const char* mqtt_server = "192.168.1.50";      // Example only: use your Raspberry Pi's local IP address
const int mqtt_port = 1883;
const char* topic_score = "intranet/vgk/live_score";
const char* topic_goal  = "intranet/vgk/goal_alert";

// === DRIVER GLOBAL INSTANCES ===
TFT_eSPI tft = TFT_eSPI();
WiFiClient espClient;
PubSubClient client(espClient);

// Storage buffers to prevent drawing identical text over and over (stops flickering)
String lastScoreStr = "";
String lastTimeStr  = "";
String lastPrevScore = "";
int lastPeriod = -1;

bool goalAlertVisible = false;
bool wifiWarningVisible = false;
bool lastStatusBarConnected = false;
int lastStatusBarSignalLevel = -1;
unsigned long goalAlertStartedAt = 0;
unsigned long lastWifiReconnectAttempt = 0;
unsigned long lastMqttReconnectAttempt = 0;
unsigned long lastStatusBarUpdate = 0;

const unsigned long GOAL_ALERT_DURATION_MS = 30000;
const unsigned long RECONNECT_INTERVAL_MS = 5000;
const unsigned long STATUS_BAR_UPDATE_MS = 2000;
const int STATUS_BAR_HEIGHT = 20;

int wifiSignalLevel() {
    if (WiFi.status() != WL_CONNECTED) {
        return 0;
    }

    int rssi = WiFi.RSSI();
    if (rssi >= -55) return 4;
    if (rssi >= -67) return 3;
    if (rssi >= -75) return 2;
    return 1;
}

void drawWifiIndicator(bool connected, int signalLevel) {
    const int iconX = 7;
    const int iconBottom = 15;

    if (!connected) {
        tft.drawLine(iconX, 5, iconX + 12, 16, TFT_RED);
        tft.drawLine(iconX + 12, 5, iconX, 16, TFT_RED);
        return;
    }

    for (int bar = 0; bar < 4; bar++) {
        int height = 3 + (bar * 3);
        uint16_t colour = bar < signalLevel ? TFT_GREEN : TFT_DARKGREY;
        tft.fillRect(iconX + (bar * 4), iconBottom - height, 3, height, colour);
    }
}

void drawStatusBar(bool force = false) {
    bool connected = WiFi.status() == WL_CONNECTED;
    int signalLevel = wifiSignalLevel();

    if (!force && connected == lastStatusBarConnected && signalLevel == lastStatusBarSignalLevel) {
        return;
    }

    tft.fillRect(1, 1, 318, STATUS_BAR_HEIGHT - 1, TFT_BLACK);
    tft.drawFastHLine(1, STATUS_BAR_HEIGHT, 318, TFT_DARKGREY);
    drawWifiIndicator(connected, signalLevel);

    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(connected ? TFT_LIGHTGREY : TFT_RED, TFT_BLACK);
    tft.drawString(connected ? "Wi-Fi" : "Disconnected", 27, 10, 1);

    tft.setTextDatum(MR_DATUM);
    tft.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
    String cydAddress = connected ? WiFi.localIP().toString() : "No IP";
    tft.drawString("CYD: " + cydAddress, 312, 10, 1);

    lastStatusBarConnected = connected;
    lastStatusBarSignalLevel = signalLevel;
}

void clearGoalAlert() {
    tft.fillRect(5, 145, 310, 85, TFT_BLACK);
    goalAlertVisible = false;
}

void setup_wifi() {
    delay(10);
    tft.fillScreen(TFT_BLACK);
    tft.setTextDatum(MC_DATUM); // Center text origin
    tft.drawString("Connecting to Wi-Fi...", 160, 120, 2);

    WiFi.setAutoReconnect(true);
    WiFi.persistent(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
    }

    tft.fillScreen(TFT_BLACK);
    tft.drawString("Wi-Fi Connected!", 160, 120, 2);
    delay(1000);
    tft.fillScreen(TFT_BLACK);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    StaticJsonDocument<768> doc;
    DeserializationError error = deserializeJson(doc, payload, length);

    if (error) {
        return; // Drop parsing corrupted frames instantly
    }

    // === CHANNEL 1: LIVE CONTINUOUS TRACKING SCORE FEED ===
    if (strcmp(topic, topic_score) == 0) {
        // 💡 FIXED FOR ARDUINOJSON V7: Explicitly fetch values with clear type fallbacks
        const char* status = doc["status"].as<const char*>() ? doc["status"].as<const char*>() : "LIVE";
        const char* score_string = doc["score_string"].as<const char*>() ? doc["score_string"].as<const char*>() : "No Data";

        String currentStatus = String(status);
        String currentScore = String(score_string);

        // --- BRANCH A: ACTIVE LIVE MATCH SCREEN LAYOUT ---
        if (currentStatus == "LIVE") {
            int period = doc["period"].as<int>();
            const char* time_remaining = doc["time_remaining"].as<const char*>() ? doc["time_remaining"].as<const char*>() : "00:00";
            String currentTime = String(time_remaining);

            if (currentScore != lastScoreStr || currentTime != lastTimeStr || period != lastPeriod) {
                tft.fillRect(10, 22, 300, 108, TFT_BLACK);
                tft.setTextDatum(TC_DATUM);

                // Main Scoreboard Line
                tft.setTextColor(TFT_WHITE, TFT_BLACK);
                tft.drawString(score_string, 160, 28, 4);

                // Period Meta Row
                tft.setTextColor(0xB497, TFT_BLACK); // Custom Theme Accent Gold
                String periodText = (period > 3) ? "Overtime" : "Period: P" + String(period);
                tft.drawString(periodText, 160, 65, 2);

                // Match Clock Remaining
                tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
                tft.drawString("Time Remaining: " + currentTime, 160, 95, 2);

                lastScoreStr = currentScore;
                lastTimeStr  = currentTime;
                lastPeriod   = period;
            }
        }

        // --- BRANCH B: UPCOMING MATCH COUNTDOWN SCREEN LAYOUT ---
        else if (currentStatus == "COUNTDOWN") {
            const char* countdown = doc["countdown"].as<const char*>() ? doc["countdown"].as<const char*>() : "00:00";
            const char* prev_score = doc["prev_game_score"].as<const char*>() ? doc["prev_game_score"].as<const char*>() : "";
            String currentCountdown = String(countdown);
            String currentPrevScore = String(prev_score);

            // Only redraw if parameters text changes (stops flickering)
            if (currentScore != lastScoreStr || currentCountdown != lastTimeStr || currentPrevScore != lastPrevScore || lastPeriod != 99) {
                tft.fillRect(10, 22, 300, 108, TFT_BLACK);
                tft.setTextDatum(TC_DATUM);

                // 1. Draw Large Matchup Info
                tft.setTextColor(TFT_WHITE, TFT_BLACK);
                tft.drawString(score_string, 160, 25, 4); // Displays "Next: AWAY @ HOME"

                // 2. Draw Dynamic Upcoming Countdown Clock
                tft.setTextColor(TFT_GREEN, TFT_BLACK);
                tft.drawString("Puck Drop: " + currentCountdown, 160, 55, 2);

                // 3. 💡 MORNING REVEAL ROW: Draw the previous game score right across the bottom panel
                tft.setTextColor(0xB497, TFT_BLACK); // Custom Accent Gold
                tft.drawString(currentPrevScore, 160, 85, 4); // Renders large enough to read easily across the room!

                lastScoreStr = currentScore;
                lastTimeStr  = currentCountdown;
                lastPrevScore = currentPrevScore;
                lastPeriod   = 99; // Set dummy state to lock frame refresh
            }
        }

        // --- BRANCH C: SYNCHRONIZER STARTUP LAYOUT ---
        else if (currentStatus == "STARTUP") {
            if (currentScore != lastScoreStr || lastPeriod != 77) {
                tft.fillRect(10, 22, 300, 108, TFT_BLACK);
                tft.setTextDatum(TC_DATUM);

                tft.setTextColor(0xB497, TFT_BLACK);
                tft.drawString("VGK SCORE FEED", 160, 28, 2);

                tft.setTextColor(TFT_WHITE, TFT_BLACK);
                tft.drawString(score_string, 160, 58, 4);

                tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
                tft.drawString("Waiting for schedule data...", 160, 98, 2);

                lastScoreStr = currentScore;
                lastTimeStr = "";
                lastPrevScore = "";
                lastPeriod = 77;
            }
        }

        // --- BRANCH D: SEASON COMPLETE / OFFSEASON LAYOUT ---
        else if (currentStatus == "OFFSEASON") {
            const char* countdown = doc["countdown"].as<const char*>() ? doc["countdown"].as<const char*>() : "";
            String currentCountdown = String(countdown);

            if (currentScore != lastScoreStr || lastPeriod != 88) {
                tft.fillRect(10, 22, 300, 108, TFT_BLACK);
                tft.setTextDatum(TC_DATUM);

                tft.setTextColor(0xB497, TFT_BLACK);
                tft.drawString("STANLEY CUP OFF-SEASON", 160, 28, 2);

                tft.setTextColor(TFT_WHITE, TFT_BLACK);
                tft.drawString(score_string, 160, 55, 4);

                tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
                tft.drawString(currentCountdown, 160, 95, 2);

                lastScoreStr = currentScore;
                lastTimeStr  = "";
                lastPrevScore = "";
                lastPeriod   = 88;
            }
        }
    }
    // === CHANNEL 2: EVENT-DRIVEN TARGETED GOAL ALERTS ===
    else if (strcmp(topic, topic_goal) == 0) {
        const char* alert_type = doc["alert"].as<const char*>() ? doc["alert"].as<const char*>() : "GOAL SCORED!";

        tft.fillRect(5, 145, 310, 85, TFT_BLACK);
        tft.setTextDatum(BC_DATUM); // Bottom Center grounding

        if (strcmp(alert_type, "DISALLOWED_RESET") == 0) {
            const char* message = doc["details"]["msg"].as<const char*>() ? doc["details"]["msg"].as<const char*>() : "Goal overturned after review";

            tft.setTextColor(TFT_ORANGE, TFT_BLACK);
            tft.drawString("GOAL OVERTURNED", 160, 175, 2);
            tft.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
            tft.drawString(message, 160, 210, 2);

            goalAlertVisible = true;
            goalAlertStartedAt = millis();
            return;
        }

        // 💡 FIXED FOR ARDUINOJSON V7: Deep nested type-casting safeguards
        const char* scorer = doc["details"]["scorer"].as<const char*>() ? doc["details"]["scorer"].as<const char*>() : "Unknown Player";
        const char* team = doc["details"]["team"].as<const char*>() ? doc["details"]["team"].as<const char*>() : "UNK";
        const char* goal_time = doc["details"]["time"].as<const char*>() ? doc["details"]["time"].as<const char*>() : "00:00";
        const char* period_label = doc["details"]["period"].as<const char*>() ? doc["details"]["period"].as<const char*>() : "P1";

        // Flash targeted Goal Alert banner string
        tft.setTextColor(TFT_RED, TFT_BLACK);
        tft.drawString("GOAL SCORED!", 160, 165, 2);

        // Print scoring profile metrics text row
        tft.setTextColor(TFT_GREEN, TFT_BLACK);
        tft.drawString(String(scorer) + " (" + String(team) + ")", 160, 195, 2);
        tft.setTextColor(TFT_LIGHTGREY, TFT_BLACK);
        tft.drawString("Time: " + String(period_label) + " - " + String(goal_time), 160, 220, 2);

        goalAlertVisible = true;
        goalAlertStartedAt = millis();
    }
}

void reconnect() {
    if (client.connected() || WiFi.status() != WL_CONNECTED) {
        return;
    }

    unsigned long now = millis();
    if (now - lastMqttReconnectAttempt < RECONNECT_INTERVAL_MS) {
        return;
    }
    lastMqttReconnectAttempt = now;

    tft.fillRect(10, 200, 300, 30, TFT_BLACK);
    tft.setTextDatum(BC_DATUM);
    tft.setTextColor(TFT_ORANGE, TFT_BLACK);
    tft.drawString("MQTT Link Dropped. Retrying...", 160, 230, 2);

    String clientId = "ESP32BedsideTicker-";
    clientId += String(random(0xffff), HEX);

    if (client.connect(clientId.c_str())) {
        tft.fillRect(10, 200, 300, 30, TFT_BLACK);
        client.subscribe(topic_score);
        client.subscribe(topic_goal);
    }
}

void maintain_wifi() {
    if (WiFi.status() == WL_CONNECTED) {
        if (wifiWarningVisible) {
            tft.fillRect(10, 200, 300, 30, TFT_BLACK);
            wifiWarningVisible = false;
        }
        return;
    }

    if (!wifiWarningVisible) {
        client.disconnect();
        tft.fillRect(10, 200, 300, 30, TFT_BLACK);
        tft.setTextDatum(BC_DATUM);
        tft.setTextColor(TFT_ORANGE, TFT_BLACK);
        tft.drawString("Wi-Fi dropped. Reconnecting...", 160, 230, 2);
        wifiWarningVisible = true;
    }

    unsigned long now = millis();
    if (now - lastWifiReconnectAttempt >= RECONNECT_INTERVAL_MS) {
        lastWifiReconnectAttempt = now;
        WiFi.reconnect();
    }
}

void setup() {
    // 1. Core Hardware Layer Drivers Setup
    tft.init();
    tft.invertDisplay(false);
    tft.setRotation(1);
    tft.setRotation(1); // Force landscape presentation alignment orientation
    tft.fillScreen(TFT_BLACK);

    // 2. Modern ESP32 LEDC PWM Backlight Setup
    ledcAttach(LCD_BACKLIGHT_PIN, 5000, 8);
    ledcWrite(LCD_BACKLIGHT_PIN, 4); // Ultra-dim bedside night glow

    // 3. Network Subsystems Bootstrap Inits
    setup_wifi();
    client.setServer(mqtt_server, mqtt_port);
    client.setCallback(mqttCallback);

    // Explicit Initial Blueprint Baseline Template Setup
    tft.drawRect(0, 0, 320, 240, 0xB497); // Outline border with Gold Accent trim
    drawStatusBar(true);
}

void loop() {
    maintain_wifi();

    if (millis() - lastStatusBarUpdate >= STATUS_BAR_UPDATE_MS) {
        lastStatusBarUpdate = millis();
        drawStatusBar();
    }

    if (WiFi.status() != WL_CONNECTED) {
        delay(50);
        return;
    }

    if (!client.connected()) {
        reconnect();
    }

    if (client.connected()) {
        client.loop();
    }

    if (goalAlertVisible && millis() - goalAlertStartedAt >= GOAL_ALERT_DURATION_MS) {
        clearGoalAlert();
    }

    delay(50);
}
