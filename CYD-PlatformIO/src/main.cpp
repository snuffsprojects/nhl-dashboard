#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include "secrets.h"

#define MQTT_MAX_PACKET_SIZE 1536

namespace {
constexpr uint8_t BACKLIGHT_PIN = 21;
constexpr uint8_t BOOT_BUTTON_PIN = 0;
constexpr uint32_t RECONNECT_INTERVAL_MS = 5000;
constexpr uint32_t STATUS_REFRESH_MS = 2000;
constexpr uint32_t GOAL_HOLD_MS = 12000;
constexpr uint16_t SCREEN_W = 320;
constexpr uint16_t SCREEN_H = 240;

constexpr uint16_t C_BG = 0x0020;
constexpr uint16_t C_PANEL = 0x0861;
constexpr uint16_t C_PANEL_2 = 0x10A2;
constexpr uint16_t C_LINE = 0x31A6;
constexpr uint16_t C_TEXT = 0xEF7D;
constexpr uint16_t C_MUTED = 0x8C71;
constexpr uint16_t C_GOLD = 0xB497;
constexpr uint16_t C_GOLD_BRIGHT = 0xD5AD;
constexpr uint16_t C_BLUE = 0x09EE;
constexpr uint16_t C_GREEN = 0x4E8C;
constexpr uint16_t C_RED = 0xD9E7;
constexpr uint16_t C_ORANGE = 0xFC60;

const char* TOPIC_SCORE = "intranet/vgk/live_score";
const char* TOPIC_GOAL = "intranet/vgk/goal_alert";

TFT_eSPI tft;
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

enum class ScreenMode { Startup, Live, Final, Countdown, Offseason };

struct PeriodScore {
  String label;
  int away = 0;
  int home = 0;
};

struct ScoreState {
  ScreenMode mode = ScreenMode::Startup;
  String awayTeam = "VGK";
  String homeTeam = "OPP";
  int awayScore = 0;
  int homeScore = 0;
  int period = 0;
  String timeRemaining = "20:00";
  String countdown = "--";
  String previousScore = "Waiting for schedule";
  PeriodScore periods[5];
  uint8_t periodCount = 3;
  int shotsAway = 0;
  int shotsHome = 0;
  int hitsAway = 0;
  int hitsHome = 0;
  int blocksAway = 0;
  int blocksHome = 0;
};

ScoreState state;
bool goalVisible = false;
bool offlineOverlayVisible = false;
bool demoMode = false;
uint8_t demoStep = 0;
uint32_t goalStartedAt = 0;
uint32_t lastWifiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t lastStatusRefresh = 0;
uint32_t lastButtonChange = 0;
bool lastButtonPressed = false;

String valueOr(JsonVariantConst value, const char* fallback) {
  const char* result = value.as<const char*>();
  return result ? String(result) : String(fallback);
}

void setBacklight(uint8_t level) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(BACKLIGHT_PIN, 5000, 8);
  ledcWrite(BACKLIGHT_PIN, level);
#else
  constexpr uint8_t channel = 0;
  ledcSetup(channel, 5000, 8);
  ledcAttachPin(BACKLIGHT_PIN, channel);
  ledcWrite(channel, level);
#endif
}

void drawSignalBars(int x, int bottom, uint16_t colour) {
  int level = 0;
  if (WiFi.status() == WL_CONNECTED) {
    const int rssi = WiFi.RSSI();
    level = rssi >= -55 ? 4 : rssi >= -67 ? 3 : rssi >= -75 ? 2 : 1;
  }
  for (int i = 0; i < 4; ++i) {
    const int h = 3 + i * 2;
    tft.fillRect(x + i * 4, bottom - h, 3, h, i < level ? colour : C_LINE);
  }
}

void drawTopStatus(const String& left, bool live = false) {
  tft.fillRect(0, 0, SCREEN_W, 22, C_BG);
  tft.drawFastHLine(0, 21, SCREEN_W, C_LINE);
  tft.setTextDatum(ML_DATUM);
  tft.setTextColor(live ? C_TEXT : C_MUTED, C_BG);
  if (live) {
    tft.fillCircle(9, 10, 3, C_RED);
    tft.drawString(left, 17, 11, 1);
  } else {
    tft.drawString(left, 8, 11, 1);
  }
  drawSignalBars(296, 16, C_GREEN);
}

String periodLabel() {
  if (state.period == 4) return "OT";
  if (state.period > 4) return "SO";
  return "P" + String(max(state.period, 1));
}

void drawTeam(int x, const String& abbreviation, bool vgk, const String& venue) {
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(vgk ? C_GOLD_BRIGHT : C_TEXT, C_BG);
  tft.drawString(abbreviation, x, 45, 4);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString(venue, x, 65, 1);
}

void drawScoreHero(bool showClock) {
  tft.fillRect(0, 22, SCREEN_W, 70, C_BG);
  drawTeam(48, state.awayTeam, state.awayTeam == "VGK", "AWAY");
  drawTeam(272, state.homeTeam, state.homeTeam == "VGK", "HOME");

  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_TEXT, C_BG);
  String score = String(state.awayScore) + "  -  " + String(state.homeScore);
  tft.drawString(score, 160, 48, 4);

  if (showClock) {
    String meta = periodLabel() + "  |  " + state.timeRemaining;
    const int width = tft.textWidth(meta, 1) + 16;
    tft.fillRoundRect(160 - width / 2, 69, width, 17, 8, C_PANEL_2);
    tft.drawRoundRect(160 - width / 2, 69, width, 17, 8, C_LINE);
    tft.setTextColor(C_TEXT, C_PANEL_2);
    tft.drawString(meta, 160, 77, 1);
  }
}

void drawPeriodTable() {
  const int x = 10;
  const int y = 94;
  const int w = 300;
  const int h = 49;
  tft.fillRoundRect(x, y, w, h, 4, C_PANEL);
  tft.drawRoundRect(x, y, w, h, 4, C_LINE);

  const int columns = state.periodCount < 4 ? state.periodCount : 4;
  const int teamWidth = 55;
  const int cellWidth = (w - teamWidth - 31) / max(columns, 1);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_MUTED, C_PANEL);
  tft.drawString("TEAM", x + 25, y + 8, 1);
  for (int i = 0; i < columns; ++i) {
    tft.drawString(state.periods[i].label, x + teamWidth + cellWidth * i + cellWidth / 2, y + 8, 1);
  }
  tft.drawString("T", x + w - 15, y + 8, 1);
  tft.drawFastHLine(x + 5, y + 15, w - 10, C_LINE);

  const String teams[2] = {state.awayTeam, state.homeTeam};
  const int totals[2] = {state.awayScore, state.homeScore};
  for (int row = 0; row < 2; ++row) {
    const int cy = y + 24 + row * 16;
    tft.setTextDatum(ML_DATUM);
    tft.setTextColor(teams[row] == "VGK" ? C_GOLD_BRIGHT : C_TEXT, C_PANEL);
    tft.drawString(teams[row], x + 8, cy, 2);
    tft.setTextDatum(MC_DATUM);
    for (int i = 0; i < columns; ++i) {
      const int value = row == 0 ? state.periods[i].away : state.periods[i].home;
      tft.drawString(String(value), x + teamWidth + cellWidth * i + cellWidth / 2, cy, 1);
    }
    tft.setTextColor(C_TEXT, C_PANEL);
    tft.drawString(String(totals[row]), x + w - 15, cy, 2);
  }
}

void drawComparisonBar(int y, const char* label, int away, int home) {
  constexpr int x = 10;
  constexpr int w = 300;
  constexpr int h = 21;
  constexpr int gap = 2;
  const int total = away + home;
  const int leftW = total > 0 ? ((w - gap) * away) / total : (w - gap) / 2;
  const int rightW = w - gap - leftW;
  const uint16_t awayColour = state.awayTeam == "VGK" ? C_GOLD : C_BLUE;
  const uint16_t homeColour = state.homeTeam == "VGK" ? C_GOLD : C_BLUE;

  tft.fillRoundRect(x, y, w, h, 3, C_PANEL_2);
  if (leftW > 0) tft.fillRect(x, y, leftW, h, awayColour);
  if (rightW > 0) tft.fillRect(x + leftW + gap, y, rightW, h, homeColour);
  tft.setTextDatum(ML_DATUM);
  tft.setTextColor(C_TEXT);
  tft.drawString(String(away), x + 6, y + h / 2, 2);
  tft.setTextDatum(MR_DATUM);
  tft.drawString(String(home), x + w - 6, y + h / 2, 2);

  const int labelW = tft.textWidth(label, 1) + 12;
  tft.fillRoundRect(160 - labelW / 2, y + 3, labelW, h - 6, 3, C_PANEL);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_TEXT, C_PANEL);
  tft.drawString(label, 160, y + h / 2, 1);
}

void drawFooter(const String& left, const String& right) {
  tft.fillRect(0, 222, SCREEN_W, 18, C_BG);
  tft.drawFastHLine(0, 222, SCREEN_W, C_LINE);
  tft.setTextColor(C_MUTED, C_BG);
  tft.setTextDatum(ML_DATUM);
  tft.drawString(left, 7, 231, 1);
  tft.setTextDatum(MR_DATUM);
  tft.drawString(right, 313, 231, 1);
}

void drawLiveOrFinal(bool finalState) {
  tft.fillScreen(C_BG);
  drawTopStatus(finalState ? "FINAL" : "LIVE  |  " + periodLabel(), !finalState);
  drawScoreHero(!finalState);
  drawPeriodTable();
  drawComparisonBar(148, "SHOTS", state.shotsAway, state.shotsHome);
  drawComparisonBar(172, "HITS", state.hitsAway, state.hitsHome);
  drawComparisonBar(196, "BLOCKS", state.blocksAway, state.blocksHome);
  drawFooter(finalState ? "GAME COMPLETE" : "VGK SCORELINK", finalState ? "FINAL" : "LIVE DATA");
}

void drawCountdown() {
  tft.fillScreen(C_BG);
  drawTopStatus("NEXT GAME");
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString("UPCOMING MATCHUP", 160, 52, 1);
  tft.setTextColor(C_GOLD_BRIGHT, C_BG);
  tft.drawString(state.awayTeam + "  @  " + state.homeTeam, 160, 80, 4);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString("PUCK DROP IN", 160, 111, 1);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(state.countdown, 160, 140, 4);
  tft.drawFastHLine(55, 166, 210, C_LINE);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString(state.previousScore, 160, 187, 2);
  drawFooter("VGK SCORELINK", "SCHEDULE SYNCED");
}

void drawStartup() {
  tft.fillScreen(C_BG);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_GOLD_BRIGHT, C_BG);
  tft.drawString("VGK", 160, 76, 4);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString("SCORELINK", 160, 112, 4);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString("CONNECTING TO GAME FEED", 160, 148, 1);
}

void renderCurrentState() {
  goalVisible = false;
  offlineOverlayVisible = false;
  switch (state.mode) {
    case ScreenMode::Live: drawLiveOrFinal(false); break;
    case ScreenMode::Final: drawLiveOrFinal(true); break;
    case ScreenMode::Countdown: drawCountdown(); break;
    case ScreenMode::Offseason: drawCountdown(); break;
    default: drawStartup(); break;
  }
}

void drawGoalAlert(const String& scorer, const String& team, const String& period, const String& time) {
  tft.fillScreen(C_BG);
  for (int radius = 105; radius > 20; radius -= 14) {
    tft.drawCircle(160, 112, radius, radius % 2 ? C_GOLD : C_LINE);
  }
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(C_GOLD_BRIGHT, C_BG);
  tft.drawString("GOAL!", 160, 82, 4);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(scorer + "  |  " + team, 160, 126, 2);
  tft.setTextColor(C_MUTED, C_BG);
  tft.drawString(period + "  |  " + time, 160, 151, 1);
  tft.drawString(state.awayTeam + " " + String(state.awayScore) + "  -  " + state.homeTeam + " " + String(state.homeScore), 160, 178, 2);
  goalVisible = true;
  goalStartedAt = millis();
}

void drawOfflineOverlay(bool force = false) {
  if (offlineOverlayVisible || goalVisible || (demoMode && !force)) return;
  tft.fillRect(0, 0, SCREEN_W, 16, C_RED);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE, C_RED);
  tft.drawString("CONNECTION LOST  |  RETRYING", 160, 8, 1);
  offlineOverlayVisible = true;
}

void parseTeamsFromMatchup(const String& matchup) {
  const int separator = matchup.indexOf(" @ ");
  if (separator > 0) {
    state.awayTeam = matchup.substring(0, separator);
    state.homeTeam = matchup.substring(separator + 3);
  }
}

void handleScore(JsonDocument& doc) {
  const String status = valueOr(doc["status"], "STARTUP");
  const String matchup = valueOr(doc["matchup"], "");
  if (matchup.length()) parseTeamsFromMatchup(matchup);
  state.awayTeam = valueOr(doc["away_team"], state.awayTeam.c_str());
  state.homeTeam = valueOr(doc["home_team"], state.homeTeam.c_str());
  state.awayScore = doc["away_score"] | state.awayScore;
  state.homeScore = doc["home_score"] | state.homeScore;
  state.period = doc["period"] | state.period;
  state.timeRemaining = valueOr(doc["time_remaining"], state.timeRemaining.c_str());

  if (doc["period_scores"].is<JsonArray>()) {
    state.periodCount = 0;
    for (JsonArrayConst item : doc["period_scores"].as<JsonArrayConst>()) {
      if (state.periodCount >= 5) break;
      state.periods[state.periodCount].label = valueOr(item[0], "P");
      state.periods[state.periodCount].away = item[1] | 0;
      state.periods[state.periodCount].home = item[2] | 0;
      ++state.periodCount;
    }
  }
  if (state.periodCount == 0) state.periodCount = 3;

  if (doc["shots"].is<JsonArray>()) {
    state.shotsAway = doc["shots"][0] | 0;
    state.shotsHome = doc["shots"][1] | 0;
  }
  if (doc["hits"].is<JsonArray>()) {
    state.hitsAway = doc["hits"][0] | 0;
    state.hitsHome = doc["hits"][1] | 0;
  }
  if (doc["blocks"].is<JsonArray>()) {
    state.blocksAway = doc["blocks"][0] | 0;
    state.blocksHome = doc["blocks"][1] | 0;
  }

  if (status == "LIVE") {
    state.mode = ScreenMode::Live;
  } else if (status == "FINAL") {
    state.mode = ScreenMode::Final;
  } else if (status == "COUNTDOWN") {
    state.mode = ScreenMode::Countdown;
    state.countdown = valueOr(doc["countdown"], "--");
    state.previousScore = valueOr(doc["prev_game_score"], "No previous result");
  } else if (status == "OFFSEASON") {
    state.mode = ScreenMode::Offseason;
    state.countdown = valueOr(doc["countdown"], "SEE YOU NEXT SEASON");
    state.previousScore = valueOr(doc["score_string"], "Season complete");
  } else {
    state.mode = ScreenMode::Startup;
  }
  renderCurrentState();
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (demoMode) return;
  DynamicJsonDocument doc(1536);
  if (deserializeJson(doc, payload, length)) {
    Serial.println("MQTT JSON parse failed");
    return;
  }
  if (strcmp(topic, TOPIC_SCORE) == 0) {
    handleScore(doc);
    return;
  }
  if (strcmp(topic, TOPIC_GOAL) == 0) {
    const String alert = valueOr(doc["alert"], "GOAL SCORED!");
    if (alert == "DISALLOWED_RESET") {
      renderCurrentState();
      return;
    }
    drawGoalAlert(
      valueOr(doc["details"]["scorer"], "VGK PLAYER"),
      valueOr(doc["details"]["team"], "VGK"),
      valueOr(doc["details"]["period"], "P1"),
      valueOr(doc["details"]["time"], "00:00")
    );
  }
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("Connecting to Wi-Fi %s\n", WIFI_SSID);
}

void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  const uint32_t now = millis();
  if (now - lastMqttAttempt < RECONNECT_INTERVAL_MS) return;
  lastMqttAttempt = now;
  String clientId = "VGK-CYD-Pilot-" + String(static_cast<uint32_t>(ESP.getEfuseMac()), HEX);
  Serial.printf("Connecting to MQTT %s:%u\n", MQTT_SERVER, MQTT_PORT);
  if (mqtt.connect(clientId.c_str())) {
    mqtt.subscribe(TOPIC_SCORE);
    mqtt.subscribe(TOPIC_GOAL);
    offlineOverlayVisible = false;
    renderCurrentState();
    Serial.println("MQTT connected");
  }
}

void loadDemo(uint8_t step) {
  state.awayTeam = "VGK";
  state.homeTeam = "VAN";
  state.awayScore = 3;
  state.homeScore = 2;
  state.period = 3;
  state.timeRemaining = "04:21";
  state.periodCount = 3;
  state.periods[0] = {"P1", 0, 1};
  state.periods[1] = {"P2", 3, 1};
  state.periods[2] = {"P3", 0, 0};
  state.shotsAway = 28;
  state.shotsHome = 19;
  state.hitsAway = 24;
  state.hitsHome = 17;
  state.blocksAway = 12;
  state.blocksHome = 15;
  state.countdown = "1D 08:42";
  state.previousScore = "LAST  |  VGK 3 - VAN 2";

  switch (step) {
    case 0: state.mode = ScreenMode::Live; renderCurrentState(); break;
    case 1: state.mode = ScreenMode::Final; renderCurrentState(); break;
    case 2: state.mode = ScreenMode::Countdown; renderCurrentState(); break;
    case 3: drawGoalAlert("J. EICHEL", "VGK", "P3", "04:21"); break;
    case 4: state.mode = ScreenMode::Live; renderCurrentState(); offlineOverlayVisible = false; drawOfflineOverlay(true); break;
    default:
      demoMode = false;
      demoStep = 0;
      state.mode = ScreenMode::Startup;
      renderCurrentState();
      Serial.println("Demo mode disabled; resumed MQTT feed");
      break;
  }
}

void pollDemoButton() {
#if ENABLE_DEMO_BUTTON
  const bool pressed = digitalRead(BOOT_BUTTON_PIN) == LOW;
  const uint32_t now = millis();
  if (pressed != lastButtonPressed && now - lastButtonChange > 40) {
    lastButtonChange = now;
    lastButtonPressed = pressed;
    if (pressed) {
      demoMode = true;
      loadDemo(demoStep++);
      if (demoStep > 5) demoStep = 5;
    }
  }
#endif
}
}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  tft.init();
  tft.setRotation(1);
  tft.invertDisplay(false);
  setBacklight(CYD_BACKLIGHT_LEVEL);
  state.periods[0] = {"P1", 0, 0};
  state.periods[1] = {"P2", 0, 0};
  state.periods[2] = {"P3", 0, 0};
  drawStartup();
  connectWifi();
  mqtt.setServer(MQTT_SERVER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(1536);
}

void loop() {
  pollDemoButton();
  const uint32_t now = millis();

  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastWifiAttempt >= RECONNECT_INTERVAL_MS) {
      lastWifiAttempt = now;
      WiFi.reconnect();
    }
    drawOfflineOverlay();
  } else {
    connectMqtt();
    if (!mqtt.connected()) drawOfflineOverlay();
  }

  if (mqtt.connected()) mqtt.loop();
  if (goalVisible && now - goalStartedAt >= GOAL_HOLD_MS && !demoMode) renderCurrentState();
  if (now - lastStatusRefresh >= STATUS_REFRESH_MS) lastStatusRefresh = now;
  delay(25);
}
