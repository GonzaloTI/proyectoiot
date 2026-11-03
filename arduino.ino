#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <WiFi.h>
#include <HTTPClient.h>

#define SDA_PIN 21
#define SCL_PIN 22
#define SOIL_MOISTURE_PIN 35 // Pin analógico al que se conecta el pin 'A0' del sensor de humedad de suelo

// Calibración típica para el sensor de humedad de suelo (ADC de 12 bits en ESP32: 0 - 4095)
// Ajusta estos valores según las lecturas físicas de tu sensor
const int SOIL_DRY_VAL = 4095; // Sensor en el aire (seco)
const int SOIL_WET_VAL = 1000; // Sensor sumergido en agua/tierra húmeda

#define RELAY_1_PIN 4 // Pin GPIO al que se conecta el pin 'IN' del Relé 1
#define RELAY_2_PIN 5 // Pin GPIO al que se conecta el pin 'IN' del Relé 2 (puedes cambiarlo según tus conexiones)
#define MQ135_PIN 34 // Pin analógico (GPIO 34) al que se conecta el pin 'AO' del MQ-135

// NOTA: La mayoría de módulos de relé comerciales para Arduino son de lógica inversa (se activan con LOW).
// Si tu relé se activa con nivel ALTO, cambia RELAY_ON a HIGH y RELAY_OFF a LOW.
#define RELAY_ON LOW
#define RELAY_OFF HIGH

// Configuración de Red WiFi (Reemplaza con tus datos)
const char* ssid = "gonzalo";
const char* password = "1234567899";

// Dirección IP del servidor Flask (Reemplaza con la IP de tu computadora)
const char* serverName = "http://10.86.129.92:5000/api/datos";

Adafruit_BMP280 bmp;
bool relay_1_activo = false;
bool relay_2_activo = false;

void setup() {
  Serial.begin(115200);

  // Configuración de los pines de los relés
  pinMode(RELAY_1_PIN, OUTPUT);
  digitalWrite(RELAY_1_PIN, RELAY_OFF); // Inicialmente apagado
  relay_1_activo = false;

  pinMode(RELAY_2_PIN, OUTPUT);
  digitalWrite(RELAY_2_PIN, RELAY_OFF); // Inicialmente apagado
  relay_2_activo = false;

  // Configuración de los pines analógicos
  pinMode(MQ135_PIN, INPUT);
  pinMode(SOIL_MOISTURE_PIN, INPUT);

  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println();
  Serial.println("Inicializando BMP280...");

  if (!bmp.begin(0x76)) {
    Serial.println("ERROR: No se encontró el BMP280.");
    while (1);
  }
  Serial.print("Chip ID: 0x");
  Serial.println(bmp.sensorID(), HEX);
  Serial.println("BMP280 detectado correctamente.");

  // Conexión WiFi
  Serial.print("Conectando a WiFi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  
  // Esperar a que se conecte
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 20) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("");
    Serial.println("Conexión WiFi establecida.");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("");
    Serial.println("No se pudo conectar al WiFi. Iniciando en modo local autónomo.");
  }
}

void loop() {
  float temperatura = bmp.readTemperature();
  float presion     = bmp.readPressure() / 100.0F;   // hPa
  float altitud     = bmp.readAltitude(1013.25);     // metros

  // Leer sensor de calidad de aire MQ-135 en GPIO 34
  int raw_mq = analogRead(MQ135_PIN);
  
  // Fórmulas de estimación: el MQ-135 tiene base de 400 PPM de CO2 en aire limpio
  float co2_ppm = 400.0 + ((float)raw_mq * 0.4);
  // El humo se activa por encima de un umbral base (ej: 700 ADC)
  float humo_ppm = (raw_mq > 700) ? ((float)(raw_mq - 700) * 0.3) : 0.0;

  // Leer sensor de humedad de suelo en GPIO 35
  int raw_soil = analogRead(SOIL_MOISTURE_PIN);
  // Convertir lectura analógica a porcentaje (%)
  float humedad_suelo = 100.0 * (1.0 - ((float)(raw_soil - SOIL_WET_VAL) / (SOIL_DRY_VAL - SOIL_WET_VAL)));
  if (humedad_suelo < 0.0) humedad_suelo = 0.0;
  if (humedad_suelo > 100.0) humedad_suelo = 100.0;

  Serial.println("=================================");
  Serial.print("Temperatura : ");
  Serial.print(temperatura, 2);
  Serial.println(" °C");
  Serial.print("Presión     : ");
  Serial.print(presion, 2);
  Serial.println(" hPa");
  Serial.print("Altitud     : ");
  Serial.print(altitud, 2);
  Serial.println(" m");
  Serial.print("CO2 (PPM)   : ");
  Serial.print(co2_ppm, 1);
  Serial.println(" ppm");
  Serial.print("Humo (PPM)  : ");
  Serial.print(humo_ppm, 1);
  Serial.println(" ppm");
  Serial.print("ADC MQ-135  : ");
  Serial.println(raw_mq);
  Serial.print("Humedad Suel: ");
  Serial.print(humedad_suelo, 1);
  Serial.println(" %");
  Serial.print("ADC Humedad : ");
  Serial.println(raw_soil);

  // Si estamos conectados a WiFi, enviamos datos al servidor
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    // Construimos el payload JSON directamente como String con CO2, Humo, Humedad de suelo y ambos relés
    String jsonPayload = "{\"temperatura\":" + String(temperatura, 2) + 
                         ",\"presion\":" + String(presion, 2) + 
                         ",\"altitud\":" + String(altitud, 2) + 
                         ",\"relay_activo\":" + (relay_1_activo ? "true" : "false") + 
                         ",\"relay_2_activo\":" + (relay_2_activo ? "true" : "false") + 
                         ",\"co2\":" + String(co2_ppm, 1) + 
                         ",\"humo\":" + String(humo_ppm, 1) + 
                         ",\"humedad_suelo\":" + String(humedad_suelo, 1) + "}";

    Serial.println("Enviando datos al servidor...");
    int httpResponseCode = http.POST(jsonPayload);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("Respuesta de API (");
      Serial.print(httpResponseCode);
      Serial.print("): ");
      Serial.println(response);

      // Determinar si el servidor nos indica usar el modo manual o automático
      int modeIdx = response.indexOf("\"mode\"");
      bool manualMode = false;
      if (modeIdx >= 0) {
        String modeSub = response.substring(modeIdx);
        if (modeSub.indexOf("\"manual\"") >= 0) {
          manualMode = true;
        }
      }

      if (manualMode) {
        // MODO MANUAL: El servidor decide el estado de cada relé
        // Control Relé 1
        int relay1CmdIdx = response.indexOf("\"relay_command\"");
        if (relay1CmdIdx >= 0) {
          int endIdx = response.indexOf(",", relay1CmdIdx);
          if (endIdx < 0) endIdx = response.indexOf("}", relay1CmdIdx);
          String sub1 = response.substring(relay1CmdIdx, endIdx);
          if (sub1.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_ON);
            relay_1_activo = true;
            Serial.println("Modo: MANUAL | Relé 1: ENCENDER");
          } else if (sub1.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_1_PIN, RELAY_OFF);
            relay_1_activo = false;
            Serial.println("Modo: MANUAL | Relé 1: APAGAR");
          }
        }

        // Control Relé 2
        int relay2CmdIdx = response.indexOf("\"relay_2_command\"");
        if (relay2CmdIdx >= 0) {
          int endIdx2 = response.indexOf(",", relay2CmdIdx);
          if (endIdx2 < 0) endIdx2 = response.indexOf("}", relay2CmdIdx);
          String sub2 = response.substring(relay2CmdIdx, endIdx2);
          if (sub2.indexOf("\"ON\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_ON);
            relay_2_activo = true;
            Serial.println("Modo: MANUAL | Relé 2: ENCENDER");
          } else if (sub2.indexOf("\"OFF\"") >= 0) {
            digitalWrite(RELAY_2_PIN, RELAY_OFF);
            relay_2_activo = false;
            Serial.println("Modo: MANUAL | Relé 2: APAGAR");
          }
        }
      } else {
        // MODO AUTOMÁTICO (Local): El ESP32 decide según su propia temperatura
        controlAutonomoLocal(temperatura);
        Serial.println("Modo: AUTOMÁTICO (Control Local)");
      }
    } else {
      Serial.print("Error en petición HTTP: ");
      Serial.println(httpResponseCode);
      
      // Control de respaldo en caso de fallo en la llamada HTTP -> MODO AUTOMÁTICO LOCAL
      controlAutonomoLocal(temperatura);
      Serial.println("Error HTTP. Modo: AUTOMÁTICO (Respaldo Local)");
    }
    http.end();
  } else {
    // Si no hay conexión WiFi -> MODO AUTOMÁTICO LOCAL
    controlAutonomoLocal(temperatura);
    Serial.println("WiFi desconectado. Modo: AUTOMÁTICO (Respaldo Local)");
  }

  Serial.print("Estado Relé 1: ");
  Serial.println(relay_1_activo ? "ACTIVADO" : "DESACTIVADO");
  Serial.print("Estado Relé 2: ");
  Serial.println(relay_2_activo ? "ACTIVADO" : "DESACTIVADO");
  Serial.println("=================================\n");

  delay(2000); // Enviar datos cada 2 segundos
}

// Función de respaldo para control local autónomo de ambos relés
void controlAutonomoLocal(float temp) {
  if (temp >= 27.0) {
    digitalWrite(RELAY_1_PIN, RELAY_ON);
    relay_1_activo = true;
    digitalWrite(RELAY_2_PIN, RELAY_ON);
    relay_2_activo = true;
  } else {
    digitalWrite(RELAY_1_PIN, RELAY_OFF);
    relay_1_activo = false;
    digitalWrite(RELAY_2_PIN, RELAY_OFF);
    relay_2_activo = false;
  }
}