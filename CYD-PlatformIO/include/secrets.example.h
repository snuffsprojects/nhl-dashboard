#pragma once

// Copy to secrets.h and enter the Wi-Fi used by the development CYD.
const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Raspberry Pi running Mosquitto and the VGK synchronizer.
const char* MQTT_SERVER = "192.168.1.50";
const uint16_t MQTT_PORT = 1883;

// 0-255. Start low for a bedside display and increase after testing.
const uint8_t CYD_BACKLIGHT_LEVEL = 18;
