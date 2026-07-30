#include <Arduino.h>
#include <Wire.h>
#include <SensirionI2cSen66.h>

#include <WiFi.h>
#include <HTTPClient.h>

// WiFi credentials and the server address live in secrets.h, which is
// git-ignored so they are never committed. Copy secrets.h.example to
// secrets.h and fill in your own values before building.
#include "secrets.h"

//==================================================
// USER CONFIGURATION
//==================================================

// ---------- Node ----------
const int NODE_ID = 3;
const char* NODE_NAME = "Bedroom";

// ---------- WiFi (from secrets.h) ----------
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASSWORD;

// ---------- Flask Server (from secrets.h) ----------
const char* serverName = SERVER_URL;

// ---------- Sampling ----------
const unsigned long SAMPLE_PERIOD = 5000;   // milliseconds

//==================================================
// SENSOR
//==================================================

SensirionI2cSen66 sensor;

static char errorMessage[64];
static int16_t error;

//==================================================
// WiFi Helper
//==================================================

void connectWiFi() {

  if (WiFi.status() == WL_CONNECTED)
    return;

  Serial.println();
  Serial.println("Connecting to WiFi...");

  WiFi.disconnect(true);
  delay(500);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi Connected");

  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  Serial.print("Node: ");
  Serial.println(NODE_NAME);

  Serial.print("Node ID: ");
  Serial.println(NODE_ID);

  Serial.println();
}

//==================================================
// SETUP
//==================================================

void setup() {

  Serial.begin(115200);
  Wire.begin();

  // ---------- SEN66 ----------
  sensor.begin(Wire, SEN66_I2C_ADDR_6B);

  sensor.stopMeasurement();

  delay(50);

  // Sensirion recommended temperature compensation
  sensor.setTemperatureOffsetParameters(
      -400,
      20,
      800,
      0);

  error = sensor.startContinuousMeasurement();

  if (error != 0) {

    errorToString(error, errorMessage, sizeof(errorMessage));

    Serial.print("Failed to start sensor: ");
    Serial.println(errorMessage);

    while (true);
  }

  delay(1000);

  // ---------- WiFi ----------
  connectWiFi();
}

//==================================================
// LOOP
//==================================================

void loop() {

  connectWiFi();

  uint8_t padding = 0;
  bool dataReady = false;

  uint16_t pm1 = 0;
  uint16_t pm25 = 0;
  uint16_t pm4 = 0;
  uint16_t pm10 = 0;

  int16_t humidityRaw = 0;
  int16_t temperatureRaw = 0;

  int16_t vocRaw = 0;
  int16_t noxRaw = 0;

  uint16_t co2 = 0;

  //------------------------------------------------
  // Check if measurement is ready
  //------------------------------------------------

  error = sensor.getDataReady(padding, dataReady);

  if (error != 0) {

    errorToString(error, errorMessage, sizeof(errorMessage));

    Serial.print("Data Ready Error: ");
    Serial.println(errorMessage);

    delay(1000);
    return;
  }

  if (!dataReady) {
    delay(100);
    return;
  }

  //------------------------------------------------
  // Read measurements
  //------------------------------------------------

  error = sensor.readMeasuredValuesAsIntegers(
      pm1,
      pm25,
      pm4,
      pm10,
      humidityRaw,
      temperatureRaw,
      vocRaw,
      noxRaw,
      co2);

  if (error != 0) {

    errorToString(error, errorMessage, sizeof(errorMessage));

    Serial.print("Read Error: ");
    Serial.println(errorMessage);

    delay(1000);
    return;
  }

  //------------------------------------------------
  // Convert units
  //------------------------------------------------

  float pm1Value = pm1 / 10.0;
  float pm25Value = pm25 / 10.0;
  float pm4Value = pm4 / 10.0;
  float pm10Value = pm10 / 10.0;

  float humidity = humidityRaw / 100.0;
  float temperature = temperatureRaw / 200.0;

  //------------------------------------------------
  // Serial Output
  //------------------------------------------------

  Serial.println();
  Serial.println("========================================");

  Serial.print("Node: ");
  Serial.println(NODE_NAME);

  Serial.print("Node ID: ");
  Serial.println(NODE_ID);

  Serial.print("Uptime (s): ");
  Serial.println(millis() / 1000);

  Serial.println();

  Serial.print("PM1.0: ");
  Serial.print(pm1Value);
  Serial.println(" ug/m3");

  Serial.print("PM2.5: ");
  Serial.print(pm25Value);
  Serial.println(" ug/m3");

  Serial.print("PM4.0: ");
  Serial.print(pm4Value);
  Serial.println(" ug/m3");

  Serial.print("PM10: ");
  Serial.print(pm10Value);
  Serial.println(" ug/m3");

  Serial.print("VOC Index: ");
  Serial.println(vocRaw);

  Serial.print("NOx Index: ");
  Serial.println(noxRaw);

  Serial.print("CO2: ");
  Serial.print(co2);
  Serial.println(" ppm");

  Serial.print("Temperature: ");
  Serial.print(temperature);
  Serial.println(" C");

  Serial.print("Humidity: ");
  Serial.print(humidity);
  Serial.println(" %");

  //------------------------------------------------
  // Send to Flask server
  //------------------------------------------------

  if (WiFi.status() == WL_CONNECTED) {

    HTTPClient http;

    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    String json =
      "{"
      "\"node_id\":" + String(NODE_ID) +
      ",\"node\":\"" + String(NODE_NAME) + "\"" +
      ",\"pm1\":" + String(pm1Value, 1) +
      ",\"pm25\":" + String(pm25Value, 1) +
      ",\"pm4\":" + String(pm4Value, 1) +
      ",\"pm10\":" + String(pm10Value, 1) +
      ",\"voc\":" + String(vocRaw) +
      ",\"nox\":" + String(noxRaw) +
      ",\"co2\":" + String(co2) +
      ",\"temperature\":" + String(temperature, 2) +
      ",\"humidity\":" + String(humidity, 2) +
      "}";

    int responseCode = http.POST(json);

    Serial.print("HTTP Response: ");
    Serial.println(responseCode);

    http.end();

  } else {

    Serial.println("WiFi not connected.");
  }

  delay(SAMPLE_PERIOD);
}